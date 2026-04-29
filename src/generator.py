"""内容生成引擎 - 刘凯睿负责"""


class ContentGenerator:
    """内容生成引擎"""

    def __init__(self, config, prompt_engine=None):
        self.config = config
        self.prompt_engine = prompt_engine

    def generate(self, topic, context=None):
        """生成内容"""
        prompt = self.prompt_engine.build_prompt(topic, context)
        # 调用LLM生成
        pass

    def generate_batch(self, topics):
        """批量生成"""
        results = []
        for topic in topics:
            result = self.generate(topic)
            results.append(result)
        return results
