"""定时任务调度 - 曾睿负责"""
import schedule
import time
import threading
from datetime import datetime


class Scheduler:
    """定时任务调度器"""

    def __init__(self, workflow_engine, config):
        self.engine = workflow_engine
        self.config = config
        self._running = False
        self._thread = None

    def setup_jobs(self):
        """配置定时任务"""
        pass

    def start(self):
        """启动调度器"""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止调度器"""
        self._running = False

    def _run_loop(self):
        """调度循环"""
        while self._running:
            schedule.run_pending()
            time.sleep(1)
