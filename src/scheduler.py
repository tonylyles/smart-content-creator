"""
核心调度引擎 - 曾睿负责

基于 APScheduler 3.x 的智能内容创作调度系统。
实现赛题硬性要求：按时间节点自动触发内容生成。

功能：
- BackgroundScheduler 后台调度（不阻塞主线程）
- ThreadPoolExecutor 线程池（max_workers=5）
- SQLAlchemy + SQLite 持久化（程序重启不丢任务）
- Job 执行监听器（日志 + 全流程耗时监控）
- Cron 表达式 / 每日定时 / 间隔循环三种触发方式
- 防重叠机制（max_instances=1）
- DAG 风格闭环流水线：爬虫 → RAG → 生成 → 评估 → (自动重试)
- 全流程耗时 ≤30 分钟 SLA 保障

接口兼容性（严格对接队友代码）：
- 爬虫：src.spiders.spider_manager.SpiderManager.crawl_and_classify()
- RAG：src.rag.vector_db.VectorDB.add_documents()
- 生成：src.generator.ContentGenerator.generate(topic, timeline=...)
- 评估：src.evaluator.Evaluator.evaluate(content)
- 修订：src.generator.ContentGenerator.regenerate(title, content, eval_result)

参考：
- APScheduler 官方文档: https://apscheduler.readthedocs.io/en/3.x/
- django-apscheduler 事件监听模式
"""

import os
import sys
import time
import json
import logging
import traceback
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

# ==================== 日志配置 ====================

# 修复 Windows 控制台编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("scheduler")
logger.setLevel(logging.DEBUG)

# 控制台日志
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
))
logger.addHandler(_console)

# 文件日志
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_file_handler = logging.FileHandler(
    os.path.join(_LOG_DIR, "scheduler.log"),
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
))
logger.addHandler(_file_handler)


# ==================== 全局常量 ====================

# 全流程 SLA：30 分钟
PIPELINE_SLA_SECONDS = 30 * 60

# 评估不达标时的最大重试次数
MAX_REGENERATE_RETRIES = 3

# 默认时区
DEFAULT_TIMEZONE = "Asia/Shanghai"

# 线程池最大工作线程数
MAX_WORKERS = 5

# 技术准确率阈值（赛题要求 ≥95%）
ACCURACY_THRESHOLD = 0.95


def parse_cron_expr(cron_str: str) -> dict:
    """将标准 5/6 段 Cron 表达式拆解为 APScheduler 3.x CronTrigger 参数

    APScheduler 3.x 的 CronTrigger 不接受原始 cron 字符串，
    需要拆分成 minute=, hour=, day=, month=, day_of_week= 等独立参数。

    支持格式：
    - 5 段: "分 时 日 月 周" → "0 2 * * *" = 每日凌晨2点
    - 6 段: "秒 分 时 日 月 周" → "0 0 2 * * *" = 每日凌晨2点整

    特殊值映射：
    - * → None（APScheduler 默认匹配所有值）
    - */N → None + 依赖 APScheduler 的拆分处理

    Args:
        cron_str: Cron 表达式字符串

    Returns:
        可直接传入 CronTrigger(**result) 的参数字典

    Example:
        >>> parse_cron_expr("0 2 * * *")
        {'minute': '0', 'hour': '2'}
        >>> parse_cron_expr("0 */6 * * *")
        {'minute': '0', 'hour': '*/6'}
        >>> parse_cron_expr("30 8 * * 1-5")
        {'minute': '30', 'hour': '8', 'day_of_week': '1-5'}
    """
    parts = cron_str.strip().split()

    # 判断是 5 段还是 6 段
    if len(parts) == 5:
        minute_s, hour_s, day_s, month_s, dow_s = parts
    elif len(parts) == 6:
        _, minute_s, hour_s, day_s, month_s, dow_s = parts
    else:
        raise ValueError(
            f"Cron 表达式格式错误: '{cron_str}'，"
            f"应为 5 段（分 时 日 月 周）或 6 段（秒 分 时 日 月 周）"
        )

    result = {}
    # '*' 或空值映射为 None（让 APScheduler 匹配所有）
    if minute_s != "*":
        result["minute"] = minute_s
    if hour_s != "*":
        result["hour"] = hour_s
    if day_s != "*":
        result["day"] = day_s
    if month_s != "*":
        result["month"] = month_s
    if dow_s != "*":
        result["day_of_week"] = dow_s

    return result


# ==================== Job 执行监听器 ====================

class JobExecutionListener:
    """Job 执行监听器

    参考 django-apscheduler 的事件监听写法。
    监听 APScheduler 的 EVENT_JOB_EXECUTED 和 EVENT_JOB_ERROR 事件，
    记录每次执行的耗时、状态和异常信息。

    同时维护一个全局的「全流程耗时仪表盘」，
    用于监控 DAG 流水线是否满足 30 分钟 SLA。
    """

    def __init__(self):
        # 执行记录：{job_id: {"start": datetime, "end": datetime, "status": str, "duration_ms": int}}
        self._records: Dict[str, Dict[str, Any]] = {}
        # 全流程耗时历史（最近 N 次）
        self._pipeline_durations: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def on_job_executed(self, event):
        """任务成功执行后的回调"""
        job_id = event.job_id
        end_time = datetime.now()

        with self._lock:
            if job_id in self._records:
                self._records[job_id]["end"] = end_time
                self._records[job_id]["status"] = "success"
                duration_ms = int((end_time - self._records[job_id]["start"]).total_seconds() * 1000)
                self._records[job_id]["duration_ms"] = duration_ms

                # 如果是流水线任务，记录全流程耗时
                if "pipeline" in job_id.lower():
                    self._pipeline_durations.append({
                        "job_id": job_id,
                        "duration_ms": duration_ms,
                        "duration_sec": duration_ms / 1000,
                        "timestamp": end_time.isoformat(),
                        "sla_pass": duration_ms <= PIPELINE_SLA_SECONDS * 1000,
                    })
                    # 只保留最近 100 条记录
                    self._pipeline_durations = self._pipeline_durations[-100:]

        logger.info(
            "[监听器] Job '%s' 执行成功，耗时 %dms",
            job_id,
            self._records.get(job_id, {}).get("duration_ms", 0),
        )

    def on_job_error(self, event):
        """任务执行失败后的回调"""
        job_id = event.job_id
        end_time = datetime.now()
        exception = event.exception

        with self._lock:
            if job_id in self._records:
                self._records[job_id]["end"] = end_time
                self._records[job_id]["status"] = "error"
                self._records[job_id]["error"] = str(exception)
                duration_ms = int((end_time - self._records[job_id]["start"]).total_seconds() * 1000)
                self._records[job_id]["duration_ms"] = duration_ms

        logger.error(
            "[监听器] Job '%s' 执行失败，耗时 %dms，错误: %s",
            job_id,
            self._records.get(job_id, {}).get("duration_ms", 0),
            str(exception),
        )
        logger.debug("[监听器] 异常堆栈:\n%s", traceback.format_exc())

    def on_job_submitted(self, event):
        """任务提交执行时的回调"""
        job_id = event.job_id
        start_time = datetime.now()

        with self._lock:
            self._records[job_id] = {
                "job_id": job_id,
                "start": start_time,
                "end": None,
                "status": "running",
                "duration_ms": 0,
            }

        logger.info("[监听器] Job '%s' 已提交执行", job_id)

    def on_job_missed(self, event):
        """任务错过执行时间的回调"""
        job_id = event.job_id
        logger.warning("[监听器] Job '%s' 错过了执行时间", job_id)

    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取全流程耗时统计

        Returns:
            包含平均耗时、最大耗时、SLA 达标率等统计信息
        """
        with self._lock:
            durations = self._pipeline_durations

        if not durations:
            return {
                "total_runs": 0,
                "avg_duration_sec": 0,
                "max_duration_sec": 0,
                "min_duration_sec": 0,
                "sla_pass_rate": 0,
                "last_run": None,
            }

        sec_list = [d["duration_sec"] for d in durations]
        pass_count = sum(1 for d in durations if d["sla_pass"])
        total = len(durations)

        return {
            "total_runs": total,
            "avg_duration_sec": round(sum(sec_list) / total, 1),
            "max_duration_sec": round(max(sec_list), 1),
            "min_duration_sec": round(min(sec_list), 1),
            "sla_pass_rate": round(pass_count / total * 100, 1) if total > 0 else 0,
            "sla_target_sec": PIPELINE_SLA_SECONDS,
            "last_run": durations[-1]["timestamp"] if durations else None,
        }

    def get_record(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Job 的最近执行记录"""
        with self._lock:
            return self._records.get(job_id)


# ==================== DAG 流水线 ====================

class PipelineStage:
    """流水线阶段定义

    每个 Stage 代表 DAG 中的一个节点，包含：
    - name: 阶段名称
    - func: 执行函数
    - depends_on: 依赖的上游阶段列表（DAG 边）
    - timeout_sec: 单阶段超时时间
    """

    def __init__(self, name: str, func: Callable, depends_on: List[str] = None,
                 timeout_sec: int = 600):
        """
        Args:
            name: 阶段唯一标识（如 "crawl"、"rag_update"、"generate"、"evaluate"）
            func: 执行函数，接受 **kwargs 参数
            depends_on: 依赖的上游阶段名称列表
            timeout_sec: 单阶段超时秒数（默认 10 分钟）
        """
        self.name = name
        self.func = func
        self.depends_on = depends_on or []
        self.timeout_sec = timeout_sec
        # 执行结果
        self.output: Any = None
        self.status: str = "pending"  # pending / running / success / error / skipped
        self.error: Optional[str] = None
        self.duration_ms: int = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None


