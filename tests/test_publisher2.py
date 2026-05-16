import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.publisher import WeChatPublisher
p = WeChatPublisher()
print(f"Mode: {p.get_mode()}")

result = p.publish_article(
    title="pyautogui发布测试",
    content_html='<h2 style="color:#1a5c2a;">测试</h2>',
    author="吉康环境",
)
print(f"Result: {result['status']}")

stats = p.get_publish_stats()
print(f"Accuracy: {stats['accuracy']}% pass={stats['accuracy_pass']}")
p.close()
print("OK")
