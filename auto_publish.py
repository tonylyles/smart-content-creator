"""
AuraScribe 一键自动生成 + 定时发布

功能：
1. 自动发现热门话题（环保行业爬虫）
2. 自动生成推文（DeepSeek + 产品知识）
3. 定时发布到微信公众号

用法：
  python auto_publish.py                    # 立即生成一篇并发布
  python auto_publish.py --schedule 09:00   # 每天早上9点自动生成并发布
  python auto_publish.py --discover         # 仅发现话题，不生成
"""
import sys, os, argparse
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime


def auto_generate_and_publish(topic: str = None, keywords: list = None,
                               location: str = "广州", publish: bool = True,
                               scheduled_time: str = ""):
    """自动生成文章并发布
    
    Args:
        topic: 主题（为空则自动发现）
        keywords: 关键词列表
        location: 地点（触发业务规则）
        publish: 是否发布
        scheduled_time: 定时发布时间
    """
    from src.main import init_system
    
    engine, scheduler, components = init_system()
    publisher = components.get("publisher")
    generator = components.get("generator")
    
    # 1. 自动发现话题（如果没有指定）
    if not topic:
        print("\n🔍 未指定话题，自动发现中...")
        try:
            from src.spiders.news_crawler import NewsCrawler
            crawler = NewsCrawler()
            topics = crawler.auto_discover_topics(count=3)
            if topics:
                chosen = topics[0]
                topic = chosen["title"]
                keywords = chosen.get("keywords", keywords)
                print(f"✅ 选择话题: {topic}")
            else:
                topic = "吉康环境低温除湿技术最新进展"
                keywords = ["低温除湿", "污泥干化", "节能"]
        except Exception as e:
            print(f"⚠️ 话题发现失败: {e}，使用默认话题")
            topic = "吉康环境闭式循环除湿技术创新"
            keywords = ["闭式循环", "除湿", "节能"]
    
    # 2. 生成文章
    print(f"\n📝 开始生成文章: 「{topic}」")
    
    now = datetime.now()
    input_data = {
        "topic": topic,
        "location": location,
        "current_date": now.strftime("%Y-%m-%d"),
        "current_day": now.strftime("%A"),
        "keywords": keywords or [],
    }
    
    result = engine.run_pipeline(
        stages=["rag_search", "generate_article"],
        input_data=input_data,
    )
    
    if result["status"] != "success":
        print(f"❌ 生成失败: {result.get('message', '未知错误')}")
        return None
    
    # 提取结果
    stages_done = result.get("stages_completed", {})
    gen_data = stages_done.get("generate_article", {}).get("data", {})
    md = gen_data.get("markdown", "")
    html = gen_data.get("html", "")
    title = md.split("\n")[0].lstrip("# ").strip() if md else topic
    
    print(f"\n✅ 文章生成完成！")
    print(f"   标题: {title}")
    print(f"   字数: {len(md)}")
    print(f"   耗时: {gen_data.get('generation_time_ms', 'N/A')}ms")
    
    # 保存HTML预览到桌面
    desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if not os.path.exists(desktop):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    
    preview_path = os.path.join(desktop, "文章预览.html")
    from src.generator import ContentGenerator
    gen = ContentGenerator()
    wechat_html = gen._markdown_to_wechat_html(md)
    
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>{title}</title></head>
<body style="margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:640px;margin:0 auto;background:#fff;padding:30px 20px;">
{wechat_html}
</div></body></html>"""
    
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"💾 HTML预览已保存到桌面: 文章预览.html")
    
    # 3. 发布
    if publish and publisher:
        print(f"\n📱 发布到微信公众号...")
        pub_result = publisher.publish_article(
            title=title,
            content_html=wechat_html,
            author="吉康环境",
            digest=md[:100].replace("\n", " ") if md else "",
            scheduled_time=scheduled_time,
        )
        print(f"发布结果: {pub_result['status']}")
        if pub_result.get("publish_id"):
            print(f"  publish_id: {pub_result['publish_id']}")
        
        # 统计
        stats = publisher.get_publish_stats()
        print(f"📊 累计发布: {stats['total']}次, 准确率: {stats['accuracy']}%")
        publisher.close()
    
    return {"title": title, "content": md, "html": wechat_html}


def run_scheduled(hour: int = 9, minute: int = 0):
    """启动定时调度：每天指定时间自动生成并发布"""
    from src.main import init_system
    engine, scheduler, components = init_system()
    
    print(f"\n⏰ 设置定时任务: 每天 {hour:02d}:{minute:02d} 自动生成并发布")
    
    # 注册定时生成任务
    scheduler.add_daily_task(
        task_name="auto_publish",
        func=auto_generate_and_publish,
        hour=hour,
        minute=minute,
    )
    
    print(f"✅ 定时任务已注册")
    print(f"📋 当前任务列表:")
    for t in scheduler.list_tasks():
        print(f"  - {t}")
    
    # 启动调度器
    scheduler.start()
    print(f"\n🚀 调度器已启动，等待定时触发...")
    print(f"💡 按 Ctrl+C 停止")
    
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n⏹️ 调度器已停止")
        scheduler.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AuraScribe 自动生成+发布")
    parser.add_argument("--topic", "-t", help="指定话题（不指定则自动发现）")
    parser.add_argument("--keywords", "-k", help="关键词，逗号分隔")
    parser.add_argument("--location", "-l", default="广州", help="地点（默认广州）")
    parser.add_argument("--schedule", "-s", help="定时发布，格式 HH:MM（如 09:00）")
    parser.add_argument("--discover", "-d", action="store_true", help="仅发现话题，不生成")
    parser.add_argument("--no-publish", action="store_true", help="生成但不发布")
    
    args = parser.parse_args()
    
    if args.discover:
        # 仅发现话题
        try:
            from src.spiders.news_crawler import NewsCrawler
            crawler = NewsCrawler()
            topics = crawler.auto_discover_topics(count=5)
            print(f"\n🎯 发现的话题:")
            for i, t in enumerate(topics, 1):
                print(f"  {i}. {t['title']}")
                print(f"     关键词: {', '.join(t.get('keywords', []))}")
        except Exception as e:
            print(f"❌ 发现失败: {e}")
    
    elif args.schedule:
        # 定时模式
        parts = args.schedule.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        run_scheduled(hour, minute)
    
    else:
        # 立即生成
        keywords = args.keywords.split(",") if args.keywords else None
        auto_generate_and_publish(
            topic=args.topic,
            keywords=keywords,
            location=args.location,
            publish=not args.no_publish,
        )
