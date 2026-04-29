"""提示词引擎 - 刘凯睿负责"""


class PromptEngine:
    """提示词管理与模板引擎"""

    def __init__(self):
        self.templates = {}

    def register_template(self, name, template):
        """注册提示词模板"""
        self.templates[name] = template

    def build_prompt(self, topic, context=None):
        """构建提示词"""
        template = self.templates.get("default", "{topic}")
        return template.format(topic=topic, context=context)
