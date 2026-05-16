import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.publisher import WeChatPublisher
p = WeChatPublisher()
print(f"Mode: {p.get_mode()}")

if p.get_mode() == "simulation" and p.app_id:
    print("Triggering Selenium init...")
    p._try_init_selenium()
    print(f"After init: {p.get_mode()}")

if p.get_mode() == "selenium":
    print("Opening Chrome for WeChat login...")
    success = p.login(timeout=120)
    print(f"Login result: {success}")
    input("Press Enter to close browser...")
    p.close()
else:
    print("Selenium not available, skipping browser test")
