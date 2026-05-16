"""启动 Gradio Web UI

用法：
  python run_ui.py              # 默认 http://127.0.0.1:7860
  python run_ui.py --port 8080  # 指定端口
  python run_ui.py --share      # 创建公网链接（演示用）
"""
import sys
import os
import argparse

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="smart-content-creator Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=7860, help="监听端口")
    parser.add_argument("--share", action="store_true", help="创建公网链接")
    args = parser.parse_args()

    print("正在初始化系统...")
    from src.main import init_system
    engine, scheduler, components = init_system()

    print("正在启动 Web UI...")
    from src.ui import AppUI
    ui = AppUI(engine, components.get("config", {}), scheduler)
    ui.run(host=args.host, port=args.port, share=args.share)


if __name__ == "__main__":
    main()
