"""系统主入口 - 曾睿负责"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from workflow import WorkflowEngine
from scheduler import Scheduler
from ui import AppUI


def main():
    """主入口函数"""
    config = load_config()
    engine = WorkflowEngine(config)
    scheduler = Scheduler(engine, config)
    ui = AppUI(engine, config)
    ui.run()


if __name__ == "__main__":
    main()
