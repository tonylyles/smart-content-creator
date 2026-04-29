"""工作流引擎 - 曾睿负责"""


class WorkflowEngine:
    """工作流引擎，协调整个内容创作流水线"""

    def __init__(self, config):
        self.config = config
        self.stages = []

    def register_stage(self, stage):
        """注册工作流阶段"""
        self.stages.append(stage)

    def run(self, task):
        """执行完整工作流"""
        context = {"task": task}
        for stage in self.stages:
            context = stage.execute(context)
        return context
