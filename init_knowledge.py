"""初始化知识库 - 将 jikang_knowledge.md 导入 Qdrant 向量数据库

用法：python init_knowledge.py
"""
import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.config import load_config
from src.knowledge_base import KnowledgeBase
from src.rag.vector_db import VectorDB


def main():
    cfg = load_config()
    kb = KnowledgeBase(cfg)

    # 读取知识库文件
    kb_path = "data/jikang_knowledge.md"
    if not os.path.exists(kb_path):
        print(f"知识库文件不存在: {kb_path}")
        return

    with open(kb_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按二级标题分块
    chunks = []
    current_title = "吉康环境产品与品牌知识库"
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_lines:
                chunks.append({
                    "title": current_title,
                    "content": "\n".join(current_lines).strip(),
                })
            current_title = line.lstrip("# ").strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append({
            "title": current_title,
            "content": "\n".join(current_lines).strip(),
        })

    print(f"知识库分块: {len(chunks)} 个文档")

    # 添加到知识库
    documents = []
    for chunk in chunks:
        documents.append({
            "content": chunk["content"],
            "metadata": {"title": chunk["title"], "source": "jikang_knowledge.md"},
        })

    result = kb.add_documents(documents)
    print(f"导入结果: {result}")

    # 验证
    search_result = kb.search("污泥干化", top_k=3)
    print(f"\n验证检索 '污泥干化': {len(search_result)} 条结果")
    for r in search_result[:2]:
        print(f"  - {r.get('title', 'N/A')}: {r.get('content', '')[:80]}...")

    print("\n知识库初始化完成！")


if __name__ == "__main__":
    main()
