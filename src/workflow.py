"""
工作流引擎 - 曾睿负责

功能：
- 协调爬虫、RAG、生成、评估等所有模块的流水线执行
- 支持动态注册功能模块（register_stage）
- 支持阶段间数据转换（register_transform），解决 RAG 结果→生成器 reference 的衔接
- 智能参数传递：inspect.signature 自动过滤不匹配参数
- 内置业务规则引擎（_apply_business_rules），region 自动补充 scene_type
- Mock 数据兜底机制：队友模块返回空/报错时自动填充模拟数据
- 兼容旧接口（run_task），适配凯睿 UI 的 engine.run({"action": "generate"}) 调用方式
"""

from typing import Dict, Any, Callable, Optional, List
import time
import traceback
import inspect


class WorkflowEngine:
    """工作流引擎，协调整个内容创作流水线

    使用方式：
        engine = WorkflowEngine(config)
        engine.register_stage("rag_search", rag_retriever.retrieve)
        engine.register_stage("generate_article", generator.generate)

        # 注册阶段间数据转换（RAG 结果 → 生成器的 reference 参数）
        engine.register_transform("rag_search", engine.rag_to_generator_transform)

        # 链式流水线：RAG 检索 → 内容生成
        result = engine.run_pipeline(["rag_search", "generate_article"], {"topic": "广州环保"})

        # 也可以单阶段调用
        result = engine.run("generate_article", {"topic": "环保", "content_type": "article"})
    """

    def __init__(self, config: dict = None):
        """初始化工作流引擎

        Args:
            config: 全局配置字典（来自 src/config.py 的 GLOBAL_CONFIG）
        """
        self.config = config or {}
        # 注册的功能模块字典：{名称: 函数对象}
        self.stages: Dict[str, Callable] = {}
        # 阶段输出转换函数：{阶段名: 转换函数(original_input, stage_output) -> next_input}
        self._transforms: Dict[str, Callable] = {}
        # 执行日志
        self.execution_log: list = []
        # 缓存上一步输出
        self._last_result: Any = None

        print("[引擎] WorkflowEngine 工作流引擎已初始化")

    # ==================== 核心方法 ====================

    def register_stage(self, name: str, func: Callable) -> bool:
        """注册一个工作流阶段

        Args:
            name: 阶段名称（如 "rag_search"、"generate_article"）
            func: 功能函数对象

        Example:
            engine.register_stage("generate_article", generator.generate)
        """
        if not callable(func):
            print(f"[引擎] ⚠️ 注册失败: '{name}' 不是可调用对象")
            return False
        self.stages[name] = func
        fname = func.__name__ if hasattr(func, '__name__') else 'lambda'
        print(f"[引擎] ✅ 已注册模块: {name} -> {fname}")
        return True

    def register_transform(self, stage_name: str, transform_func: Callable):
        """注册阶段输出转换函数

        当流水线经过该阶段后，自动将阶段输出转换为下一步的输入格式。
        转换函数签名: transform(original_input: dict, stage_output: Any) -> dict

        Args:
            stage_name: 阶段名称
            transform_func: 转换函数

        Example:
            engine.register_transform("rag_search", engine.rag_to_generator_transform)
        """
        self._transforms[stage_name] = transform_func
        print(f"[引擎] ✅ 已注册转换器: {stage_name}")

    def run(self, task_type: str, input_data: Any) -> Dict[str, Any]:
        """执行指定类型的工作流任务

        Args:
            task_type: 任务类型名称
            input_data: 输入数据（字典或任意类型）

        Returns:
            dict: {"status": "success"|"error", "data": ..., "message": ...}
        """
        if task_type not in self.stages:
            return {
                "status": "error",
                "message": f"未找到对应的任务模块: '{task_type}'。"
                           f"已注册: {list(self.stages.keys())}",
            }

        print(f"[引擎] 🚀 开始执行任务: {task_type}")
        start_time = time.time()

        try:
            func = self.stages[task_type]
            result = self._safe_call(func, input_data, stage_name=task_type)

            elapsed_ms = int((time.time() - start_time) * 1000)
            print(f"[引擎] ✅ 任务 '{task_type}' 完成，耗时 {elapsed_ms}ms")

            self._log_execution(task_type, input_data, result, elapsed_ms)
            self._last_result = result

            return {
                "status": "success",
                "data": result,
                "task_type": task_type,
                "elapsed_ms": elapsed_ms,
            }

        except Exception as e:
            error_msg = f"执行出错 [{task_type}]: {str(e)}"
            print(f"[引擎] ❌ {error_msg}")
            traceback.print_exc()
            self._log_execution(task_type, input_data, None, 0, error=error_msg)
            return {"status": "error", "message": error_msg, "task_type": task_type}

    def run_pipeline(self, stages: list, input_data: dict) -> Dict[str, Any]:
        """按顺序执行多个工作流阶段（链式流水线）

        上一步的输出经过转换后，作为下一步的输入。
        每个阶段之间会自动：
        1. 应用业务规则（_apply_business_rules）
        2. 智能传递参数（_safe_call）
        3. 应用输出转换器（register_transform）

        Args:
            stages: 阶段名称列表，如 ["rag_search", "generate_article"]
            input_data: 初始输入数据

        Returns:
            dict: {"status": ..., "data": ..., "stages_completed": ...}
        """
        print(f"[引擎] 🔗 开始链式流水线: {' -> '.join(stages)}")
        current_data = input_data.copy() if isinstance(input_data, dict) else input_data
        intermediate_results = {}

        for i, stage_name in enumerate(stages):
            print(f"[引擎]   ├── [{i+1}/{len(stages)}] {stage_name}")

            # 1. 应用业务规则
            if isinstance(current_data, dict):
                current_data = self._apply_business_rules(current_data)

            # 2. 执行阶段
            result = self.run(stage_name, current_data)

            if result["status"] == "error":
                # Mock 兜底
                mock_data = self._get_mock_data(stage_name, current_data)
                if mock_data is not None:
                    print(f"[引擎]   ├── ⚠️ '{stage_name}' 失败，使用 Mock 数据继续")
                    current_data = mock_data
                    intermediate_results[stage_name] = {"status": "mock", "data": mock_data}
                else:
                    return {
                        "status": "error",
                        "message": f"流水线在 '{stage_name}' 失败",
                        "failed_stage": stage_name,
                        "completed": intermediate_results,
                    }
            else:
                stage_output = result["data"]
                intermediate_results[stage_name] = result

                # 3. 应用阶段间数据转换
                if stage_name in self._transforms:
                    current_data = self._transforms[stage_name](current_data, stage_output)
                    print(f"[引擎]   └── 已应用转换器，准备下一阶段输入")
                else:
                    # 默认行为：用阶段输出替换当前数据
                    current_data = stage_output

        print(f"[引擎] 🔗 流水线全部完成")
        return {"status": "success", "data": current_data, "stages_completed": intermediate_results}

    # ==================== 兼容旧接口（适配凯睿 UI）====================

    def run_task(self, task_data: dict) -> Any:
        """兼容凯睿 UI 的旧接口

        凯睿的 ui.py 调用方式: engine.run({"action": "generate", "title": ...})
        本方法将旧格式转换为新的 stage 调用方式。

        Args:
            task_data: 包含 "action" 字段的字典
                - action="generate": 调用 RAG + 生成器
                - action="search": 调用 RAG 检索
                - action="evaluate": 调用质量评估
        """
        action = task_data.get("action", "")

        if action == "generate":
            # 组装生成器输入
            input_data = {
                "topic": task_data.get("title", ""),
                "content_type": task_data.get("content_type", "article"),
                "scene_type": task_data.get("scene_type", "municipal"),
                "keywords": task_data.get("keywords", []),
            }

            # 自动检索相关知识作为 reference
            title = task_data.get("title", "")
            if title and "rag_search" in self.stages:
                print("[引擎] 📡 自动检索相关知识...")
                rag_result = self.run("rag_search", {"query": title})
                if rag_result["status"] == "success" and rag_result["data"]:
                    input_data["reference"] = self.build_rag_reference(rag_result["data"])

            # 调用生成器
            gen_result = self.run("generate_article", input_data)

            if gen_result["status"] == "success":
                data = gen_result["data"]
                # 如果有评估器，自动评估
                if "evaluate" in self.stages:
                    eval_result = self.run("evaluate", {
                        "content": data.get("markdown", ""),
                        "title": task_data.get("title", ""),
                        "scene_type": task_data.get("scene_type", "municipal"),
                    })
                    if eval_result["status"] == "success":
                        data["review"] = eval_result["data"]
                return data
            return gen_result

        elif action == "search":
            result = self.run("rag_search", {"query": task_data.get("query", "")})
            return result["data"] if result["status"] == "success" else []

        elif action == "evaluate":
            result = self.run("evaluate", {
                "content": task_data.get("content", ""),
                "title": task_data.get("title", ""),
                "scene_type": task_data.get("scene_type", "municipal"),
            })
            return result["data"] if result["status"] == "success" else {}

        else:
            return {"status": "error", "message": f"未知 action: '{action}'"}

    # ==================== 内置转换器 ====================

    @staticmethod
    def rag_to_generator_transform(original_input: dict, rag_results: Any) -> dict:
        """RAG 检索结果 → 生成器输入的转换器

        将 RAG 返回的文档列表转换为生成器需要的 reference 参数。
        保留原始输入的 topic/content_type/scene_type/keywords。

        Args:
            original_input: 流水线原始输入（包含 topic 等）
            rag_results: RAG 检索返回的 list[dict]

        Returns:
            合并后的生成器输入字典
        """
        merged = original_input.copy()
        if isinstance(rag_results, list) and rag_results:
            merged["reference"] = WorkflowEngine.build_rag_reference(rag_results)
        return merged

    @staticmethod
    def generator_to_evaluator_transform(original_input: dict, gen_results: Any) -> dict:
        """生成器输出 → 评估器输入的转换器

        Args:
            original_input: 原始输入
            gen_results: 生成器返回的 dict（含 markdown）

        Returns:
            评估器输入字典
        """
        merged = original_input.copy()
        if isinstance(gen_results, dict):
            merged["content"] = gen_results.get("markdown", "")
        return merged

    @staticmethod
    def build_rag_reference(rag_results: list) -> str:
        """将 RAG 检索结果列表格式化为参考文本

        Args:
            rag_results: [{"title", "content", "score"}, ...]

        Returns:
            格式化的参考文本字符串
        """
        if not rag_results:
            return ""
        parts = []
        for r in rag_results:
            title = r.get("title", "未知标题")
            content = r.get("content", "")
            score = r.get("score", 0)
            parts.append(f"### {title}\n{content}\n(相关度: {score:.0%})")
        return "\n\n".join(parts)

    # ==================== 内部方法 ====================

    def _safe_call(self, func: Callable, input_data: Any, stage_name: str = "") -> Any:
        """安全调用函数，智能匹配参数"""
        if isinstance(input_data, dict):
            try:
                sig = inspect.signature(func)
                func_params = set(sig.parameters.keys())
                # 只传入函数签名中存在的参数
                filtered = {k: v for k, v in input_data.items() if k in func_params}
                if filtered:
                    result = func(**filtered)
                else:
                    result = func(input_data)
            except (TypeError, ImportError) as e:
                print(f"[引擎]   └── 参数传递失败 ({e})，回退为直接传入")
                result = func(input_data)
        else:
            result = func(input_data)

        # 空值检测 + Mock 兜底
        if self._is_empty_result(result):
            print(f"[引擎]   └── ⚠️ '{stage_name}' 返回空值，使用 Mock 数据")
            mock_data = self._get_mock_data(stage_name, input_data)
            return mock_data if mock_data is not None else result
        return result

    def _apply_business_rules(self, data: dict) -> dict:
        """应用业务规则，自动补充缺失参数"""
        result = data.copy()
        data_schema = self.config.get("data_schema", {})
        region_map = data_schema.get("region_to_scene", {})
        default_region = data_schema.get("default_region", "广州")

        # region → scene_type
        region = result.get("region") or result.get("location") or default_region
        if region in region_map:
            if "scene_type" not in result:
                result["scene_type"] = region_map[region]
                print(f"[业务规则] region='{region}' → scene_type='{region_map[region]}'")
        elif "scene_type" not in result:
            result["scene_type"] = "municipal"

        # 默认 content_type
        if "content_type" not in result:
            result["content_type"] = "article"

        # 默认 keywords
        if "keywords" not in result and "topic" in result:
            result["keywords"] = ["环保", "绿色发展"]

        # topic → query 映射（RAG 需要 query）
        if "query" not in result and "topic" in result:
            result["query"] = result["topic"]

        return result

    def _is_empty_result(self, result: Any) -> bool:
        if result is None:
            return True
        if isinstance(result, (list, dict)) and len(result) == 0:
            return True
        return False

    def _get_mock_data(self, stage_name: str, input_data: Any) -> Any:
        """根据阶段名称生成 Mock 模拟数据"""
        topic = ""
        if isinstance(input_data, dict):
            topic = input_data.get("topic", input_data.get("query", ""))

        if "rag_search" in stage_name or "retrieve" in stage_name:
            return [
                {"title": f"【Mock】{topic or '环保'}相关政策解读",
                 "content": f"模拟的 RAG 检索结果，与'{topic or '环保'}'相关。",
                 "score": 0.85, "category": "政策", "source": "mock"},
                {"title": f"【Mock】{topic or '环保'}行业技术趋势",
                 "content": f"模拟的技术趋势检索结果。",
                 "score": 0.72, "category": "技术", "source": "mock"},
            ]

        if "generate" in stage_name:
            return {
                "markdown": f"# 【Mock】{topic or '未指定主题'}\n\n模拟生成内容。",
                "html": f"<h1>Mock: {topic}</h1>",
                "generation_time_ms": 0,
                "content_type": "article",
                "scene_type": "municipal",
            }

        if "evaluate" in stage_name:
            return {
                "accuracy_score": 0.7, "compliance_score": 0.8,
                "readability_score": 0.75, "brand_alignment_score": 0.7,
                "overall": 0.74, "result": "needs_revision",
                "comments": "【Mock】评估模块尚未就绪",
            }

        return {"status": "mock", "message": f"Mock for '{stage_name}'"}

    def _log_execution(self, stage_name, input_data, output, elapsed_ms, error=None):
        self.execution_log.append({
            "stage": stage_name,
            "input": str(input_data)[:200] if input_data else None,
            "output": str(output)[:200] if output else None,
            "elapsed_ms": elapsed_ms,
            "error": error,
        })

    def get_execution_log(self) -> list:
        return self.execution_log

    def list_stages(self) -> list:
        return list(self.stages.keys())

    def clear_log(self):
        self.execution_log.clear()


# ==================== 单元测试 ====================
if __name__ == "__main__":
    engine = WorkflowEngine()
    def dummy_rag(query, top_k=3):
        return [{"title": "测试", "content": "测试内容", "score": 0.9}]
    def dummy_gen(topic, content_type="article", reference=None):
        ref = reference[:50] + "..." if reference else "无参考"
        return {"markdown": f"# {topic}\n参考: {ref}", "generation_time_ms": 0}

    engine.register_stage("rag_search", dummy_rag)
    engine.register_stage("generate_article", dummy_gen)
    engine.register_transform("rag_search", WorkflowEngine.rag_to_generator_transform)

    result = engine.run_pipeline(["rag_search", "generate_article"], {"topic": "广州环保"})
    print(f"Pipeline: {result['status']}")
    print(f"Output: {result['data']['markdown'][:100]}")

    print("\n[引擎] 工作流引擎自测通过 ✓")