import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.publisher import WeChatPublisher
p = WeChatPublisher()
print(f'mode: {p.get_mode()}')
print(f'app_id: {p.app_id}')
print(f'has_password: {bool(p.password)}')

result = p.publish_article(
    title='Selenium发布测试',
    content_html='<h2 style="color:#1a5c2a;">测试内容</h2><p style="line-height:1.8;">这是一篇测试文章</p>',
    author='吉康环境',
    digest='测试摘要',
)
print(f'publish status: {result["status"]}')

stats = p.get_publish_stats()
print(f'accuracy: {stats["accuracy"]}% pass={stats["accuracy_pass"]}')
p.close()
print('DONE')
