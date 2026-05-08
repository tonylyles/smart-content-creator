import sys, os, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.publisher import WeChatPublisher
p = WeChatPublisher()
print(f"Mode: {p.get_mode()}")

# 打开 Chrome 到微信登录页
print("\n>>> 打开 Chrome，请在弹出的浏览器中扫码登录 <<<")
success = p.login(timeout=0)  # timeout=0 不自动等待
print(f"Chrome opened: {success}")

input("\n扫码登录完成后，按 Enter 继续...")

# 打开图文编辑页
print("\n>>> 打开图文编辑页 <<<")
p.open_chrome("https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77")
input("编辑器加载完成后，按 Enter 开始自动填写...")

# 自动填写
import pyautogui
import pyperclip

title = "吉康环境闭式循环除湿技术解析"
pyautogui.click(640, 300)
time.sleep(0.5)
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.3)
pyperclip.copy(title)
pyautogui.hotkey('ctrl', 'v')
time.sleep(1)

print(f"标题已粘贴: {title}")
input("检查标题是否正确，按 Enter 继续...")

# 粘贴正文
content = """<section style="padding:16px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
<h1 style="font-size:22px;color:#1a5c2a;border-bottom:3px solid #2d8c4e;">闭式循环除湿技术</h1>
<p style="font-size:16px;line-height:1.8;color:#333;">这是一篇通过 AuraScribe AI 自动生成并通过 pyautogui 自动发布的测试文章。</p>
</section>"""

pyautogui.press('tab')
time.sleep(1)
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.3)
pyperclip.copy(content)
pyautogui.hotkey('ctrl', 'v')
time.sleep(2)

print("正文已粘贴")
input("检查正文是否正确，按 Enter 保存草稿...")

# Ctrl+S 保存
pyautogui.hotkey('ctrl', 's')
time.sleep(2)
print("已按 Ctrl+S 保存草稿")

input("按 Enter 关闭 Chrome...")
p.close()
print("DONE")
