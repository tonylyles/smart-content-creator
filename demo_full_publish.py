"""
全链路演示：生成文章 → 自动发布到微信公众号
"""
import sys, os, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# ==================== Step 1: 生成文章 ====================
print("=" * 60)
print("  🚀 AuraScribe 全链路演示")
print("=" * 60)

from src.main import init_system
engine, scheduler, components = init_system()

pipeline_input = {
    "topic": "广州工业除湿技术创新趋势",
    "location": "广州",
    "current_date": "2026-05-08",
    "current_day": "Friday",
    "user_mood": "focused",
}

print(f"\n📋 生成主题: {pipeline_input['topic']}")
print("⏳ DeepSeek 生成中...\n")

result = engine.run_pipeline(
    stages=["rag_search", "generate_article"],
    input_data=pipeline_input,
)

if not result or not result.get("success"):
    print("❌ 生成失败，使用预设内容")
    title = "吉康环境闭式循环除湿技术解析"
    content_html = """<section style="padding:16px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;">
<h1 style="font-size:22px;color:#1a5c2a;border-bottom:3px solid #2d8c4e;padding-bottom:8px;">闭式循环除湿技术</h1>
<p style="font-size:16px;line-height:1.8;color:#333;">测试文章内容</p>
</section>"""
else:
    stages_data = result.get("stages_completed", {})
    gen_data = stages_data.get("generate_article", {}).get("data", {})
    title = gen_data.get("title", "吉康环境技术解析")
    content_md = gen_data.get("markdown", gen_data.get("content", ""))
    
    # 转换为微信 HTML
    from src.generator import ContentGenerator
    gen = ContentGenerator()
    content_html = gen._markdown_to_wechat_html(content_md)

print(f"\n✅ 文章生成完成: 「{title}」")
print(f"   正文长度: {len(content_html)} 字符")

# ==================== Step 2: 打开编辑器 ====================
print("\n" + "=" * 60)
print("  📱 自动发布到微信公众号")
print("=" * 60)

import pyperclip
import pyautogui

# 复制标题到剪贴板备用
pyperclip.copy(title)
print(f"📋 标题已复制到剪贴板: {title[:30]}...")

# 打开图文编辑页
edit_url = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77"
os.system(f'start "" "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
          f'--user-data-dir=C:\\Users\\ZhuanZ1\\chrome_wechat_profile '
          f'--no-first-run --no-default-browser-check "{edit_url}"')

print("\n⏳ 等待编辑器加载（8秒）...")
time.sleep(8)

# ==================== Step 3: 自动填写 ====================
print("\n🤖 开始自动填写...")

# 点击标题区域（微信编辑器标题大约在页面上方中间）
pyautogui.click(640, 280)
time.sleep(1)

# 粘贴标题
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.3)
pyautogui.hotkey('ctrl', 'v')
time.sleep(1)
print(f"  ✅ 标题已粘贴")

# Tab 到正文编辑器
pyautogui.press('tab')
time.sleep(1.5)

# 粘贴正文
pyperclip.copy(content_html)
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.3)
pyautogui.hotkey('ctrl', 'v')
time.sleep(3)
print(f"  ✅ 正文已粘贴")

# 保存草稿 Ctrl+S
pyautogui.hotkey('ctrl', 's')
time.sleep(2)
print(f"  ✅ 已按 Ctrl+S 保存")

print("\n" + "=" * 60)
print("  ✅ 自动发布流程完成！")
print("  💡 请检查 Chrome 中的文章是否正确")
print("=" * 60)
