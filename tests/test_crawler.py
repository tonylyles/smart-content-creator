import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.spiders.eco_crawler import EcoNewsCrawler
crawler = EcoNewsCrawler()
topics = crawler.auto_discover_topics(count=3)
print(f"\nFound {len(topics)} topics:")
for i, t in enumerate(topics, 1):
    print(f"  {i}. {t['title']}")
    print(f"     Keywords: {', '.join(t.get('keywords', []))}")
