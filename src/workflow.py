"""工作流引擎 - 曾睿负责"""
import time


class WorkflowEngine:
    """工作流引擎，协调整个内容创作流水线"""

    def __init__(self, config):
        self.config = config
        self.stages = []
        self._generator = None
        self._retriever = None
        self._evaluator = None

    def _init_components(self):
        """延迟初始化组件"""
        if self._generator is None:
            from src.generator import ContentGenerator
            self._generator = ContentGenerator(self.config)

        if self._retriever is None:
            from src.rag.retriever import RAGRetriever
            self._retriever = RAGRetriever(self.config)

        if self._evaluator is None:
            from src.evaluator import Evaluator
            self._evaluator = Evaluator(self.config)

    def register_stage(self, stage):
        """注册工作流阶段"""
        self.stages.append(stage)

    def run(self, task):
        """执行完整工作流"""
        self._init_components()
        action = task.get("action", "")

        if action == "generate":
            return self._run_generate(task)
        elif action == "search":
            return self._run_search(task)
        elif action == "evaluate":
            return self._run_evaluate(task)
        else:
            # 传统工作流模式
            context = {"task": task}
            for stage in self.stages:
                context = stage.execute(context)
            return context

    def _run_generate(self, task):
        """执行内容生成工作流"""
        start_time = time.time()

        # 1. 检索相关知识
        keywords = task.get("keywords", [])
        reference_knowledge = []
        if keywords:
            query = " ".join(keywords)
            try:
                reference_knowledge = self._retriever.retrieve(query, top_k=3)
            except Exception:
                pass

        # 2. 生成内容
        result = self._generator.generate(
            topic=task.get("title", ""),
            content_type=task.get("content_type", "article"),
            scene_type=task.get("scene_type", "municipal"),
            keywords=keywords,
            reference="\n".join([r.get("content", "") for r in reference_knowledge]) if reference_knowledge else None,
        )

        # 3. 质量评估
        try:
            review = self._evaluator.evaluate(
                content=result.get("markdown", ""),
                title=task.get("title", ""),
                scene_type=task.get("scene_type", "municipal"),
            )
            result["review"] = review
        except Exception as e:
            result["review"] = {"result": "评估跳过", "error": str(e)}

        # 4. 记录耗时
        result["total_time_ms"] = int((time.time() - start_time) * 1000)

        return result

    def _run_search(self, task):
        """执行知识检索工作流"""
        query = task.get("query", "")
        category = task.get("category")
        scene_type = task.get("scene_type")

        results = self._retriever.retrieve(
            query=query,
            top_k=5,
            category=category,
            scene_type=scene_type,
        )

        return {
            "task": task,
            "results": results,
            "count": len(results),
        }

    def _run_evaluate(self, task):
        """执行质量评估工作流"""
        result = self._evaluator.evaluate(
            content=task.get("content", ""),
            title=task.get("title", ""),
            scene_type=task.get("scene_type", "municipal"),
        )
        return result
