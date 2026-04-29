"""配置管理 - 曾睿负责"""
import json
import os

DEFAULT_CONFIG = {
    "database": {
        "type": "sqlite",
        "path": "data/content.db"
    },
    "rag": {
        "model_name": "all-MiniLM-L6-v2",
        "chunk_size": 500,
        "overlap": 50
    },
    "generator": {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000
    },
    "scheduler": {
        "crawl_interval_hours": 6,
        "generate_interval_hours": 12
    }
}


def load_config(path=None):
    """加载配置文件"""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config.json")

    config = DEFAULT_CONFIG.copy()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            config.update(user_config)
    return config
