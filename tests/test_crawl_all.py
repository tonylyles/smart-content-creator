"""测试爬虫 - 验证所有数据源"""
import sys
sys.path.insert(0, 'src')
from spiders.news_crawler import NewsCrawler
from collections import Counter

crawler = NewsCrawler()
results = crawler.crawl()

print()
print('=' * 60)
print(f'total: {len(results)}')
print('=' * 60)

source_count = Counter(r.get('source', 'unknown') for r in results)
for source, count in source_count.most_common():
    print(f'  {source}: {count}')
print()

for i, r in enumerate(results[:15], 1):
    title = r.get('title', 'no title')
    source = r.get('source', '?')
    print(f'{i}. [{source}] {title}')
