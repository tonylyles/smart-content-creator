"""知识库管理 - 胡圳刚负责"""
import os
import json
from typing import List, Dict, Any, Optional


class KnowledgeBase:
    """知识库管理系统 - 支持文档添加、搜索和删除"""

    def __init__(self, config):
        self.config = config
        self.storage_path = config.get("path", "data/knowledge.json")
        self._ensure_storage()

    def _ensure_storage(self):
        """确保存储目录和文件存在"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        """添加文档到知识库"""
        if not documents:
            return 0
        
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        added_count = 0
        for doc in documents:
            # 确保文档有必要的字段
            doc_id = len(knowledge) + 1 + added_count
            doc.setdefault("id", doc_id)
            doc.setdefault("category", "general")
            doc.setdefault("source", "unknown")
            doc.setdefault("embedding", None)
            
            # 添加文档
            knowledge.append(doc)
            added_count += 1
        
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
        
        print(f"成功添加 {added_count} 篇文档到知识库")
        return added_count

    def search(self, query: str, top_k: int = 5, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索知识库 - 基于关键词匹配"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        if not knowledge:
            return []
        
        # 预处理查询词
        query_words = [w.strip().lower() for w in query.split() if w.strip()]
        
        # 计算相似度
        results = []
        for doc in knowledge:
            # 如果指定了分类，过滤
            if category and doc.get("category") != category:
                continue
            
            # 计算匹配分数
            title = doc.get("title", "").lower()
            content = doc.get("content", "").lower()
            
            score = 0
            for word in query_words:
                if word in title:
                    score += 3  # 标题匹配权重更高
                if word in content:
                    score += 1
            
            if score > 0:
                results.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "content": doc.get("content"),
                    "category": doc.get("category"),
                    "source": doc.get("source"),
                    "score": score
                })
        
        # 按分数排序并取前top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_document(self, doc_id: int) -> bool:
        """删除文档"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        original_count = len(knowledge)
        knowledge = [doc for doc in knowledge if doc.get("id") != doc_id]
        
        if len(knowledge) < original_count:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(knowledge, f, ensure_ascii=False, indent=2)
            print(f"成功删除文档 ID: {doc_id}")
            return True
        
        print(f"未找到文档 ID: {doc_id}")
        return False

    def get_categories(self) -> List[str]:
        """获取所有分类"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        categories = set()
        for doc in knowledge:
            categories.add(doc.get("category", "general"))
        
        return sorted(list(categories))

    def get_document_count(self) -> int:
        """获取文档总数"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        return len(knowledge)

    def get_document_by_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取文档"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        for doc in knowledge:
            if doc.get("id") == doc_id:
                return doc
        
        return None

    def update_document(self, doc_id: int, updates: Dict[str, Any]) -> bool:
        """更新文档"""
        with open(self.storage_path, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
        
        found = False
        for doc in knowledge:
            if doc.get("id") == doc_id:
                doc.update(updates)
                found = True
                break
        
        if found:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(knowledge, f, ensure_ascii=False, indent=2)
            print(f"成功更新文档 ID: {doc_id}")
            return True
        
        print(f"未找到文档 ID: {doc_id}")
        return False
