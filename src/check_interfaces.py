import sys, os, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=== ContentGenerator ===")
from src.generator import ContentGenerator
print("generate:", inspect.signature(ContentGenerator.generate))
print("regenerate:", inspect.signature(ContentGenerator.regenerate))

print("\n=== Evaluator ===")
from src.evaluator import Evaluator
print("evaluate:", inspect.signature(Evaluator.evaluate))

print("\n=== VectorDB ===")
try:
    from src.rag.vector_db import VectorDB
    print("add_documents:", inspect.signature(VectorDB.add_documents))
    print("search:", inspect.signature(VectorDB.search))
except Exception as e:
    print("VectorDB import failed:", e)

print("\n=== SpiderManager ===")
try:
    from src.spiders.spider_manager import SpiderManager
    print("crawl_and_classify:", inspect.signature(SpiderManager.crawl_and_classify))
    print("full_workflow:", inspect.signature(SpiderManager.full_workflow))
except Exception as e:
    print("SpiderManager import failed:", e)
