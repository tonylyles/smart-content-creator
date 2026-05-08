"""
全局配置中心 - 曾睿负责

功能：
- 集中管理所有模块的配置参数
- 提供 GLOBAL_CONFIG 全局配置字典
- 支持从 config.json 文件加载用户自定义配置（覆盖默认值）
- 包含 LLM、RAG、UI、DATA_SCHEMA 等所有业务配置
"""

import json
import os
from typing import Dict, Any


# ==================== 全局默认配置 ====================
GLOBAL_CONFIG: Dict[str, Any] = {
    # ---------- LLM / 生成器配置 ----------
    "llm": {
        "model": "gpt-4",                       # 默认大模型
        "api_key": "",                           # 从 .env 读取，留空则走模板模式
        "base_url": "https://api.openai.com/v1",  # 可替换为国内中转地址
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "generator": {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 4096,
        "default_content_type": "article",       # 默认内容类型
        "default_scene_type": "municipal",       # 默认场景类型（市政环保）
    },

    # ---------- RAG 检索配置 ----------
    "rag": {
        "model_name": "all-MiniLM-L6-v2",        # Embedding 模型
        "chunk_size": 500,
        "overlap": 50,
        "vector_db_url": "http://localhost:6333", # Qdrant 向量数据库地址
        "vector_db_collection": "knowledge_base", # 默认集合名
        "top_k": 5,                               # 默认检索条数
        "enable_vector_search": True,             # 是否启用向量检索
        "enable_keyword_search": True,            # 是否启用关键词检索
    },

    # ---------- 数据库配置 ----------
    "database": {
        "type": "sqlite",
        "path": "data/content.db",               # SQLite 数据库文件路径
    },

    # ---------- UI / Web 服务配置 ----------
    "ui": {
        "host": "0.0.0.0",
        "port": 8080,                            # Web 服务端口
        "debug": False,                          # 生产环境关闭调试模式
        "template_dir": "templates",
        "static_dir": "static",
    },

    # ---------- 数据层配置（与胡圳刚的数据规范对齐） ----------
    "data_schema": {
        # 向量数据库字段映射 —— 核心字段定义，入库时必须遵循
        "doc_id": "doc_id",                      # 文档唯一标识
        "text_field": "content",                 # 向量化时取 content 字段作为文本源
        "title_field": "title",                  # 标题字段
        "region_field": "region",                # 地域字段（如"广州"、"深圳"）
        "category_field": "category",            # 分类字段（如"政策"、"技术"、"案例"）
        "source_field": "source",                # 数据来源字段
        "timestamp_field": "created_at",         # 时间戳字段
        # 所有需要存储的元数据字段列表
        "metadata_fields": ["title", "region", "category", "source", "created_at"],
        # 地域-场景自动映射规则（业务规则）
        "region_to_scene": {
            "广州": "municipal",                 # 广州 → 市政环保
            "深圳": "municipal",
            "珠海": "municipal",
            "佛山": "industrial",                # 佛山 → 工业环保（陶瓷/制造业）
            "东莞": "industrial",
            "惠州": "industrial",
        },
        # 默认地域（当输入未指定时）
        "default_region": "广州",
    },

    # ---------- 调度器配置 ----------
    "scheduler": {
        "crawl_interval_hours": 6,               # 爬虫抓取间隔（小时）
        "generate_interval_hours": 12,           # 内容生成间隔（小时）
        "data_pipeline_hour": 2,                 # 数据清洗流水线运行时间（凌晨2点）
        "data_pipeline_minute": 0,
        "timezone": "Asia/Shanghai",
    },

    # ---------- 爬虫配置 ----------
    "spider": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "request_timeout": 30,
        "max_retries": 3,
        "crawl_delay": 1.0,                      # 爬取间隔（秒），避免被封
    },

    # ---------- 日志配置 ----------
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "file": "logs/app.log",
    },
}


def load_config(config_path: str = None) -> Dict[str, Any]:
    """加载配置

    优先级：config_path 参数 > 项目根目录 config.json > GLOBAL_CONFIG 默认值

    Args:
        config_path: 自定义配置文件路径，默认为项目根目录下的 config.json

    Returns:
        合并后的完整配置字典
    """
    # 1. 从默认配置深拷贝一份
    import copy
    config = copy.deepcopy(GLOBAL_CONFIG)

    # 2. 确定配置文件路径
    if config_path is None:
        # 默认从项目根目录读取 config.json
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config.json")

    # 3. 如果文件存在，读取并合并（用户配置覆盖默认值）
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config = _deep_merge(config, user_config)
            print(f"[配置] 已加载用户配置文件: {config_path}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[配置] ⚠️ 配置文件读取失败: {e}，使用默认配置")

    # 4. 尝试从 .env 读取敏感信息（如 API Key）
    _load_env_overrides(config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 中的值覆盖 base

    Args:
        base: 基础字典
        override: 覆盖字典

    Returns:
        合并后的新字典
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_env_overrides(config: dict):
    """从 .env 文件或环境变量加载敏感配置

    Args:
        config: 配置字典（原地修改）
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv 未安装时跳过

    import os
    # LLM API Key —— 优先级最高
    env_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    if env_key:
        config["llm"]["api_key"] = env_key
        config["generator"]["api_key"] = env_key

    # 向量数据库地址
    env_db = os.getenv("VECTOR_DB_URL")
    if env_db:
        config["rag"]["vector_db_url"] = env_db


def get_config_section(config: dict, section: str, default=None):
    """安全获取配置的某个区块

    Args:
        config: 完整配置字典
        section: 区块名称（如 "llm"、"rag"）
        default: 区块不存在时的默认返回值

    Returns:
        对应的配置子字典
    """
    if config is None:
        return default or {}
    return config.get(section, default or {})


if __name__ == "__main__":
    # 测试：打印当前完整配置
    cfg = load_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    print("\n[配置] 配置加载测试通过 ✓")
