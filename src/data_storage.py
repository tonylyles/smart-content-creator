"""数据存储接口 - 胡圳刚负责"""
import json
import os
import sqlite3
from typing import List, Dict, Any, Optional


class DataStorage:
    """数据存储抽象层 - 支持SQLite和JSON文件两种模式"""

    def __init__(self, config):
        self.config = config
        self.mode = config.get("type", "json")  # json 或 sqlite
        self.path = config.get("path", "data/content.db")
        
        # 确保数据目录存在
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        
        if self.mode == "sqlite":
            self._init_sqlite()

    def _init_sqlite(self):
        """初始化SQLite数据库"""
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        
        # 创建内容表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                content_type TEXT,
                scene_type TEXT,
                created_at TEXT,
                data JSON
            )
        ''')
        
        # 创建知识库表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                category TEXT,
                source TEXT,
                embedding BLOB,
                created_at TEXT
            )
        ''')
        
        # 创建发布计划表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS release_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                content_type TEXT,
                title TEXT,
                priority INTEGER,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        conn.commit()
        conn.close()

    def save(self, collection: str, data: Dict[str, Any]) -> int:
        """保存数据"""
        if self.mode == "sqlite":
            return self._sqlite_save(collection, data)
        else:
            return self._json_save(collection, data)

    def _sqlite_save(self, collection: str, data: Dict[str, Any]) -> int:
        """SQLite保存"""
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        
        if collection == "contents":
            cursor.execute('''
                INSERT INTO contents (title, content, content_type, scene_type, created_at, data)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            ''', (data.get("title"), data.get("content"), data.get("content_type"), 
                  data.get("scene_type"), json.dumps(data)))
        elif collection == "knowledge":
            cursor.execute('''
                INSERT INTO knowledge (title, content, category, source, created_at, data)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            ''', (data.get("title"), data.get("content"), data.get("category"), 
                  data.get("source"), json.dumps(data)))
        elif collection == "release_plans":
            cursor.execute('''
                INSERT INTO release_plans (date, content_type, title, priority)
                VALUES (?, ?, ?, ?)
            ''', (data.get("date"), data.get("content_type"), data.get("title"), data.get("priority", 3)))
        
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id

    def _json_save(self, collection: str, data: Dict[str, Any]) -> int:
        """JSON文件保存"""
        file_path = f"data/{collection}.json"
        os.makedirs("data", exist_ok=True)
        
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        else:
            records = []
        
        record_id = len(records) + 1
        data["id"] = record_id
        records.append(data)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        return record_id

    def query(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """查询数据"""
        if self.mode == "sqlite":
            return self._sqlite_query(collection, filters)
        else:
            return self._json_query(collection, filters)

    def _sqlite_query(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """SQLite查询"""
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        
        query = f"SELECT * FROM {collection}"
        params = []
        
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"{key} = ?")
                params.append(value)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return results

    def _json_query(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """JSON文件查询"""
        file_path = f"data/{collection}.json"
        
        if not os.path.exists(file_path):
            return []
        
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        if filters:
            records = [r for r in records if all(r.get(k) == v for k, v in filters.items())]
        
        return records

    def delete(self, collection: str, doc_id: int) -> bool:
        """删除数据"""
        if self.mode == "sqlite":
            return self._sqlite_delete(collection, doc_id)
        else:
            return self._json_delete(collection, doc_id)

    def _sqlite_delete(self, collection: str, doc_id: int) -> bool:
        """SQLite删除"""
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        
        cursor.execute(f"DELETE FROM {collection} WHERE id = ?", (doc_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        return affected > 0

    def _json_delete(self, collection: str, doc_id: int) -> bool:
        """JSON文件删除"""
        file_path = f"data/{collection}.json"
        
        if not os.path.exists(file_path):
            return False
        
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        original_count = len(records)
        records = [r for r in records if r.get("id") != doc_id]
        
        if len(records) < original_count:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        
        return False
