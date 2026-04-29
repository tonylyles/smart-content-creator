"""用户界面 - 刘凯睿负责"""


class AppUI:
    """用户界面"""

    def __init__(self, workflow_engine, config):
        self.engine = workflow_engine
        self.config = config

    def run(self):
        """启动界面"""
        print("Smart Content Creator")
        print("=" * 40)
        print("智能内容创作平台已启动")

    def show_status(self):
        """显示系统状态"""
        pass

    def show_logs(self):
        """显示日志"""
        pass
