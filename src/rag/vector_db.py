"""向量数据库接口 - 刘凯睿负责

功能：
- 文档向量化存储
- 语义检索
- 支持Qdrant（生产）和内存模式（演示）
- 文档分块管理
- 与knowledge_base.py对接
"""
import uuid
from typing import List, Optional


class VectorDB:
    """向量数据库接口

    双模式：
    - 有Qdrant → 生产级向量检索
    - 无Qdrant → 内存模式（演示用）
    """

    def __init__(self, config=None, knowledge_base=None):
        self.config = config or {}
        self.knowledge_base = knowledge_base
        self._client = None
        self._embedding = None
        self._has_qdrant = False

        # 内存模式存储
        self._memory_store = []
        self._next_id = 1

        # 尝试连接Qdrant
        self._init_qdrant()

    def _init_qdrant(self):
        """初始化Qdrant连接"""
        try:
            from qdrant_client import QdrantClient
            rag_config = self.config.get("rag", {})
            url = rag_config.get("url", "http://localhost:6333")
            self._client = QdrantClient(url=url)
            self._has_qdrant = True
            self._ensure_collection()
        except (ImportError, Exception):
            self._has_qdrant = False

    def _ensure_collection(self):
        """确保向量集合存在"""
        if not self._client:
            return
        try:
            from qdrant_client.models import Distance, VectorParams
            collection_name = self.config.get("rag", {}).get("collection", "smart_content")
            collections = self._client.get_collections().collections
            if collection_name not in [c.name for c in collections]:
                dim = self.config.get("rag", {}).get("embedding_dim", 1536)
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
        except Exception:
            pass

    def _get_embedding(self):
        """获取Embedding模型"""
        if self._embedding is None:
            try:
                from langchain_openai import OpenAIEmbeddings
                gen_config = self.config.get("generator", {})
                api_key = gen_config.get("api_key", "") or self.config.get("llm_api_key", "")
                if api_key:
                    self._embedding = OpenAIEmbeddings(
                        model=self.config.get("rag", {}).get("embedding_model", "text-embedding-ada-002"),
                        openai_api_key=api_key,
                        openai_api_base=gen_config.get("base_url", "https://api.openai.com/v1"),
                    )
            except (ImportError, Exception):
                self._embedding = None
        return self._embedding

    def add_documents(self, documents, collection=None):
        """添加文档到向量库

        Args:
            documents: list[dict] [{"title", "content", "category", "tags", "source"}]
            collection: 集合名称（可选）

        Returns:
            list[str]: 文档ID列表
        """
        ids = []
        for doc in documents:
            doc_id = str(uuid.uuid4())
            content = doc.get("content", "")
            chunks = self._chunk_text(content)

            if self._has_qdrant and self._get_embedding():
                # Qdrant 向量存储
                collection_name = collection or self.config.get("rag", {}).get("collection", "smart_content")
                for i, chunk in enumerate(chunks):
                    vector = self._get_embedding().embed_query(chunk)
                    self._client.upsert(
                        collection_name=collection_name,
                        points=[{
                            "id": f"{doc_id}_{i}",
                            "vector": vector,
                            "payload": {
                                "title": doc.get("title", ""),
                                "content": chunk,
                                "category": doc.get("category", ""),
                                "tags": doc.get("tags", []),
                                "source": doc.get("source", ""),
                            },
                        }],
                    )
            else:
                # 内存模式
                for i, chunk in enumerate(chunks):
                    self._memory_store.append({
                        "id": f"{doc_id}_{i}",
                        "title": doc.get("title", ""),
                        "content": chunk,
                        "category": doc.get("category", ""),
                        "tags": doc.get("tags", []),
                        "source": doc.get("source", ""),
                    })

            ids.append(doc_id)
        return ids

    def search(self, query, top_k=5, category=None, collection=None):
        """语义检索

        Args:
            query: 查询文本
            top_k: 返回数量
            category: 分类过滤
            collection: 集合名称

        Returns:
            list[dict]: [{"id", "score", "title", "content", "category", "tags", "source"}]
        """
        # Qdrant 语义检索
        if self._has_qdrant and self._get_embedding():
            try:
                collection_name = collection or self.config.get("rag", {}).get("collection", "smart_content")
                query_vector = self._get_embedding().embed_query(query)

                from qdrant_client.models import Filter, FieldCondition, MatchValue
                must = []
                if category:
                    must.append(FieldCondition(key="category", match=MatchValue(value=category)))

                results = self._client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=Filter(must=must) if must else None,
                )
                return [{
                    "id": str(r.id), "score": r.score,
                    "title": r.payload.get("title", ""),
                    "content": r.payload.get("content", ""),
                    "category": r.payload.get("category", ""),
                    "tags": r.payload.get("tags", []),
                    "source": r.payload.get("source", ""),
                } for r in results]
            except Exception:
                pass

        # 内存关键词检索
        return self._memory_search(query, top_k, category)

    def _memory_search(self, query, top_k, category=None):
        """内存模式关键词检索"""
        keywords = set(query.replace("，", " ").replace(",", " ").split())
        results = []

        for item in self._memory_store:
            if category and item.get("category") != category:
                continue
            content_lower = (item["title"] + item["content"]).lower()
            match_count = sum(1 for kw in keywords if kw.lower() in content_lower)
            if match_count > 0:
                score = min(0.99, 0.5 + match_count * 0.15)
                results.append({**item, "score": score})

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    def delete(self, doc_ids, collection=None):
        """删除文档

        Args:
            doc_ids: 文档ID列表
            collection: 集合名称
        """
        if self._has_qdrant and self._client:
            try:
                from qdrant_client.models import PointIdsList
                collection_name = collection or self.config.get("rag", {}).get("collection", "smart_content")
                self._client.delete(
                    collection_name=collection_name,
                    points_selector=PointIdsList(points=doc_ids),
                )
            except Exception:
                pass

        # 同时清理内存
        self._memory_store = [
            item for item in self._memory_store
            if not any(item["id"].startswith(did) for did in doc_ids)
        ]

    def _chunk_text(self, text, chunk_size=None, overlap=50):
        """文本分块"""
        chunk_size = chunk_size or self.config.get("rag", {}).get("chunk_size", 500)
        paragraphs = text.split("\n\n")
        chunks, current = [], ""
        for para in paragraphs:
            if len(current) + len(para) > chunk_size and current:
                chunks.append(current.strip())
                current = current[-overlap:] + "\n\n" + para
            else:
                current += "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if len(c) > 20]

    @property
    def is_available(self):
        """检查向量数据库是否可用"""
        return self._has_qdrant or len(self._memory_store) > 0