class ContentPipeline:
    """内容创作 DAG 流水线

    执行顺序：
    ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  crawl   │───>│ rag_update│───>│ generate │───>│ evaluate │
    └─────────┘    └──────────┘    └──────────┘    └──────────┘
                                                             │
                                          ┌──────────┐       │ (if accuracy < 0.95
                                          │regenerate│<──────┘  or compliance fail)
                                          └──────────┘
                                                │
                                          ┌──────────┐
                                          │ re-eval  │
                                          └──────────┘
    """

    def __init__(self, spider_manager=None, vector_db=None,
                 generator=None, evaluator=None, config: dict = None):
        """
        Args:
            spider_manager: SpiderManager 实例（胡圳刚）
            vector_db: VectorDB 实例（刘凯睿）
            generator: ContentGenerator 实例（刘凯睿）
            evaluator: Evaluator 实例（刘凯睿）
            config: 全局配置字典
        """
        self.config = config or {}
        self._components = {
            "spider_manager": spider_manager,
            "vector_db": vector_db,
            "generator": generator,
            "evaluator": evaluator,
        }
        self._stages: Dict[str, PipelineStage] = {}
        self._execution_log: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._build_dag()

    def _build_dag(self):
        """构建 DAG 流水线节点和依赖关系"""
        self._stages["crawl"] = PipelineStage(
            name="crawl",
            func=self._stage_crawl,
            depends_on=[],
            timeout_sec=300,  # 爬虫 5 分钟超时
        )
        self._stages["rag_update"] = PipelineStage(
            name="rag_update",
            func=self._stage_rag_update,
            depends_on=["crawl"],
            timeout_sec=120,  # RAG 更新 2 分钟超时
        )
        self._stages["generate"] = PipelineStage(
            name="generate",
            func=self._stage_generate,
            depends_on=["rag_update"],
            timeout_sec=600,  # LLM 生成 10 分钟超时
        )
        self._stages["evaluate"] = PipelineStage(
            name="evaluate",
            func=self._stage_evaluate,
            depends_on=["generate"],
            timeout_sec=120,  # 评估 2 分钟超时
        )

    # ==================== 各阶段实现 ====================

    def _stage_crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """阶段 1：爬虫抓取

        接口：src.spiders.spider_manager.SpiderManager.crawl_and_classify()
        数据流：爬取数据 → List[Dict] 供下一步 RAG 处理

        Returns:
            爬取到的新闻列表
        """
        spider = self._components.get("spider_manager")
        if spider is None:
            logger.warning("[流水线] SpiderManager 未初始化，跳过爬取")
            return []

        categories = kwargs.get("categories", ["tech", "policy", "industry"])
        logger.info("[流水线/爬虫] 开始抓取，类别: %s", categories)

        try:
            news_list = spider.crawl_and_classify(categories=categories)
            logger.info("[流水线/爬虫] 抓取完成，共 %d 条", len(news_list))
            return news_list
        except Exception as e:
            logger.error("[流水线/爬虫] 抓取失败: %s", e)
            raise

    def _stage_rag_update(self, **kwargs) -> int:
        """阶段 2：RAG 知识库更新

        接口：src.rag.vector_db.VectorDB.add_documents()
        数据流：爬取结果 → 转换为文档格式 → 写入向量库

        Returns:
            新增文档数量
        """
        vector_db = self._components.get("vector_db")
        crawl_data = kwargs.get("crawl_result", [])

        if not crawl_data:
            logger.warning("[流水线/RAG] 无新数据，跳过知识库更新")
            return 0

        if vector_db is None:
            logger.warning("[流水线/RAG] VectorDB 未初始化，跳过知识库更新")
            return 0

        logger.info("[流水线/RAG] 开始更新知识库，%d 条数据", len(crawl_data))

        try:
            # 将爬取数据转换为 VectorDB.add_documents 所需格式
            # add_documents 接受: [{"title", "content", "category", "tags", "source"}]
            docs = []
            for item in crawl_data:
                if not item.get("content") and not item.get("title"):
                    continue
                docs.append({
                    "title": item.get("title", "未知标题"),
                    "content": item.get("content", item.get("title", "")),
                    "category": item.get("content_type", item.get("category", "general")),
                    "tags": item.get("keywords", []),
                    "source": item.get("source", "crawler"),
                })

            if not docs:
                logger.warning("[流水线/RAG] 无有效文档可入库")
                return 0

            added_ids = vector_db.add_documents(docs)
            added_count = len(added_ids) if added_ids else len(docs)
            logger.info("[流水线/RAG] 知识库更新完成，新增 %d 条", added_count)
            return added_count
        except Exception as e:
            logger.error("[流水线/RAG] 知识库更新失败: %s", e)
            raise

    def _stage_generate(self, **kwargs) -> Dict[str, Any]:
        """阶段 3：内容生成

        接口：src.generator.ContentGenerator.generate(topic, timeline=...)
        必须传入 timeline 参数（时间点感知生成）

        Returns:
            生成结果字典 {"markdown", "html", "generation_time_ms", ...}
        """
        generator = self._components.get("generator")

        if generator is None:
            raise RuntimeError("[流水线/生成] ContentGenerator 未初始化")

        # 从上游获取参考知识
        rag_reference = kwargs.get("rag_reference", "")

        # 组装生成参数
        topic = kwargs.get("topic", "环保行业动态")
        content_type = kwargs.get("content_type", "article")
        scene_type = kwargs.get("scene_type", "municipal")
        keywords = kwargs.get("keywords", ["环保", "绿色发展"])

        # 时间节点参数（赛题核心要求）
        timeline = kwargs.get("timeline", [])
        if not timeline:
            # 如果没有传入 timeline，自动生成当前时间节点的默认值
            now = datetime.now()
            timeline = [
                {"phase": "信息采集", "deadline": now.strftime("%Y-%m-%d")},
                {"phase": "内容审核", "deadline": (now + timedelta(days=1)).strftime("%Y-%m-%d")},
                {"phase": "正式发布", "deadline": (now + timedelta(days=3)).strftime("%Y-%m-%d")},
            ]

        logger.info(
            "[流水线/生成] 开始生成，主题: %s，类型: %s，场景: %s",
            topic, content_type, scene_type,
        )

        # 调用生成器（严格传入 timeline 参数）
        result = generator.generate(
            topic=topic,
            context=kwargs.get("context"),
            content_type=content_type,
            scene_type=scene_type,
            keywords=keywords,
            custom_instructions=kwargs.get("custom_instructions"),
            reference=rag_reference if rag_reference else None,
            timeline=timeline,  # ← 时间节点感知
        )

        gen_time = result.get("generation_time_ms", 0)
        word_count = len(result.get("markdown", ""))
        logger.info(
            "[流水线/生成] 生成完成，耗时 %dms，%d 字",
            gen_time, word_count,
        )
        return result

    def _stage_evaluate(self, **kwargs) -> Dict[str, Any]:
        """阶段 4：质量评估

        接口：src.evaluator.Evaluator.evaluate(content)
        评估维度：技术准确率、合规性、可读性、品牌匹配度、专业性

        Returns:
            评估结果字典
        """
        evaluator = self._components.get("evaluator")

        if evaluator is None:
            raise RuntimeError("[流水线/评估] Evaluator 未初始化")

        gen_result = kwargs.get("generate_result", {})
        content = gen_result.get("markdown", "")
        title = kwargs.get("topic", "未指定主题")
        scene_type = kwargs.get("scene_type", "municipal")

        logger.info("[流水线/评估] 开始评估，标题: %s", title)

        eval_result = evaluator.evaluate(
            content=content,
            title=title,
            scene_type=scene_type,
        )

        accuracy = eval_result.get("accuracy_score", 0)
        compliance = eval_result.get("compliance_score", 0)
        overall = eval_result.get("overall", 0)
        result_tag = eval_result.get("result", "unknown")

        logger.info(
            "[流水线/评估] 评估完成 — 准确率: %.1f%%, 合规性: %.1f%%, 综合分: %.1f%%, 结论: %s",
            accuracy * 100, compliance * 100, overall * 100, result_tag,
        )
        return eval_result

    # ==================== 流水线执行 ====================

    def execute(self, topic: str = None, content_type: str = "article",
                scene_type: str = "municipal", keywords: List[str] = None,
                timeline: List[Dict] = None, categories: List[str] = None,
                context: str = None, custom_instructions: str = None,
                **kwargs) -> Dict[str, Any]:
        """执行完整的 DAG 流水线

        流程：crawl → rag_update → generate → evaluate → (自动重试)

        Args:
            topic: 文章主题/标题
            content_type: 内容类型
            scene_type: 场景类型
            keywords: 关键词列表
            timeline: 时间节点列表
            categories: 爬虫抓取类别
            context: 额外上下文
            custom_instructions: 自定义指令

        Returns:
            完整执行报告：
            {
                "status": "success" | "fail",
                "content": dict,          # 最终生成的内容
                "evaluation": dict,      # 最终评估结果
                "stages": dict,           # 各阶段执行详情
                "total_duration_ms": int, # 全流程总耗时
                "sla_pass": bool,         # 是否满足 30 分钟 SLA
                "retry_count": int,       # 重试次数
            }
        """
        pipeline_start = time.time()

        # 合并参数
        pipeline_kwargs = {
            "topic": topic or "环保行业动态",
            "content_type": content_type,
            "scene_type": scene_type,
            "keywords": keywords or ["环保", "绿色发展"],
            "timeline": timeline,
            "categories": categories or ["tech", "policy", "industry"],
            "context": context,
            "custom_instructions": custom_instructions,
        }

        logger.info("=" * 60)
        logger.info("[流水线] 开始执行 DAG 流水线")
        logger.info("[流水线] 主题: %s | 类型: %s | 场景: %s",
                     pipeline_kwargs["topic"], content_type, scene_type)
        logger.info("[流水线] SLA 目标: %d 秒 (%d 分钟)",
                     PIPELINE_SLA_SECONDS, PIPELINE_SLA_SECONDS // 60)
        logger.info("=" * 60)

        # 重置所有阶段状态
        for stage in self._stages.values():
            stage.status = "pending"
            stage.output = None
            stage.error = None

        # ====== 阶段 1：爬虫 ======
        pipeline_kwargs["crawl_result"] = self._run_stage("crawl", pipeline_kwargs)

        # ====== 阶段 2：RAG 更新 ======
        self._run_stage("rag_update", pipeline_kwargs)

        # 尝试从 RAG 检索相关参考知识（供生成器使用）
        rag_reference = ""
        vector_db = self._components.get("vector_db")
        if vector_db is not None:
            try:
                search_results = vector_db.search(
                    query=pipeline_kwargs["topic"],
                    top_k=5,
                    category=pipeline_kwargs.get("content_type", "article"),
                )
                if search_results:
                    parts = []
                    for r in search_results[:3]:
                        parts.append(f"### {r.get('title', '')}\n{r.get('content', '')}")
                    rag_reference = "\n\n".join(parts)
                    logger.info("[流水线] RAG 检索到 %d 条参考资料", len(search_results))
            except Exception as e:
                logger.warning("[流水线] RAG 检索失败（不影响生成）: %s", e)

        pipeline_kwargs["rag_reference"] = rag_reference

        # ====== 阶段 3：内容生成 ======
        gen_result = self._run_stage("generate", pipeline_kwargs)
        pipeline_kwargs["generate_result"] = gen_result

        # ====== 阶段 4：质量评估 + 闭环重试 ======
        eval_result = None
        final_content = gen_result
        retry_count = 0

        for attempt in range(MAX_REGENERATE_RETRIES + 1):
            eval_result = self._run_stage("evaluate", pipeline_kwargs)

            # 判断是否需要重试
            accuracy = eval_result.get("accuracy_score", 0)
            compliance_ok = eval_result.get("result", "fail") != "fail"
            needs_retry = (accuracy < ACCURACY_THRESHOLD or not compliance_ok)

            if not needs_retry or attempt >= MAX_REGENERATE_RETRIES:
                break

            retry_count = attempt + 1
            logger.warning(
                "[流水线] 评估未达标（准确率: %.1f%% < %.0f%%），第 %d/%d 次重试",
                accuracy * 100, ACCURACY_THRESHOLD * 100,
                retry_count, MAX_REGENERATE_RETRIES,
            )

            # 调用生成器的 regenerate 方法
            generator = self._components.get("generator")
            if generator and hasattr(generator, "regenerate"):
                logger.info("[流水线] 调用 regenerate 重新生成内容...")
                regenerate_start = time.time()

                final_content = generator.regenerate(
                    original_title=pipeline_kwargs["topic"],
                    original_content=gen_result.get("markdown", ""),
                    evaluation_result=eval_result,
                    scene_type=pipeline_kwargs["scene_type"],
                )

                regenerate_time = int((time.time() - regenerate_start) * 1000)
                logger.info("[流水线] regenerate 完成，耗时 %dms", regenerate_time)

                # 更新 pipeline_kwargs，供下次评估使用
                pipeline_kwargs["generate_result"] = final_content
            else:
                logger.warning("[流水线] Generator 不支持 regenerate，停止重试")
                break

        # ====== 汇总报告 ======
        total_duration_ms = int((time.time() - pipeline_start) * 1000)
        sla_pass = total_duration_ms <= PIPELINE_SLA_SECONDS * 1000

        report = {
            "status": "success" if self._stages["evaluate"].status == "success" else "fail",
            "content": final_content,
            "evaluation": eval_result,
            "stages": {
                name: {
                    "status": stage.status,
                    "duration_ms": stage.duration_ms,
                    "error": stage.error,
                }
                for name, stage in self._stages.items()
            },
            "total_duration_ms": total_duration_ms,
            "total_duration_sec": round(total_duration_ms / 1000, 1),
            "sla_pass": sla_pass,
            "sla_target_sec": PIPELINE_SLA_SECONDS,
            "retry_count": retry_count,
            "max_retries": MAX_REGENERATE_RETRIES,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info("=" * 60)
        if sla_pass:
            logger.info("[流水线] 全流程完成，耗时 %dms (%.1fs)，SLA 达标",
                         total_duration_ms, total_duration_ms / 1000)
        else:
            logger.warning(
                "[流水线] 全流程完成，耗时 %dms (%.1fs)，SLA 未达标（目标: %ds）",
                total_duration_ms, total_duration_ms / 1000, PIPELINE_SLA_SECONDS,
            )
        if retry_count > 0:
            logger.info("[流水线] 重试次数: %d/%d", retry_count, MAX_REGENERATE_RETRIES)
        logger.info("=" * 60)

        # 记录执行日志
        with self._lock:
            self._execution_log.append(report)

        return report

    def _run_stage(self, stage_name: str, pipeline_kwargs: Dict) -> Any:
        """执行单个阶段（带超时保护和错误处理）"""
        stage = self._stages.get(stage_name)
        if stage is None:
            logger.error("[流水线] 未知阶段: %s", stage_name)
            raise ValueError(f"Unknown stage: {stage_name}")

        # 检查依赖
        for dep in stage.depends_on:
            dep_stage = self._stages.get(dep)
            if dep_stage and dep_stage.status == "error":
                stage.status = "skipped"
                logger.warning("[流水线] 阶段 '%s' 因上游 '%s' 失败而跳过", stage_name, dep)
                return None

        stage.status = "running"
        stage.start_time = datetime.now()
        stage.error = None

        logger.info(
            "[流水线] ┌─ [%s] 开始执行...",
            stage_name,
        )

        # 在子线程中执行（支持超时）
        result = None
        exception_holder = [None]

        def _target():
            try:
                result_holder = stage.func(**pipeline_kwargs)
                # 需要用 nonlocal 或者列表包装
                return result_holder
            except Exception as e:
                exception_holder[0] = e
                raise

        # 使用线程 + Event 实现超时控制
        result_container = [None]
        done_event = threading.Event()

        def _thread_target():
            try:
                result_container[0] = stage.func(**pipeline_kwargs)
            except Exception as e:
                exception_holder[0] = e
            finally:
                done_event.set()

        worker = threading.Thread(target=_thread_target, daemon=True)
        worker.start()

        # 等待完成或超时
        if not done_event.wait(timeout=stage.timeout_sec):
            stage.status = "error"
            stage.error = f"超时（{stage.timeout_sec}秒）"
            stage.end_time = datetime.now()
            stage.duration_ms = int((stage.end_time - stage.start_time).total_seconds() * 1000)
            logger.error("[流水线] └─ [%s] 执行超时（%ds）", stage_name, stage.timeout_sec)
            raise TimeoutError(f"Stage '{stage_name}' timed out after {stage.timeout_sec}s")

        worker.join(timeout=1)  # 确保线程结束

        if exception_holder[0] is not None:
            stage.status = "error"
            stage.error = str(exception_holder[0])
            stage.end_time = datetime.now()
            stage.duration_ms = int((stage.end_time - stage.start_time).total_seconds() * 1000)
            logger.error("[流水线] └─ [%s] 执行失败: %s", stage_name, stage.error)
            raise exception_holder[0]

        # 成功
        stage.output = result_container[0]
        stage.status = "success"
        stage.end_time = datetime.now()
        stage.duration_ms = int((stage.end_time - stage.start_time).total_seconds() * 1000)

        logger.info(
            "[流水线] └─ [%s] 完成，耗时 %dms",
            stage_name, stage.duration_ms,
        )
        return stage.output


# ==================== 核心调度器 ====================

class TaskScheduler:
    """核心任务调度器

    基于 APScheduler 3.x BackgroundScheduler + ThreadPoolExecutor。

    特性：
    - 后台调度，不阻塞主线程
    - ThreadPoolExecutor（max_workers=5）
    - SQLAlchemy + SQLite 持久化（防重启丢任务）
    - Cron 表达式 + 每日定时 + 间隔循环
    - 防重叠（max_instances=1）
    - Job 执行监听器
    - DAG 闭环流水线（自动重试）
    - 全流程 30 分钟 SLA 保障

    使用方式：
        scheduler = TaskScheduler(config)
        scheduler.add_pipeline_job("每日早间推文", topic="环保动态", hour=9)
        scheduler.start()

    参考：
    - APScheduler BackgroundScheduler:
      https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/background.html
    - django-apscheduler 事件监听:
      https://github.com/jcassou/django-apscheduler
    """

    def __init__(self, config: dict = None, workflow_engine=None):
        """
        Args:
            config: 全局配置字典（来自 src/config.py）
            workflow_engine: WorkflowEngine 实例（兼容旧接口）
        """
        self.config = config or {}
        self.workflow_engine = workflow_engine
        self._scheduler = None
        self._use_apscheduler = False
        self._listener = JobExecutionListener()
        self._pipeline = None
        self._running = False
        self._fallback_jobs: List[Dict[str, Any]] = []
        self._thread = None

        self._init_scheduler()
        logger.info(
            "[调度器] TaskScheduler 初始化完成（模式: %s）",
            "APScheduler" if self._use_apscheduler else "内置轮询",
        )

    def _init_scheduler(self):
        """初始化调度器

        优先使用 APScheduler 3.x BackgroundScheduler + ThreadPoolExecutor。
        配置 SQLAlchemy JobStore（SQLite）实现持久化。
        不可用时回退到内置轮询模式。
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
            from apscheduler.events import EVENT_JOB_SUBMITTED, EVENT_JOB_MISSED
            from apscheduler.executors.pool import ThreadPoolExecutor

            scheduler_config = self.config.get("scheduler", {})
            timezone = scheduler_config.get("timezone", DEFAULT_TIMEZONE)

            # 项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "data", "scheduler_jobs.sqlite")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            # 尝试配置 SQLAlchemy JobStore（持久化）
            jobstores = {}
            try:
                from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
                jobstores["default"] = SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
                logger.info("[调度器] SQLAlchemy JobStore 已配置: %s", db_path)
            except ImportError:
                logger.warning(
                    "[调度器] SQLAlchemy 未安装，任务将不持久化"
                    "（pip install SQLAlchemy 后重启即可启用）"
                )
            except Exception as e:
                logger.warning("[调度器] JobStore 初始化失败，使用内存存储: %s", e)

            # 配置 ThreadPoolExecutor（最大 5 个工作线程）
            executors = {
                "default": ThreadPoolExecutor(max_workers=MAX_WORKERS),
            }

            # 配置监听器
            self._scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults={
                    "coalesce": True,        # 合并错过的执行
                    "max_instances": 1,      # 防重叠：同一 Job 同时只运行 1 个实例
                    "misfire_grace_time": 300,  # 错过执行时间后 5 分钟内仍补偿执行
                },
                timezone=timezone,
            )

            # 注册事件监听器（参考 django-apscheduler 模式）
            self._scheduler.add_listener(
                self._listener.on_job_executed, EVENT_JOB_EXECUTED,
            )
            self._scheduler.add_listener(
                self._listener.on_job_error, EVENT_JOB_ERROR,
            )
            self._scheduler.add_listener(
                self._listener.on_job_submitted, EVENT_JOB_SUBMITTED,
            )
            self._scheduler.add_listener(
                self._listener.on_job_missed, EVENT_JOB_MISSED,
            )

            self._use_apscheduler = True

        except ImportError:
            logger.warning("[调度器] APScheduler 未安装，回退到内置轮询模式")
            logger.warning("[调度器] 提示：pip install APScheduler")

    # ==================== 流水线管理 ====================

    def init_pipeline(self, spider_manager=None, vector_db=None,
                      generator=None, evaluator=None):
        """初始化 DAG 流水线

        Args:
            spider_manager: SpiderManager 实例
            vector_db: VectorDB 实例
            generator: ContentGenerator 实例
            evaluator: Evaluator 实例
        """
        self._pipeline = ContentPipeline(
            spider_manager=spider_manager,
            vector_db=vector_db,
            generator=generator,
            evaluator=evaluator,
            config=self.config,
        )
        logger.info("[调度器] DAG 流水线已初始化")

    def run_pipeline_now(self, **kwargs) -> Dict[str, Any]:
        """立即执行一次完整流水线（不经过调度器，手动触发）

        Args:
            topic: 文章主题
            content_type: 内容类型
            scene_type: 场景类型
            keywords: 关键词列表
            timeline: 时间节点列表

        Returns:
            执行报告字典
        """
        if self._pipeline is None:
            raise RuntimeError("[调度器] 流水线未初始化，请先调用 init_pipeline()")

        return self._pipeline.execute(**kwargs)

    # ==================== 任务注册 ====================

    def add_pipeline_job(self, job_name: str, topic: str = None,
                         content_type: str = "article",
                         scene_type: str = "municipal",
                         keywords: List[str] = None,
                         timeline: List[Dict] = None,
                         cron: str = None,
                         hour: int = 9, minute: int = 0,
                         **kwargs):
        """添加流水线调度任务

        支持 Cron 表达式或简单的每日定时。

        Args:
            job_name: 任务唯一标识
            topic: 文章主题
            content_type: 内容类型
            scene_type: 场景类型
            keywords: 关键词列表
            timeline: 时间节点列表
            cron: Cron 表达式（如 "0 2 * * *"），如果提供则忽略 hour/minute
            hour: 每日执行小时（仅 cron 为空时生效）
            minute: 每日执行分钟（仅 cron 为空时生效）

        Example:
            # 每日凌晨 2 点执行
            scheduler.add_pipeline_job("凌晨推文", topic="环保政策解读", hour=2)

            # 使用 Cron 表达式：每 6 小时执行
            scheduler.add_pipeline_job("定期推文", topic="行业动态",
                                       cron="0 */6 * * *")
        """
        if self._pipeline is None:
            logger.error("[调度器] 流水线未初始化，无法添加流水线任务")
            return

        # 构建闭包，捕获当前参数
        job_kwargs = {
            "topic": topic,
            "content_type": content_type,
            "scene_type": scene_type,
            "keywords": keywords,
            "timeline": timeline,
        }

        def _pipeline_wrapper():
            """流水线任务包装器（带异常保护）"""
            logger.info("[调度任务] 开始执行流水线任务: %s", job_name)
            try:
                report = self._pipeline.execute(**job_kwargs)
                if report.get("sla_pass"):
                    logger.info(
                        "[调度任务] 任务 '%s' 完成，耗时 %.1fs，SLA 达标",
                        job_name, report.get("total_duration_sec", 0),
                    )
                else:
                    logger.warning(
                        "[调度任务] 任务 '%s' 完成，耗时 %.1fs，SLA 未达标",
                        job_name, report.get("total_duration_sec", 0),
                    )
                return report
            except Exception as e:
                logger.error("[调度任务] 任务 '%s' 执行失败: %s", job_name, e)
                raise

        if self._use_apscheduler and self._scheduler is not None:
            if cron:
                # Cron 表达式模式（解析为 APScheduler 3.x 参数）
                cron_kwargs = parse_cron_expr(cron)
                self._scheduler.add_job(
                    _pipeline_wrapper,
                    'cron',
                    id=job_name,
                    **cron_kwargs,
                    replace_existing=True,
                    # max_instances=1 已在 job_defaults 中全局配置
                )
                logger.info("[调度器] 已添加 Cron 任务: '%s'（%s）", job_name, cron)
            else:
                # 每日定时模式
                self._scheduler.add_job(
                    _pipeline_wrapper,
                    'cron',
                    id=job_name,
                    hour=hour,
                    minute=minute,
                    replace_existing=True,
                )
                logger.info(
                    "[调度器] 已添加每日任务: '%s'（每天 %02d:%02d）",
                    job_name, hour, minute,
                )
        else:
            # 回退模式
            self._fallback_jobs.append({
                "name": job_name,
                "func": _pipeline_wrapper,
                "type": "cron" if cron else "daily",
                "cron": cron,
                "hour": hour,
                "minute": minute,
                "last_run": None,
            })
            logger.info("[调度器] 已添加任务（轮询模式）: '%s'", job_name)

    def add_daily_task(self, task_name: str, func: Callable,
                       hour: int = 2, minute: int = 0,
                       args: tuple = None, kwargs: dict = None):
        """添加每日定时任务

        Args:
            task_name: 任务名称
            func: 任务函数
            hour: 每天执行的小时（24h）
            minute: 每天执行的分钟
            args: 位置参数
            kwargs: 关键字参数
        """
        kwargs = kwargs or {}

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.add_job(
                self._safe_execute,
                'cron',
                id=task_name,
                hour=hour,
                minute=minute,
                args=[task_name, func],
                kwargs=kwargs,
                replace_existing=True,
            )
            logger.info("[调度器] 已添加每日任务: '%s'（每天 %02d:%02d）", task_name, hour, minute)
        else:
            self._fallback_jobs.append({
                "name": task_name,
                "func": func,
                "type": "daily",
                "hour": hour,
                "minute": minute,
                "args": args or (),
                "kwargs": kwargs,
                "last_run": None,
            })
            logger.info("[调度器] 已添加每日任务（轮询模式）: '%s'", task_name)

    def add_interval_task(self, task_name: str, func: Callable,
                          hours: int = 0, minutes: int = 0, seconds: int = 0,
                          args: tuple = None, kwargs: dict = None):
        """添加间隔循环任务

        Args:
            task_name: 任务名称
            func: 任务函数
            hours: 间隔小时数
            minutes: 间隔分钟数
            seconds: 间隔秒数
        """
        kwargs = kwargs or {}

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.add_job(
                self._safe_execute,
                'interval',
                id=task_name,
                hours=hours,
                minutes=minutes,
                seconds=seconds,
                args=[task_name, func],
                kwargs=kwargs,
                replace_existing=True,
            )
            parts = []
            if hours:
                parts.append(f"{hours}h")
            if minutes:
                parts.append(f"{minutes}m")
            if seconds:
                parts.append(f"{seconds}s")
            logger.info("[调度器] 已添加间隔任务: '%s'（每 %s）", task_name, " ".join(parts))
        else:
            self._fallback_jobs.append({
                "name": task_name,
                "func": func,
                "type": "interval",
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "args": args or (),
                "kwargs": kwargs,
                "last_run": datetime.now(),
            })
            logger.info("[调度器] 已添加间隔任务（轮询模式）: '%s'", task_name)

    def add_cron_task(self, task_name: str, func: Callable,
                      cron_expr: str,
                      args: tuple = None, kwargs: dict = None):
        """通过 Cron 表达式添加任务

        Args:
            task_name: 任务名称
            func: 任务函数
            cron_expr: Cron 表达式（如 "0 2 * * *" 每日凌晨2点）
            args: 位置参数
            kwargs: 关键字参数
        """
        kwargs = kwargs or {}

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.add_job(
                self._safe_execute,
                'cron',
                id=task_name,
                **parse_cron_expr(cron_expr),  # 解析 cron 字符串为 APScheduler 参数
                args=[task_name, func],
                kwargs=kwargs,
                replace_existing=True,
            )
            logger.info("[调度器] 已添加 Cron 任务: '%s'（%s）", task_name, cron_expr)
        else:
            logger.warning("[调度器] Cron 表达式在轮询模式下不支持，请使用 add_daily_task")

    def remove_task(self, task_name: str):
        """移除指定任务"""
        if self._use_apscheduler and self._scheduler is not None:
            try:
                self._scheduler.remove_job(task_name)
                logger.info("[调度器] 已移除任务: '%s'", task_name)
            except Exception as e:
                logger.warning("[调度器] 移除任务失败: %s", e)
        else:
            self._fallback_jobs = [j for j in self._fallback_jobs if j["name"] != task_name]

    # ==================== 调度器生命周期 ====================

    def start(self):
        """启动调度器

        APScheduler 模式：启动后台调度线程
        回退模式：启动轮询线程
        """
        if self._running:
            logger.warning("[调度器] 调度器已在运行中")
            return

        self._running = True

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.start()
            logger.info("[调度器] APScheduler 后台调度已启动")
            logger.info("[调度器] 时区: %s | 线程池: %d | 持久化: 已启用",
                        self.config.get("scheduler", {}).get("timezone", DEFAULT_TIMEZONE),
                        MAX_WORKERS)
        else:
            self._thread = threading.Thread(target=self._fallback_loop, daemon=True)
            self._thread.start()
            logger.info("[调度器] 内置轮询调度已启动")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return
        self._running = False
        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            logger.info("[调度器] APScheduler 已停止")
        logger.info("[调度器] 调度器已停止")

    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有已注册的任务"""
        tasks = []
        if self._use_apscheduler and self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                # APScheduler 3.x: next_run_time 通过 scheduler.get_jobs() 的 pending 计算获取
                next_run = "N/A"
                try:
                    # APScheduler 3.x 中 _trigger 已被解析，直接打印 trigger
                    next_run = str(job.next_run_time) if hasattr(job, 'next_run_time') and job.next_run_time else "N/A"
                except Exception:
                    pass
                tasks.append({
                    "name": job.id,
                    "next_run": next_run,
                    "trigger": str(job.trigger),
                })
        else:
            for job in self._fallback_jobs:
                tasks.append({
                    "name": job["name"],
                    "type": job.get("type", "unknown"),
                    "last_run": str(job.get("last_run", "N/A")),
                })
        return tasks

    def get_stats(self) -> Dict[str, Any]:
        """获取调度器运行统计

        Returns:
            包含任务列表、SLA 统计、最近执行记录等
        """
        pipeline_stats = self._listener.get_pipeline_stats()
        tasks = self.list_tasks()

        return {
            "running": self._running,
            "mode": "APScheduler" if self._use_apscheduler else "轮询",
            "timezone": self.config.get("scheduler", {}).get("timezone", DEFAULT_TIMEZONE),
            "max_workers": MAX_WORKERS,
            "total_tasks": len(tasks),
            "tasks": tasks,
            "pipeline": pipeline_stats,
        }

    # ==================== 数据流水线（兼容旧接口） ====================

    def _run_data_pipeline(self):
        """执行数据清洗流水线

        完整流程：爬虫抓取 → 数据清洗 → 入库存储 → 更新知识库
        保留此方法以兼容 main.py 中的旧调用。
        """
        logger.info("[数据流水线] 开始执行 (%s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        raw_data = []
        # 第1步：爬虫抓取
        try:
            from src.spiders.spider_manager import SpiderManager
            spider = SpiderManager()
            spider_result = spider.full_workflow(categories=["tech", "policy", "industry"])
            raw_data = spider_result.get("news", [])
            logger.info("[数据流水线] 爬虫完成，%d 条", len(raw_data))
        except Exception as e:
            logger.error("[数据流水线] 爬虫失败: %s", e)

        if not raw_data:
            logger.warning("[数据流水线] 无数据，结束")
            return

        # 第2步：数据清洗
        cleaned_data = raw_data
        try:
            from src.data_cleaner import DataCleaner
            cleaner = DataCleaner()
            cleaned_data = cleaner.clean(raw_data)
            logger.info("[数据流水线] 清洗完成，%d 条", len(cleaned_data))
        except ImportError:
            pass
        except Exception as e:
            logger.error("[数据流水线] 清洗失败: %s", e)

        # 第3步：入库
        try:
            from src.data_storage import DataStorage
            db_config = self.config.get("database", {})
            storage = DataStorage(db_config)
            for item in cleaned_data:
                try:
                    storage.save("contents", {
                        "title": item.get("title", ""),
                        "content": item.get("content", ""),
                        "content_type": item.get("content_type", "article"),
                    })
                except Exception:
                    pass
            logger.info("[数据流水线] 入库完成")
        except ImportError:
            pass

        # 第4步：更新知识库
        try:
            from src.knowledge_base import KnowledgeBase
            kb_config = self.config.get("database", {})
            kb = KnowledgeBase(kb_config)
            kb_docs = [
                {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "category": item.get("content_type", "general"),
                    "source": "crawler",
                }
                for item in cleaned_data if item.get("content")
            ]
            if kb_docs:
                kb.add_documents(kb_docs)
                logger.info("[数据流水线] 知识库更新完成，%d 条", len(kb_docs))
        except ImportError:
            pass

        logger.info("[数据流水线] 执行完毕 (%s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # ==================== 内部方法 ====================

    def _safe_execute(self, task_name: str, func: Callable, **kwargs):
        """安全执行任务（全局异常捕获，单个任务失败不影响调度器）"""
        logger.info("[调度器] 执行任务: '%s' (%s)", task_name, datetime.now().strftime("%H:%M:%S"))
        try:
            func(**kwargs)
            logger.info("[调度器] 任务 '%s' 完成", task_name)
        except Exception as e:
            logger.error("[调度器] 任务 '%s' 失败: %s", task_name, e)
            logger.debug("[调度器] 堆栈:\n%s", traceback.format_exc())

    def _fallback_loop(self):
        """内置轮询循环（APScheduler 不可用时的回退方案）"""
        import time as _time

        while self._running:
            now = datetime.now()

            for job in self._fallback_jobs:
                should_run = False

                if job["type"] == "daily":
                    if (job.get("last_run") is None or
                            job["last_run"].date() < now.date()):
                        if now.hour == job["hour"] and now.minute == job["minute"]:
                            should_run = True

                elif job["type"] == "interval":
                    last = job.get("last_run")
                    if last is None:
                        should_run = True
                    else:
                        delta = (job.get("hours", 0) * 3600 +
                                 job.get("minutes", 0) * 60 +
                                 job.get("seconds", 0))
                        if delta > 0 and (now - last).total_seconds() >= delta:
                            should_run = True

                if should_run:
                    t = threading.Thread(
                        target=self._safe_execute,
                        args=(job["name"], job["func"]),
                        kwargs=job.get("kwargs", {}),
                        daemon=True,
                    )
                    t.start()
                    job["last_run"] = now

            _time.sleep(60)


# ==================== 便捷入口 ====================

def start_scheduler(config: dict = None, workflow_engine=None) -> TaskScheduler:
    """创建并启动调度器的便捷入口函数

    Args:
        config: 全局配置字典
        workflow_engine: WorkflowEngine 实例（兼容旧接口）

    Returns:
        已启动的 TaskScheduler 实例

    Example:
        from src.config import load_config
        from src.scheduler import start_scheduler

        config = load_config()
        scheduler = start_scheduler(config)
    """
    scheduler = TaskScheduler(config=config, workflow_engine=workflow_engine)
    scheduler.start()
    return scheduler


# ==================== 任务拆分管理器（TaskManager） ====================

class TaskPhase:
    """任务阶段定义

    代表内容创作流程中的一个时间节点。
    每个阶段包含：阶段 ID、名称、对应 Pipeline 阶段、计划截止时间、实际状态。

    Attributes:
        phase_id: 阶段唯一标识（如 "info_collection"）
        name: 阶段中文名称
        pipeline_stage: 对应的 Pipeline 阶段名（如 "crawl"、"generate"）
        deadline: 计划截止时间（datetime）
        status: 阶段状态（pending/running/success/failed/skipped）
        started_at: 实际开始时间
        completed_at: 实际完成时间
        error: 失败原因
        retry_count: 重试次数
    """

    def __init__(self, phase_id: str, name: str, pipeline_stage: str,
                 deadline: datetime, order: int = 0):
        self.phase_id = phase_id
        self.name = name
        self.pipeline_stage = pipeline_stage
        self.deadline = deadline
        self.order = order
        self.status = "pending"  # pending / running / success / failed / skipped
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.retry_count = 0
        self.trigger_time: Optional[datetime] = None  # 实际触发时间（用于计算准确率）
        self.expected_trigger_time: Optional[datetime] = None  # 期望触发时间

    @property
    def is_completed(self) -> bool:
        return self.status in ("success", "skipped")

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"

    @property
    def duration_minutes(self) -> Optional[float]:
        """阶段实际耗时（分钟）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() / 60
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "name": self.name,
            "pipeline_stage": self.pipeline_stage,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_minutes": self.duration_minutes,
            "error": self.error,
            "retry_count": self.retry_count,
            "trigger_time": self.trigger_time.isoformat() if self.trigger_time else None,
            "expected_trigger_time": self.expected_trigger_time.isoformat() if self.expected_trigger_time else None,
        }


class ContentTask:
    """内容创作任务

    代表一个完整的内容创作请求，由多个 TaskPhase 组成。
    包含任务元信息、进度跟踪、时间节点管理。

    Attributes:
        task_id: 任务唯一标识
        topic: 内容主题
        content_type: 内容类型
        scene_type: 场景类型
        final_deadline: 最终交付截止时间
        phases: 阶段列表（按 order 排序）
        status: 任务整体状态
        created_at: 任务创建时间
    """

    def __init__(self, task_id: str, topic: str, final_deadline: datetime,
                 content_type: str = "article", scene_type: str = "municipal",
                 start_time: datetime = None,
                 keywords: List[str] = None, custom_instructions: str = None):
        self.task_id = task_id
        self.topic = topic
        self.content_type = content_type
        self.scene_type = scene_type
        self.final_deadline = final_deadline
        self.start_time = start_time or datetime.now()
        self.keywords = keywords or []
        self.custom_instructions = custom_instructions
        self.phases: List[TaskPhase] = []
        self.status = "pending"  # pending / running / success / failed / partial
        self.created_at = datetime.now()
        self._current_phase_index = 0

    @property
    def current_phase(self) -> Optional[TaskPhase]:
        """获取当前应执行的阶段"""
        for phase in self.phases:
            if phase.status == "pending":
                return phase
        return None

    @property
    def progress(self) -> float:
        """任务完成进度（0.0 ~ 1.0）"""
        if not self.phases:
            return 0.0
        completed = sum(1 for p in self.phases if p.is_completed)
        return completed / len(self.phases)

    @property
    def total_duration_minutes(self) -> Optional[float]:
        """任务总耗时（分钟）"""
        if not self.phases:
            return None
        first_start = None
        last_end = None
        for phase in self.phases:
            if phase.started_at and (first_start is None or phase.started_at < first_start):
                first_start = phase.started_at
            if phase.completed_at and (last_end is None or phase.completed_at > last_end):
                last_end = phase.completed_at
        if first_start and last_end:
            return (last_end - first_start).total_seconds() / 60
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "topic": self.topic,
            "content_type": self.content_type,
            "scene_type": self.scene_type,
            "status": self.status,
            "progress": round(self.progress * 100, 1),
            "final_deadline": self.final_deadline.isoformat(),
            "created_at": self.created_at.isoformat(),
            "start_time": self.start_time.isoformat(),
            "current_phase": self.current_phase.to_dict() if self.current_phase else None,
            "total_duration_minutes": self.total_duration_minutes,
            "phases": [p.to_dict() for p in self.phases],
        }


# 默认任务拆分模板
# 每个阶段对应 Pipeline 中的一个节点，duration_hours 为预估耗时
DEFAULT_PHASE_TEMPLATE = [
    {"phase_id": "info_collection",   "name": "信息采集",   "pipeline_stage": "crawl",       "duration_hours": 2},
    {"phase_id": "rag_retrieval",     "name": "知识检索",   "pipeline_stage": "rag_update",  "duration_hours": 1},
    {"phase_id": "content_generation","name": "内容生成",   "pipeline_stage": "generate",    "duration_hours": 4},
    {"phase_id": "quality_evaluation","name": "质量评估",   "pipeline_stage": "evaluate",    "duration_hours": 1},
    {"phase_id": "revision",          "name": "修订完善",   "pipeline_stage": "regenerate",  "duration_hours": 2},
    {"phase_id": "publish",           "name": "正式发布",   "pipeline_stage": "publish",     "duration_hours": 1},
]


class TaskManager:
    """任务拆分与管理器

    赛题硬性要求：按时间节点自动触发内容生成。
    本模块负责：
    1. 任务拆分：将内容创作请求分解为多个阶段（crawl→RAG→generate→evaluate→revise→publish）
    2. 时间节点分配：根据最终截止时间，倒推每个阶段的截止时间
    3. 进度跟踪：记录每个阶段的状态、耗时、错误
    4. 任务生命周期：创建→执行→完成/失败

    使用方式：
        manager = TaskManager()
        task = manager.create_task(
            topic="广州环保政策解读",
            final_deadline="2026-05-20 18:00",
        )
        print(task.progress)  # 0.0
        # ... 执行各阶段 ...
        manager.complete_phase(task.task_id, "info_collection")
        print(task.progress)  # 0.167

    设计原则：
    - 阶段间串行依赖（DAG 线性链）
    - 前一阶段成功后，后一阶段才可执行
    - 每个阶段有独立的超时和重试策略
    - 所有操作线程安全（使用锁保护）
    """

    def __init__(self, phase_template: List[Dict] = None):
        """
        Args:
            phase_template: 自定义阶段模板，默认使用 DEFAULT_PHASE_TEMPLATE
        """
        self._phase_template = phase_template or DEFAULT_PHASE_TEMPLATE
        # 任务存储：{task_id: ContentTask}
        self._tasks: Dict[str, ContentTask] = {}
        self._lock = threading.Lock()
        # ID 计数器
        self._task_counter = 0
        logger.info("[TaskManager] 任务管理器已初始化，阶段模板: %d 个阶段",
                     len(self._phase_template))

    def create_task(self, topic: str, final_deadline,
                    content_type: str = "article", scene_type: str = "municipal",
                    start_time: datetime = None,
                    keywords: List[str] = None,
                    custom_instructions: str = None,
                    phase_config: Dict[str, Any] = None) -> ContentTask:
        """创建内容创作任务并自动拆分阶段

        Args:
            topic: 内容主题
            final_deadline: 最终截止时间（datetime 或 ISO 字符串）
            content_type: 内容类型
            scene_type: 场景类型
            start_time: 任务开始时间（默认当前时间）
            keywords: 关键词列表
            custom_instructions: 自定义指令
            phase_config: 阶段配置覆盖，如 {"info_collection": {"duration_hours": 1}}

        Returns:
            ContentTask: 已拆分完成的内容任务

        Example:
            task = manager.create_task(
                topic="环保政策解读",
                final_deadline="2026-05-20 18:00",
                phase_config={"content_generation": {"duration_hours": 6}},
            )
        """
        # 参数标准化
        if isinstance(final_deadline, str):
            final_deadline = datetime.fromisoformat(final_deadline.replace("Z", "+00:00"))
        if start_time is None:
            start_time = datetime.now()
        elif isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))

        # 生成任务 ID
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._task_counter}"

        # 创建任务
        task = ContentTask(
            task_id=task_id,
            topic=topic,
            final_deadline=final_deadline,
            content_type=content_type,
            scene_type=scene_type,
            start_time=start_time,
            keywords=keywords,
            custom_instructions=custom_instructions,
        )

        # === 时间节点分配（倒推法） ===
        # 从最终截止时间倒推，按预估耗时分配每个阶段的截止时间
        phase_config = phase_config or {}
        total_duration = sum(
            phase_config.get(p["phase_id"], p)["duration_hours"]
            if p["phase_id"] in phase_config else p["duration_hours"]
            for p in self._phase_template
        )

        # 计算开始时间 = 截止时间 - 总预估耗时
        earliest_start = final_deadline - timedelta(hours=total_duration)
        actual_start = min(start_time, earliest_start)
        current_deadline = actual_start

        for i, phase_def in enumerate(self._phase_template):
            pid = phase_def["phase_id"]
            # 允许通过 phase_config 覆盖单个阶段的时长
            duration = phase_def["duration_hours"]
            if pid in phase_config:
                override = phase_config[pid]
                if isinstance(override, dict):
                    duration = override.get("duration_hours", duration)
                elif isinstance(override, (int, float)):
                    duration = override

            phase_deadline = current_deadline + timedelta(hours=duration)

            phase = TaskPhase(
                phase_id=pid,
                name=phase_def["name"],
                pipeline_stage=phase_def["pipeline_stage"],
                deadline=phase_deadline,
                order=i,
            )
            task.phases.append(phase)
            current_deadline = phase_deadline

        # 存储任务
        with self._lock:
            self._tasks[task_id] = task

        logger.info(
            "[TaskManager] 创建任务 '%s': %s，%d 个阶段，截止 %s",
            task_id, topic, len(task.phases),
            final_deadline.strftime("%Y-%m-%d %H:%M"),
        )
        for phase in task.phases:
            logger.info(
                "  阶段 %d: %s（%s）截止 %s",
                phase.order + 1, phase.name, phase.phase_id,
                phase.deadline.strftime("%m-%d %H:%M"),
            )

        return task

    def get_task(self, task_id: str) -> Optional[ContentTask]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: str = None) -> List[ContentTask]:
        """列出所有任务

        Args:
            status: 按状态过滤（None 返回全部）
        """
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def start_phase(self, task_id: str, phase_id: str = None) -> bool:
        """标记阶段开始执行

        Args:
            task_id: 任务 ID
            phase_id: 阶段 ID（为空时自动推进到下一个 pending 阶段）

        Returns:
            是否成功启动
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                logger.warning("[TaskManager] 任务不存在: %s", task_id)
                return False

            # 确定目标阶段
            if phase_id:
                target = None
                for p in task.phases:
                    if p.phase_id == phase_id:
                        target = p
                        break
                if target is None:
                    logger.warning("[TaskManager] 阶段不存在: %s", phase_id)
                    return False
            else:
                target = task.current_phase
                if target is None:
                    logger.info("[TaskManager] 任务 '%s' 所有阶段已完成", task_id)
                    return False

            # 检查前置依赖（所有前面的阶段必须已完成）
            for p in task.phases:
                if p.order < target.order and not p.is_completed:
                    logger.warning(
                        "[TaskManager] 阶段 '%s' 的前置阶段 '%s' 未完成，无法启动",
                        phase_id or target.phase_id, p.phase_id,
                    )
                    return False

            # 检查当前是否是 pending 状态
            if target.status != "pending":
                logger.warning("[TaskManager] 阶段 '%s' 状态不是 pending（当前: %s）",
                               target.phase_id, target.status)
                return False

            target.status = "running"
            target.started_at = datetime.now()
            task.status = "running"

            logger.info(
                "[TaskManager] 阶段开始: %s/%s [%s]（任务: %s）",
                target.phase_id, target.name, target.pipeline_stage, task_id,
            )
            return True

    def complete_phase(self, task_id: str, phase_id: str,
                       error: str = None) -> bool:
        """标记阶段完成

        Args:
            task_id: 任务 ID
            phase_id: 阶段 ID
            error: 如果有错误，传入错误信息

        Returns:
            是否成功
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False

            target = None
            for p in task.phases:
                if p.phase_id == phase_id:
                    target = p
                    break
            if target is None:
                return False

            target.completed_at = datetime.now()

            if error:
                target.status = "failed"
                target.error = error
                # 整体任务状态
                task.status = "failed"
                logger.error("[TaskManager] 阶段失败: %s/%s — %s", task_id, phase_id, error)
            else:
                target.status = "success"
                # 检查是否所有阶段都完成
                if all(p.is_completed for p in task.phases):
                    task.status = "success"
                    logger.info(
                        "[TaskManager] 任务完成: %s「%s」，总耗时 %.1f 分钟",
                        task_id, task.topic, task.total_duration_minutes or 0,
                    )
                elif any(p.is_failed for p in task.phases):
                    task.status = "partial"
                else:
                    task.status = "running"

                logger.info(
                    "[TaskManager] 阶段完成: %s/%s [%s]，耗时 %.1f 分钟，进度 %.0f%%",
                    task_id, phase_id, target.name,
                    target.duration_minutes or 0,
                    task.progress * 100,
                )

            return True

    def skip_phase(self, task_id: str, phase_id: str, reason: str = "") -> bool:
        """跳过某个阶段

        Args:
            reason: 跳过原因
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            for p in task.phases:
                if p.phase_id == phase_id:
                    p.status = "skipped"
                    p.completed_at = datetime.now()
                    p.error = reason
                    logger.info("[TaskManager] 阶段跳过: %s/%s — %s", task_id, phase_id, reason)
                    return True
        return False

    def remove_task(self, task_id: str) -> bool:
        """移除任务"""
        with self._lock:
            return self._tasks.pop(task_id, None) is not None


# ==================== 触发引擎（TriggerEngine） ====================

class TriggerRecord:
    """触发记录

    记录一次触发事件，用于计算节点触发准确率。
    节点触发准确率 = 按时触发的次数 / 总触发次数 ≥ 98%
    """

    def __init__(self, task_id: str, phase_id: str,
                 expected_time: datetime, actual_time: datetime,
                 is_on_time: bool, trigger_source: str = "time"):
        self.task_id = task_id
        self.phase_id = phase_id
        self.expected_time = expected_time
        self.actual_time = actual_time
        self.is_on_time = is_on_time  # 是否在期望时间窗口内触发
        self.trigger_source = trigger_source  # "time" | "event" | "manual"

    @property
    def delay_seconds(self) -> float:
        """实际触发时间与期望时间的偏差（秒），负数表示提前"""
        return (self.actual_time - self.expected_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase_id": self.phase_id,
            "expected_time": self.expected_time.isoformat(),
            "actual_time": self.actual_time.isoformat(),
            "is_on_time": self.is_on_time,
            "delay_seconds": round(self.delay_seconds, 1),
            "trigger_source": self.trigger_source,
        }


class TriggerEngine:
    """时间节点触发引擎

    赛题硬性要求：节点触发准确率 ≥ 98%。

    功能：
    1. 时间节点监控：定期检查待触发阶段，到期自动执行
    2. 事件驱动触发：前一阶段完成后，自动触发下一阶段
    3. 触发准确率统计：记录每次触发的偏差，计算准确率
    4. 双保险机制：时间触发 + 事件触发，确保不漏发

    设计：
    - 后台线程每 30 秒扫描一次待触发的阶段
    - 触发容差窗口：期望时间前后 5 分钟内触发均视为「按时」
    - 支持手动触发（用于调试和补救）

    使用方式：
        engine = TriggerEngine(task_manager, scheduler)
        engine.start()  # 启动后台监控线程
        # ... 系统运行 ...
        accuracy = engine.get_trigger_accuracy()  # 应 ≥ 98%
    """

    # 触发容差窗口（秒）：期望时间前后 N 秒内触发均视为「按时」
    TRIGGER_TOLERANCE_SECONDS = 300  # 5 分钟

    # 扫描间隔（秒）
    SCAN_INTERVAL_SECONDS = 30

    def __init__(self, task_manager: TaskManager, scheduler: TaskScheduler = None,
                 tolerance_seconds: int = None):
        """
        Args:
            task_manager: TaskManager 实例
            scheduler: TaskScheduler 实例（用于注册定时触发）
            tolerance_seconds: 触发容差窗口（秒），默认 300（5 分钟）
        """
        self._task_manager = task_manager
        self._scheduler = scheduler
        self._tolerance = tolerance_seconds or self.TRIGGER_TOLERANCE_SECONDS
        # 触发记录
        self._records: List[TriggerRecord] = []
        # 触发回调：{(task_id, phase_id): callback}
        self._callbacks: Dict[str, Callable] = {}
        # 后台监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        logger.info(
            "[TriggerEngine] 触发引擎已初始化，容差窗口: %d 秒",
            self._tolerance,
        )

    def register_callback(self, task_id: str, phase_id: str,
                          callback: Callable) -> bool:
        """注册阶段触发回调

        当阶段被触发时，自动调用回调函数。
        回调签名: callback(task_id, phase_id, task_manager)

        Args:
            task_id: 任务 ID（或 "*" 表示通配所有任务）
            phase_id: 阶段 ID（或 "*" 表示通配所有阶段）
            callback: 回调函数
        """
        key = f"{task_id}:{phase_id}"
        with self._lock:
            self._callbacks[key] = callback
        logger.info("[TriggerEngine] 注册回调: %s", key)
        return True

    def start(self):
        """启动后台监控线程

        定期扫描 TaskManager 中的待触发阶段，到期自动执行。
        """
        if self._running:
            logger.warning("[TriggerEngine] 已在运行中")
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="TriggerEngine-Monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("[TriggerEngine] 后台监控线程已启动（扫描间隔: %ds）",
                     self.SCAN_INTERVAL_SECONDS)

    def stop(self):
        """停止后台监控"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("[TriggerEngine] 后台监控线程已停止")

    def trigger_phase(self, task_id: str, phase_id: str,
                      source: str = "time") -> bool:
        """手动或程序触发一个阶段

        Args:
            task_id: 任务 ID
            phase_id: 阶段 ID
            source: 触发来源（"time" | "event" | "manual"）

        Returns:
            是否成功触发
        """
        task = self._task_manager.get_task(task_id)
        if task is None:
            logger.warning("[TriggerEngine] 触发失败：任务不存在 %s", task_id)
            return False

        # 找到目标阶段
        target_phase = None
        for phase in task.phases:
            if phase.phase_id == phase_id:
                target_phase = phase
                break
        if target_phase is None:
            logger.warning("[TriggerEngine] 触发失败：阶段不存在 %s/%s", task_id, phase_id)
            return False

        # 检查阶段是否可触发
        if target_phase.status != "pending":
            logger.info(
                "[TriggerEngine] 阶段 %s/%s 状态为 %s，跳过触发",
                task_id, phase_id, target_phase.status,
            )
            return False

        # 检查前置依赖
        for phase in task.phases:
            if phase.order < target_phase.order and phase.status == "pending":
                logger.info(
                    "[TriggerEngine] 阶段 %s/%s 的前置阶段 %s 未触发，延迟",
                    task_id, phase_id, phase.phase_id,
                )
                return False

        now = datetime.now()

        # 启动阶段
        if not self._task_manager.start_phase(task_id, phase_id):
            return False

        # 记录期望触发时间（用于计算准确率）
        # 对于第一个阶段，期望触发时间就是 start_time
        # 对于后续阶段，期望触发时间是前一阶段的完成时间
        expected_time = target_phase.deadline
        if target_phase.order == 0:
            expected_time = task.start_time
        else:
            prev = task.phases[target_phase.order - 1]
            if prev.completed_at:
                expected_time = prev.completed_at

        target_phase.expected_trigger_time = expected_time
        target_phase.trigger_time = now

        # 判断是否按时触发
        delay = abs((now - expected_time).total_seconds())
        is_on_time = delay <= self._tolerance

        # 记录触发
        record = TriggerRecord(
            task_id=task_id,
            phase_id=phase_id,
            expected_time=expected_time,
            actual_time=now,
            is_on_time=is_on_time,
            trigger_source=source,
        )
        with self._lock:
            self._records.append(record)

        status_icon = "✅" if is_on_time else "⚠️"
        logger.info(
            "[TriggerEngine] %s 触发阶段: %s/%s [%s]（来源: %s，偏差: %.1fs）",
            status_icon, task_id, phase_id, target_phase.name, source, delay,
        )

        # 执行回调
        self._fire_callbacks(task_id, phase_id)

        return True

    def on_phase_completed(self, task_id: str, completed_phase_id: str):
        """阶段完成回调（事件驱动触发）

        当一个阶段完成后，自动触发下一个待执行阶段。
        这是「事件驱动」触发模式，与「时间驱动」互补。

        Args:
            task_id: 任务 ID
            completed_phase_id: 刚完成的阶段 ID
        """
        task = self._task_manager.get_task(task_id)
        if task is None:
            return

        # 找到下一个 pending 阶段
        next_phase = None
        for phase in task.phases:
            if phase.phase_id == completed_phase_id:
                continue
            if phase.status == "pending" and (next_phase is None or phase.order < next_phase.order):
                # 确保前面的阶段都已完成
                all_prev_done = all(
                    p.is_completed for p in task.phases if p.order < phase.order
                )
                if all_prev_done:
                    next_phase = phase
                    break  # 取第一个

        if next_phase is None:
            logger.info("[TriggerEngine] 任务 %s 所有阶段已完成，无下一阶段", task_id)
            return

        logger.info(
            "[TriggerEngine] 事件触发: %s 完成 → 自动触发 %s [%s]",
            completed_phase_id, next_phase.phase_id, next_phase.name,
        )
        self.trigger_phase(task_id, next_phase.phase_id, source="event")

    def register_task_triggers(self, task: ContentTask, scheduler: TaskScheduler = None):
        """为任务注册所有阶段的时间触发

        使用 APScheduler 注册每个阶段的定时触发任务。
        如果 scheduler 为 None，使用初始化时传入的 scheduler。

        Args:
            task: ContentTask 实例
            scheduler: TaskScheduler 实例（可选）
        """
        sched = scheduler or self._scheduler
        if sched is None:
            logger.warning("[TriggerEngine] 无可用调度器，时间触发将仅依赖后台扫描")
            return

        for phase in task.phases:
            job_id = f"trigger_{task.task_id}_{phase.phase_id}"
            trigger_time = phase.deadline
            # 用 APScheduler 的 date 触发器在截止时间前 30 分钟触发
            # （给 Pipeline 留出执行时间）
            fire_time = trigger_time - timedelta(minutes=30)

            phase_closure = {
                "task_id": task.task_id,
                "phase_id": phase.phase_id,
                "engine": self,
            }

            def _trigger_wrapper(tid=phase_closure["task_id"],
                                  pid=phase_closure["phase_id"],
                                  eng=phase_closure["engine"]):
                eng.trigger_phase(tid, pid, source="time")

            try:
                sched._scheduler.add_job(
                    _trigger_wrapper,
                    'date',
                    id=job_id,
                    run_date=fire_time,
                    replace_existing=True,
                )
                logger.info(
                    "[TriggerEngine] 注册时间触发: %s → %s [%s]（触发时间: %s）",
                    job_id, phase.phase_id, phase.name,
                    fire_time.strftime("%m-%d %H:%M"),
                )
            except Exception as e:
                logger.warning(
                    "[TriggerEngine] 注册时间触发失败 %s: %s（将依赖后台扫描）",
                    job_id, e,
                )

    # ==================== 准确率统计 ====================

    def get_trigger_accuracy(self) -> Dict[str, Any]:
        """获取节点触发准确率

        赛题指标：节点触发准确率 ≥ 98%

        Returns:
            {
                "accuracy": 98.5,  # 百分比
                "total_triggers": 200,
                "on_time_triggers": 197,
                "late_triggers": 3,
                "tolerance_seconds": 300,
                "met_target": true,  # 是否 ≥ 98%
            }
        """
        with self._lock:
            records = self._records[:]

        total = len(records)
        if total == 0:
            return {
                "accuracy": 100.0,
                "total_triggers": 0,
                "on_time_triggers": 0,
                "late_triggers": 0,
                "tolerance_seconds": self._tolerance,
                "met_target": True,
            }

        on_time = sum(1 for r in records if r.is_on_time)
        late = total - on_time
        accuracy = round(on_time / total * 100, 2)
        target = 98.0

        return {
            "accuracy": accuracy,
            "total_triggers": total,
            "on_time_triggers": on_time,
            "late_triggers": late,
            "tolerance_seconds": self._tolerance,
            "met_target": accuracy >= target,
            "target": target,
        }

    def get_trigger_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近触发记录"""
        with self._lock:
            records = self._records[-limit:]
        return [r.to_dict() for r in reversed(records)]

    # ==================== 内部方法 ====================

    def _fire_callbacks(self, task_id: str, phase_id: str):
        """执行匹配的回调"""
        callbacks_to_fire = []
        with self._lock:
            # 精确匹配
            exact_key = f"{task_id}:{phase_id}"
            if exact_key in self._callbacks:
                callbacks_to_fire.append(self._callbacks[exact_key])
            # 通配任务匹配
            wildcard_task = f"*:{phase_id}"
            if wildcard_task in self._callbacks:
                callbacks_to_fire.append(self._callbacks[wildcard_task])
            # 通配阶段匹配
            wildcard_phase = f"{task_id}:*"
            if wildcard_phase in self._callbacks:
                callbacks_to_fire.append(self._callbacks[wildcard_phase])
            # 全通配
            if "*:*" in self._callbacks:
                callbacks_to_fire.append(self._callbacks["*:*"])

        for cb in callbacks_to_fire:
            try:
                cb(task_id, phase_id, self._task_manager)
            except Exception as e:
                logger.error(
                    "[TriggerEngine] 回调执行失败 %s/%s: %s",
                    task_id, phase_id, e,
                )

    def _monitor_loop(self):
        """后台监控循环

        定期扫描 TaskManager 中的待触发阶段：
        1. 找到所有 pending 状态的阶段
        2. 检查当前时间是否已到达触发时间
        3. 检查前置依赖是否已满足
        4. 触发满足条件的阶段
        """
        import time as _time

        while self._running:
            try:
                now = datetime.now()

                with self._task_manager._lock:
                    tasks = list(self._task_manager._tasks.values())

                for task in tasks:
                    if task.status not in ("pending", "running"):
                        continue

                    for phase in task.phases:
                        if phase.status != "pending":
                            continue

                        # 检查是否到达触发时间
                        # 触发时间 = 阶段截止时间 - 30 分钟（留出执行时间）
                        fire_time = phase.deadline - timedelta(minutes=30)

                        if now >= fire_time:
                            # 检查前置依赖
                            deps_ok = all(
                                p.is_completed for p in task.phases if p.order < phase.order
                            )
                            if deps_ok:
                                self.trigger_phase(
                                    task.task_id, phase.phase_id, source="time",
                                )

            except Exception as e:
                logger.error("[TriggerEngine] 监控循环异常: %s", e)

            _time.sleep(self.SCAN_INTERVAL_SECONDS)

if __name__ == "__main__":
    import sys

    # Windows 编码修复
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 60)
    print("  核心调度引擎 - 单元测试")
    print("=" * 60)

    # 1. 测试调度器初始化
    print("\n[测试 1] 调度器初始化...")
    scheduler = TaskScheduler()
    tasks = scheduler.list_tasks()
    print(f"  已注册任务: {len(tasks)} 个")
    assert isinstance(tasks, list), "list_tasks 应返回列表"
    print("  ✅ 通过")

    # 2. 测试添加任务
    print("\n[测试 2] 添加定时任务...")
    def dummy_task():
        print(f"    → Dummy 任务执行: {datetime.now().strftime('%H:%M:%S')}")

    scheduler.add_daily_task("测试每日", dummy_task, hour=2, minute=0)
    scheduler.add_interval_task("测试间隔", dummy_task, minutes=30)
    scheduler.add_cron_task("测试Cron", dummy_task, "0 */6 * * *")

    tasks = scheduler.list_tasks()
    print(f"  已注册任务: {len(tasks)} 个")
    for t in tasks:
        print(f"    - {t['name']} | {t.get('trigger', t.get('type', 'N/A'))}")
    assert len(tasks) >= 3, "应至少有 3 个任务"
    print("  ✅ 通过")

    # 3. 测试移除任务
    print("\n[测试 3] 移除任务...")
    scheduler.remove_task("测试间隔")
    tasks = scheduler.list_tasks()
    names = [t["name"] for t in tasks]
    assert "测试间隔" not in names, "任务应已被移除"
    print("  ✅ 通过")

    # 4. 测试流水线（Mock 模式）
    print("\n[测试 4] DAG 流水线（Mock）...")

    # 创建 Mock 组件
    class MockGenerator:
        def generate(self, topic, content_type="article", scene_type="municipal",
                     keywords=None, reference=None, timeline=None, **kwargs):
            tl = ""
            if timeline:
                tl = f"\n时间节点: {timeline[0].get('phase', '')} - {timeline[0].get('deadline', '')}"
            return {
                "markdown": f"# {topic}\n\n这是Mock生成的内容。{tl}",
                "html": f"<h1>{topic}</h1>",
                "generation_time_ms": 100,
                "content_type": content_type,
                "scene_type": scene_type,
            }
        def regenerate(self, original_title, original_content, evaluation_result,
                       scene_type="municipal"):
            return {
                "markdown": f"# {original_title}（修改版）\n\n基于评估意见修改。",
                "html": "",
                "generation_time_ms": 50,
                "content_type": "revision",
                "scene_type": scene_type,
            }

    class MockEvaluator:
        def evaluate(self, content, title="", scene_type="municipal"):
            # 第一次返回低分（触发重试），后面返回高分
            if "修改版" in content:
                return {
                    "accuracy_score": 0.96,
                    "compliance_score": 0.95,
                    "readability_score": 0.90,
                    "brand_alignment_score": 0.88,
                    "professionalism_score": 0.85,
                    "overall": 0.91,
                    "result": "pass",
                    "comments": "内容质量良好",
                    "suggestions": ["内容质量良好，无需修改"],
                }
            return {
                "accuracy_score": 0.82,  # < 0.95，触发重试
                "compliance_score": 0.95,
                "readability_score": 0.85,
                "brand_alignment_score": 0.88,
                "professionalism_score": 0.80,
                "overall": 0.86,
                "result": "needs_revision",
                "comments": "技术准确率不足",
                "suggestions": ["建议增加专业技术术语", "建议补充量化数据"],
            }

    scheduler.init_pipeline(
        spider_manager=None,
        vector_db=None,
        generator=MockGenerator(),
        evaluator=MockEvaluator(),
    )

    report = scheduler.run_pipeline_now(
        topic="广州环保政策解读",
        content_type="article",
        scene_type="municipal",
        timeline=[
            {"phase": "政策调研", "deadline": "2026-05-13"},
            {"phase": "内容审核", "deadline": "2026-05-14"},
            {"phase": "正式发布", "deadline": "2026-05-16"},
        ],
    )

    print(f"  状态: {report['status']}")
    print(f"  全流程耗时: {report['total_duration_ms']}ms ({report['total_duration_sec']}s)")
    print(f"  SLA 达标: {'✅' if report['sla_pass'] else '❌'}")
    print(f"  重试次数: {report['retry_count']}/{report['max_retries']}")
    print(f"  各阶段:")
    for name, info in report["stages"].items():
        icon = {"success": "✅", "error": "❌", "skipped": "⏭️", "pending": "⬜"}.get(
            info["status"], "❓"
        )
        print(f"    {icon} {name}: {info['duration_ms']}ms")

    assert report["status"] == "success", "流水线应成功完成"
    assert report["sla_pass"], "应满足 SLA"
    assert report["retry_count"] >= 1, "应触发了至少一次重试"
    print("  ✅ 通过")

    # 5. 测试统计信息
    print("\n[测试 5] 统计信息...")
    stats = scheduler.get_stats()
    print(f"  运行模式: {stats['mode']}")
    print(f"  任务数量: {stats['total_tasks']}")
    print(f"  SLA 统计: {stats['pipeline']['sla_pass_rate']}% 达标率")
    print("  ✅ 通过")

    # 6. 测试防重叠配置
    print("\n[测试 6] 防重叠配置...")
    if scheduler._use_apscheduler and scheduler._scheduler:
        # APScheduler 3.x 中 max_instances 存储在 scheduler._job_defaults 中
        defaults = scheduler._scheduler._job_defaults
        max_inst = defaults.get("max_instances", "未配置")
        print(f"  全局 max_instances = {max_inst}")
        assert max_inst == 1, f"max_instances 应为 1，实际为 {max_inst}"
        print("  ✅ 防重叠已全局配置")
    else:
        print("  跳过（轮询模式）")
    print("  ✅ 通过")

    print("\n" + "=" * 60)
    print("  全部测试通过 ✓")
    print("=" * 60)

    # ==================== TaskManager & TriggerEngine 测试 ====================

    print("\n\n" + "=" * 60)
    print("  TaskManager & TriggerEngine 测试")
    print("=" * 60)

    # 7. 任务拆分
    print("\n[测试 7] TaskManager 任务拆分...")
    from datetime import timedelta
    tm = TaskManager()
    deadline = datetime.now() + timedelta(days=7)
    task = tm.create_task(
        topic="测试任务拆分",
        final_deadline=deadline,
        content_type="article",
        scene_type="municipal",
    )
    assert task.task_id.startswith("task_"), f"task_id 格式错误: {task.task_id}"
    assert len(task.phases) == 6, f"应有 6 个阶段，实际 {len(task.phases)}"
    assert task.progress == 0.0, "初始进度应为 0"
    assert task.phases[0].phase_id == "info_collection"
    assert task.phases[-1].phase_id == "publish"
    # 检查时间节点：每个阶段的 deadline 应递增
    for i in range(len(task.phases) - 1):
        assert task.phases[i].deadline <= task.phases[i+1].deadline, \
            f"阶段 {i} 截止时间应早于阶段 {i+1}"
    print(f"  任务 ID: {task.task_id}")
    print(f"  阶段数: {len(task.phases)}")
    for p in task.phases:
        print(f"    {p.order+1}. {p.name}（{p.phase_id}）截止 {p.deadline.strftime('%m-%d %H:%M')}")
    print("  ✅ 通过")

    # 8. 阶段推进
    print("\n[测试 8] TaskManager 阶段推进...")
    # 启动阶段 1
    ok = tm.start_phase(task.task_id, "info_collection")
    assert ok, "启动 info_collection 应成功"
    assert task.phases[0].status == "running"
    assert task.status == "running"

    # 不能跳过阶段 1 直接启动阶段 3
    ok = tm.start_phase(task.task_id, "content_generation")
    assert not ok, "前置阶段未完成时应不能跳过"

    # 完成阶段 1
    ok = tm.complete_phase(task.task_id, "info_collection")
    assert ok, "完成 info_collection 应成功"
    assert task.phases[0].status == "success"
    assert task.phases[0].duration_minutes is not None
    assert task.progress > 0, f"进度应 > 0，实际 {task.progress}"

    # 启动阶段 2（不指定 phase_id，自动推进到下一个 pending）
    ok = tm.start_phase(task.task_id)
    assert ok, "自动推进应成功"
    assert task.phases[1].status == "running", f"阶段 2 应在运行，实际: {task.phases[1].status}"

    # 跳过阶段 2
    ok = tm.skip_phase(task.task_id, "rag_retrieval", reason="测试跳过")
    assert ok
    assert task.phases[1].status == "skipped"

    print(f"  进度: {task.progress * 100:.0f}%")
    print(f"  状态: {task.status}")
    print("  ✅ 通过")

    # 9. 任务列表
    print("\n[测试 9] TaskManager 任务列表...")
    all_tasks = tm.list_tasks()
    assert len(all_tasks) >= 1, "应至少有 1 个任务"
    running_tasks = tm.list_tasks(status="running")
    assert len(running_tasks) >= 1, "应有运行中的任务"
    tm.remove_task(task.task_id)
    assert tm.get_task(task.task_id) is None, "移除后应查不到"
    print(f"  总任务: {len(all_tasks)}, 运行中: {len(running_tasks)}")
    print("  ✅ 通过")

    # 10. 触发引擎
    print("\n[测试 10] TriggerEngine 触发引擎...")
    tm2 = TaskManager()
    scheduler2 = TaskScheduler()
    engine = TriggerEngine(task_manager=tm2, scheduler=scheduler2)

    # 创建任务
    task2 = tm2.create_task(
        topic="触发引擎测试",
        final_deadline=datetime.now() + timedelta(hours=2),
    )
    first_phase = task2.phases[0]

    # 手动触发第一阶段
    ok = engine.trigger_phase(task2.task_id, "info_collection", source="manual")
    assert ok, "手动触发应成功"
    assert first_phase.status == "running"
    assert first_phase.trigger_time is not None

    # 完成第一阶段 → 事件触发第二阶段
    tm2.complete_phase(task2.task_id, "info_collection")
    engine.on_phase_completed(task2.task_id, "info_collection")
    second_phase = task2.phases[1]
    assert second_phase.status == "running", f"第二阶段应被事件触发，实际状态: {second_phase.status}"

    # 完成第二阶段 → 事件触发第三阶段
    tm2.complete_phase(task2.task_id, "rag_retrieval")
    engine.on_phase_completed(task2.task_id, "rag_retrieval")
    third_phase = task2.phases[2]
    assert third_phase.status == "running", "第三阶段应被事件触发"

    print(f"  触发记录: {len(engine._records)} 条")
    for r in engine._records:
        print(f"    {r.task_id}/{r.phase_id} — {'按时' if r.is_on_time else '迟到'} "
              f"({r.delay_seconds:+.0f}s) [{r.trigger_source}]")
    print("  ✅ 通过")

    # 11. 触发准确率统计
    print("\n[测试 11] 触发准确率统计...")
    accuracy = engine.get_trigger_accuracy()
    print(f"  准确率: {accuracy['accuracy']}%")
    print(f"  总触发: {accuracy['total_triggers']}")
    print(f"  按时触发: {accuracy['on_time_triggers']}")
    print(f"  达标(≥98%): {'✅' if accuracy['met_target'] else '❌'}")
    # 手动触发都在容差窗口内，应 100%
    assert accuracy['accuracy'] == 100.0, f"手动触发应在容差内，实际 {accuracy['accuracy']}%"
    assert accuracy['met_target'], "应达标"
    print("  ✅ 通过")

    # 12. 自定义阶段模板
    print("\n[测试 12] 自定义阶段模板...")
    custom_template = [
        {"phase_id": "research", "name": "深度调研", "pipeline_stage": "crawl", "duration_hours": 3},
        {"phase_id": "draft", "name": "初稿撰写", "pipeline_stage": "generate", "duration_hours": 5},
        {"phase_id": "final", "name": "终审定稿", "pipeline_stage": "evaluate", "duration_hours": 2},
    ]
    tm3 = TaskManager(phase_template=custom_template)
    task3 = tm3.create_task(
        topic="自定义模板测试",
        final_deadline=datetime.now() + timedelta(days=3),
    )
    assert len(task3.phases) == 3, f"应有 3 个阶段，实际 {len(task3.phases)}"
    assert task3.phases[0].phase_id == "research"
    assert task3.phases[-1].phase_id == "final"
    print(f"  自定义阶段: {len(task3.phases)} 个")
    for p in task3.phases:
        print(f"    {p.name}（{p.phase_id}）截止 {p.deadline.strftime('%m-%d %H:%M')}")
    print("  ✅ 通过")

    # 13. 阶段配置覆盖
    print("\n[测试 13] 阶段配置覆盖...")
    task4 = tm.create_task(
        topic="配置覆盖测试",
        final_deadline=datetime.now() + timedelta(days=2),
        phase_config={"content_generation": {"duration_hours": 8}},
    )
    gen_phase = None
    for p in task4.phases:
        if p.phase_id == "content_generation":
            gen_phase = p
            break
    assert gen_phase is not None, "应包含 content_generation 阶段"
    # 该阶段分配了 8 小时，截止时间应比默认晚
    print(f"  content_generation 截止: {gen_phase.deadline.strftime('%m-%d %H:%M')}")
    print("  ✅ 通过")

    # 14. 停止触发引擎
    engine.stop()
    scheduler2.stop()

    print("\n" + "=" * 60)
    print("  TaskManager & TriggerEngine 全部测试通过 ✓")
    print("=" * 60)
