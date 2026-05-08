import sys, os, traceback
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from src.main import *
    engine, scheduler, components = init_system()
    
    # Quick test: just publish without generating
    publisher = components.get("publisher")
    print(f"\nPublisher mode: {publisher.get_mode()}")
    print(f"App ID: {publisher.app_id}")
    print(f"Has password: {bool(publisher.password)}")
    
    # Test publish
    result = publisher.publish_article(
        title="快速发布测试",
        content_html="<h2>测试</h2>",
        author="吉康环境",
    )
    print(f"Result: {result['status']}")
    
    stats = publisher.get_publish_stats()
    print(f"Accuracy: {stats['accuracy']}%")
    
    publisher.close()
    print("\nDONE")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
