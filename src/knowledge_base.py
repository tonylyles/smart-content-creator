"""知识库管理 - 胡圳刚负责"""


class KnowledgeBase:
    """知识库管理器"""

    def __init__(self, storage):
        self.storage = storage

    def add_documents(self, documents):
        """添加文档到知识库"""
        pass

    def search(self, query, top_k=5):
        """搜索知识库"""
        pass

    def delete_document(self, doc_id):
        """删除文档"""
        pass
