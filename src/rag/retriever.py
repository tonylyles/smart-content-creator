"""RAG检索模块 - 刘凯睿负责

功能：
- 语义/关键词混合检索
- 对接知识库(knowledge_base.py)
- 查询预处理与扩展
- 检索结果排序与过滤
- 支持Qdrant向量检索（有Qdrant时）和数据库检索回退
"""
import re
from typing import List, Optional


class RAGRetriever:
    """RAG检索器.

    检索策略：
    1. 有Qdrant + Embedding → 向量语义检索
    2. 有knowledge_base → 关键词检索（回退）
    3. 无外部依赖 → 基础关键词匹配

    Attributes:
        config: 全局配置字典.
        knowledge_base: 知识库实例.
        vector_db: 向量数据库实例.
    """

    def __init__(self, config=None, knowledge_base=None, vector_db=None):
        """初始化RAG检索器.

        Args:
            config: 全局配置字典.
            knowledge_base: 知识库实例.
            vector_db: 向量数据库实例.
        """
        self.config = config or {}
        self.knowledge_base = knowledge_base
        self.vector_db = vector_db
        self._embedding = None

    def retrieve(self, query, top_k=5, category=None, scene_type=None):
        """检索相关知识.

        Args:
            query: 查询文本.
            top_k: 返回数量.
            category: 分类过滤，可选值：技术/政策/案例.
            scene_type: 场景过滤，可选值：municipal/industrial.

        Returns:
            list[dict]: [{"title", "content", "score", "category", "source"}]
        """
        # 1. 优先向量检索
        if self.vector_db:
            try:
                results = self.vector_db.search(query, top_k=top_k, category=category)
                if results:
                    return results
            except Exception:
                pass

        # 2. 知识库检索
        if self.knowledge_base:
            try:
                results = self.knowledge_base.search(query, top_k=top_k)
                if results:
                    return self._rank_results(query, results)
            except Exception:
                pass

        # 3. 基础关键词匹配
        return self._keyword_search(query, top_k, category)

    def _keyword_search(self, query, top_k, category=None):
        """基础关键词搜索（无需外部依赖）.

        Args:
            query: 查询文本.
            top_k: 返回数量.
            category: 分类过滤.

        Returns:
            list[dict]: 检索结果列表.
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        if self.knowledge_base:
            try:
                all_docs = self.knowledge_base.search(" ".join(keywords), top_k=top_k * 2)
                return self._rank_results(query, all_docs)[:top_k]
            except Exception:
                pass

        return []

    def _extract_keywords(self, query):
        """提取查询关键词.

        使用简单规则分词并过滤停用词.

        Args:
            query: 查询文本.

        Returns:
            list[str]: 关键词列表.
        """
        stopwords = {"的", "了", "是", "在", "和", "与", "或", "等", "及",
                     "如何", "怎么", "什么", "哪些", "可以", "能够"}
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]+', query)
        return [w for w in words if w not in stopwords]

    def _rank_results(self, query, results):
        """对检索结果排序.

        结合关键词匹配度和原始得分进行综合排序.

        Args:
            query: 查询文本.
            results: 检索结果列表.

        Returns:
            list[dict]: 排序后的结果列表.
        """
        query_keywords = set(self._extract_keywords(query))

        for r in results:
            content = (r.get("title", "") + r.get("content", "")).lower()
            match_count = sum(1 for kw in query_keywords if kw.lower() in content)
            base_score = r.get("score", 0.5)
            keyword_bonus = min(0.3, match_count * 0.1)
            r["score"] = min(0.99, base_score + keyword_bonus)

        return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

    def expand_query(self, query, scene_type=None):
        """查询扩展 - 添加同义词和相关术语.

        Args:
            query: 原始查询.
            scene_type: 场景类型.

        Returns:
            str: 扩展后的查询.
        """
        expansions = {
            "污水处理": ["水处理", "污水治理", "废水处理"],
            "VOCs": ["挥发性有机物", "有机废气"],
            "废气治理": ["废气处理", "尾气治理"],
            "零排放": ["ZLD", "废水零排放"],
            "固废": ["固体废物", "固废处理"],
            "提标改造": ["提标", "升级改造"],
        }

        expanded = query
        for term, synonyms in expansions.items():
            if term in query:
                expanded += " " + " ".join(synonyms[:2])

        if scene_type == "municipal":
            if "污水" in query and "市政" not in query:
                expanded += " 市政"
        elif scene_type == "industrial":
            if "废水" in query and "工业" not in query:
                expanded += " 工业"

        return expanded
