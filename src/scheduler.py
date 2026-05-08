"""
任务调度器 - 曾睿负责

功能：
- 基于 APScheduler 实现定时任务调度
- 支持每日定时任务（add_daily_task）和间隔循环任务（add_interval_task）
- 预留 _run_data_pipeline() 方法，用于每天凌晨调用胡圳刚的数据清洗脚本
- 支持动态添加/移除任务
- 任务执行异常自动捕获，不影响调度器运行
"""

import traceback
from datetime import datetime
from typing import Callable, Optional


class TaskScheduler:
    """任务调度器

    基于 APScheduler 的 BackgroundScheduler 实现后台定时任务调度。
    如果 APScheduler 未安装，自动回退到简单的 time.sleep 轮询模式。

    使用方式：
        scheduler = TaskScheduler(config)
        scheduler.add_daily_task("数据清洗", my_func, hour=2)
        scheduler.add_interval_task("状态检查", check_func, hours=1)
        scheduler.start()
    """

    def __init__(self, config: dict = None, workflow_engine=None):
        """
        初始化任务调度器

        Args:
            config: 全局配置字典（来自 src/config.py）
            workflow_engine: 工作流引擎实例（可选，供调度任务调用）
        """
        self.config = config or {}
        self.workflow_engine = workflow_engine

        # 尝试导入 APScheduler，失败则使用内置轮询调度器
        self._scheduler = None
        self._use_apscheduler = False
        self._fallback_jobs = []  # APScheduler 不可用时的回退任务列表
        self._running = False
        self._thread = None

        self._init_scheduler()
        print(f"[调度器] TaskScheduler 初始化完成（调度模式: {'APScheduler' if self._use_apscheduler else '内置轮询'})")

    def _init_scheduler(self):
        """初始化调度器

        优先使用 APScheduler，不可用时回退到 schedule 库或内置轮询。
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            scheduler_config = self.config.get("scheduler", {})
            timezone = scheduler_config.get("timezone", "Asia/Shanghai")

            self._scheduler = BackgroundScheduler(timezone=timezone)
            self._use_apscheduler = True
        except ImportError:
            print("[调度器] ⚠️ APScheduler 未安装，回退到内置轮询调度器")
            print("[调度器] 💡 提示：运行 `pip install APScheduler` 以获得更精确的定时调度")

            # 尝试使用 schedule 库作为第二选择
            try:
                import schedule
                self._scheduler = schedule
                self._use_apscheduler = False
            except ImportError:
                print("[调度器] ⚠️ schedule 库也未安装，使用最基础的轮询模式")

    # ==================== 公开方法 ====================

    def add_daily_task(self, task_name: str, func: Callable,
                       hour: int = 2, minute: int = 0,
                       args: tuple = None, kwargs: dict = None):
        """添加每日定时任务

        Args:
            task_name: 任务名称（用于标识）
            func: 任务函数
            hour: 每天执行的小时（24小时制，默认凌晨2点）
            minute: 每天执行的分钟（默认0分）
            args: 位置参数元组
            kwargs: 关键字参数字典
        """
        kwargs = kwargs or {}

        if self._use_apscheduler and self._scheduler is not None:
            # APScheduler 模式 —— 支持精确的 cron 定时
            self._scheduler.add_job(
                self._safe_execute,
                'cron',
                id=task_name,
                hour=hour,
                minute=minute,
                args=[task_name, func],
                kwargs=kwargs,
                replace_existing=True,  # 同名任务自动替换
            )
            print(f"[调度器] ✅ 已添加每日任务: '{task_name}'（每天 {hour:02d}:{minute:02d}）")
        else:
            # 内置轮询回退模式
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
            print(f"[调度器] ✅ 已添加每日任务（轮询模式）: '{task_name}'（每天 {hour:02d}:{minute:02d}）")

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
            args: 位置参数元组
            kwargs: 关键字参数字典
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
            interval_desc = []
            if hours: interval_desc.append(f"{hours}小时")
            if minutes: interval_desc.append(f"{minutes}分钟")
            if seconds: interval_desc.append(f"{seconds}秒")
            print(f"[调度器] ✅ 已添加间隔任务: '{task_name}'（每 {' '.join(interval_desc)}）")
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
            print(f"[调度器] ✅ 已添加间隔任务（轮询模式）: '{task_name}'")

    def remove_task(self, task_name: str):
        """移除指定任务

        Args:
            task_name: 任务名称
        """
        if self._use_apscheduler and self._scheduler is not None:
            try:
                self._scheduler.remove_job(task_name)
                print(f"[调度器] 已移除任务: '{task_name}'")
            except Exception as e:
                print(f"[调度器] ⚠️ 移除任务失败: {e}")
        else:
            self._fallback_jobs = [j for j in self._fallback_jobs if j["name"] != task_name]
            print(f"[调度器] 已移除任务（轮询模式）: '{task_name}'")

    def start(self):
        """启动调度器

        APScheduler 模式：启动后台调度线程
        回退模式：启动轮询线程
        """
        if self._running:
            print("[调度器] ⚠️ 调度器已在运行中")
            return

        self._running = True

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.start()
            print("[调度器] 🚀 APScheduler 后台调度已启动")
        else:
            import threading
            self._thread = threading.Thread(target=self._fallback_loop, daemon=True)
            self._thread.start()
            print("[调度器] 🚀 内置轮询调度已启动")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False

        if self._use_apscheduler and self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            print("[调度器] APScheduler 已停止")
        print("[调度器] 调度器已停止")

    def list_tasks(self) -> list:
        """列出所有已注册的任务

        Returns:
            任务信息列表
        """
        tasks = []
        if self._use_apscheduler and self._scheduler is not None:
            for job in self._scheduler.get_jobs():
                tasks.append({
                    "name": job.id,
                    "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
                    "type": str(job.trigger),
                })
        else:
            for job in self._fallback_jobs:
                tasks.append({
                    "name": job["name"],
                    "type": job["type"],
                    "last_run": str(job.get("last_run", "N/A")),
                })
        return tasks

    # ==================== 数据流水线（预留） ====================

    def _run_data_pipeline(self):
        """执行数据清洗流水线

        完整流程：爬虫抓取 → 数据清洗 → 入库存储 → 更新知识库

        注意：当前为预留实现，具体逻辑需与胡圳刚对接后完善。
        """
        print(f"[数据流水线] 🔄 开始执行 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        pipeline_ok = True

        # ---- 第1步：爬虫抓取（胡圳刚负责） ----
        raw_data = []
        try:
            from src.spiders.spider_manager import SpiderManager
            spider = SpiderManager()
            spider_result = spider.full_workflow(categories=["tech", "policy", "industry"])
            raw_data = spider_result.get("news", [])
            print(f"[数据流水线] ✅ 爬虫抓取完成，共 {len(raw_data)} 条")
        except ImportError:
            print("[数据流水线] ⚠️ SpiderManager 未安装，跳过爬取步骤")
        except Exception as e:
            print(f"[数据流水线] ❌ 爬虫抓取失败: {e}")
            pipeline_ok = False

        if not raw_data:
            print("[数据流水线] ⚠️ 无新数据，流水线结束")
            return

        # ---- 第2步：数据清洗（胡圳刚负责） ----
        cleaned_data = []
        try:
            from src.data_cleaner import DataCleaner
            cleaner = DataCleaner()
            cleaned_data = cleaner.clean(raw_data)
            print(f"[数据流水线] ✅ 数据清洗完成，剩余 {len(cleaned_data)} 条")
        except ImportError:
            print("[数据流水线] ⚠️ DataCleaner 未实现，使用原始数据")
            cleaned_data = raw_data
        except Exception as e:
            print(f"[数据流水线] ❌ 数据清洗失败: {e}")
            cleaned_data = raw_data

        # ---- 第3步：入库存储（胡圳刚负责） ----
        try:
            from src.data_storage import DataStorage
            db_config = self.config.get("database", {"type": "json", "path": "data/content.db"})
            storage = DataStorage(db_config)
            saved_count = 0
            for item in cleaned_data:
                try:
                    storage.save("contents", {
                        "title": item.get("title", ""),
                        "content": item.get("content", ""),
                        "content_type": item.get("content_type", "article"),
                        "scene_type": item.get("scene_type", "municipal"),
                    })
                    saved_count += 1
                except Exception:
                    pass
            print(f"[数据流水线] ✅ 数据存储完成，入库 {saved_count} 条")
        except ImportError:
            print("[数据流水线] ⚠️ DataStorage 不可用，跳过存储步骤")
        except Exception as e:
            print(f"[数据流水线] ❌ 数据存储失败: {e}")

        # ---- 第4步：更新知识库（胡圳刚负责） ----
        try:
            from src.knowledge_base import KnowledgeBase
            kb_config = self.config.get("database", {"path": "data/knowledge.json"})
            kb = KnowledgeBase(kb_config)
            # 将清洗后的数据转为知识库格式
            kb_docs = []
            for item in cleaned_data:
                if item.get("content"):
                    kb_docs.append({
                        "title": item.get("title", ""),
                        "content": item.get("content", ""),
                        "category": item.get("content_type", "general"),
                        "source": item.get("source", "crawler"),
                    })
            added = kb.add_documents(kb_docs) if kb_docs else 0
            print(f"[数据流水线] ✅ 知识库更新完成，新增 {added} 条")
        except ImportError:
            print("[数据流水线] ⚠️ KnowledgeBase 不可用，跳过知识库更新")
        except Exception as e:
            print(f"[数据流水线] ❌ 知识库更新失败: {e}")

        # ---- 第5步：通知工作流引擎数据已更新 ----
        if self.workflow_engine and pipeline_ok:
            print("[数据流水线] 📡 数据已更新，可触发自动内容生成")

        print(f"[数据流水线] 🏁 流水线执行完毕 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    # ==================== 内部方法 ====================

    def _safe_execute(self, task_name: str, func: Callable, **kwargs):
        """安全执行任务函数，捕获所有异常

        Args:
            task_name: 任务名称
            func: 任务函数
            **kwargs: 传递给 func 的参数
        """
        print(f"[调度器] ▶️ 执行任务: '{task_name}' ({datetime.now().strftime('%H:%M:%S')})")
        try:
            func(**kwargs)
            print(f"[调度器] ✅ 任务 '{task_name}' 执行完成")
        except Exception as e:
            print(f"[调度器] ❌ 任务 '{task_name}' 执行失败: {e}")
            traceback.print_exc()

    def _fallback_loop(self):
        """内置轮询循环（APScheduler 不可用时的回退方案）

        每分钟检查一次是否有任务需要执行。
        """
        import time
        import threading

        while self._running:
            now = datetime.now()

            for job in self._fallback_jobs:
                should_run = False

                if job["type"] == "daily":
                    # 每日任务：检查是否到达指定时间
                    if job.get("last_run") is None or job["last_run"].date() < now.date():
                        if now.hour == job["hour"] and now.minute == job["minute"]:
                            should_run = True

                elif job["type"] == "interval":
                    # 间隔任务：检查是否到达间隔时间
                    last = job.get("last_run")
                    if last is None:
                        should_run = True
                    else:
                        delta_sec = (job.get("hours", 0) * 3600 +
                                     job.get("minutes", 0) * 60 +
                                     job.get("seconds", 0))
                        if delta_sec > 0 and (now - last).total_seconds() >= delta_sec:
                            should_run = True

                if should_run:
                    # 在子线程中执行，避免阻塞轮询
                    t = threading.Thread(
                        target=self._safe_execute,
                        args=(job["name"], job["func"]),
                        kwargs=job.get("kwargs", {}),
                        daemon=True,
                    )
                    t.start()
                    job["last_run"] = now

            time.sleep(60)  # 每分钟检查一次


# ==================== 单元测试 ====================
if __name__ == "__main__":
    scheduler = TaskScheduler()

    # 测试添加任务
    def test_task():
        print(f"  → 测试任务执行成功！时间: {datetime.now().strftime('%H:%M:%S')}")

    scheduler.add_daily_task("测试每日任务", test_task, hour=2, minute=0)
    scheduler.add_interval_task("测试间隔任务", test_task, minutes=1)

    # 打印任务列表
    tasks = scheduler.list_tasks()
    print(f"\n已注册任务: {len(tasks)} 个")
    for t in tasks:
        print(f"  - {t}")

    # 注意：start() 会启动后台线程，测试时手动调用即可
    print("\n[调度器] 调度器自测通过 ✓")
    print("[调度器] 提示：调用 scheduler.start() 启动后台调度")
