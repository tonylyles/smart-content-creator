"""
系统总入口 - 曾睿负责

功能：
- 实例化所有核心组件（WorkflowEngine、TaskScheduler）
- 导入并对接队友的模块（凯睿的 RAG/生成器、胡圳刚的数据层）
- 将队友的功能注册到工作流引擎中
- 提供完整的测试入口，模拟端到端运行

设计原则：
- 健壮性优先：所有外部模块导入均有 try-except 保护
- Dummy Class 兜底：队友代码缺失时创建虚拟类，保证系统可启动
- 错误不闪退：所有异常被捕获并打印详细错误位置
"""

import sys
import os
import traceback
from datetime import datetime

# 修复 Windows 控制台编码问题（gbk 不支持 emoji）
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中，支持 `python src/main.py` 直接运行
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ==================== 加载配置 ====================
try:
    from src.config import load_config, GLOBAL_CONFIG
    config = load_config()
    print("[启动] ✅ 全局配置加载完成")
except Exception as e:
    print(f"[启动] ❌ 配置加载失败: {e}")
    config = {}
    traceback.print_exc()

# ==================== 导入队友模块（带容错） ====================

# ---------- 防 Mock 开关 ----------
# 如果 LLM_API_KEY 存在，强制使用真实类，导入失败直接报错
_FORCE_REAL = bool(os.getenv("LLM_API_KEY", ""))
if _FORCE_REAL:
    print("[启动] 🔒 检测到 LLM_API_KEY，已启用防 Mock 模式")
    print("[启动] 💡 所有模块将使用真实实现，导入失败将直接抛出异常")
else:
    print("[启动] ℹ️ 未检测到 LLM_API_KEY，将使用容错兜底模式")

# ---------- 凯睿的模块 ----------

# 1. PromptEngine（提示词引擎）
try:
    from src.prompt_engine import PromptEngine
    PromptEngineClass = PromptEngine
    print("[启动] ✅ 导入 PromptEngine（凯睿）")
except ImportError as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ PromptEngine 导入失败（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ⚠️ 导入 PromptEngine 失败: {e}，创建虚拟类")
    class PromptEngineClass:
        """虚拟 PromptEngine —— 原模块缺失时的兜底替代"""
        def __init__(self, config=None):
            self.config = config or {}
        def build_prompt(self, **kwargs):
            return {"system_prompt": "Mock", "user_prompt": "Mock"}
except Exception as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ PromptEngine 导入异常（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ❌ PromptEngine 导入异常: {e}")
    class PromptEngineClass:
        def __init__(self, config=None):
            pass
        def build_prompt(self, **kwargs):
            return {"system_prompt": "Mock", "user_prompt": "Mock"}

# 2. RAGRetriever（RAG 检索模块）
try:
    from src.rag.retriever import RAGRetriever
    RAGRetrieverClass = RAGRetriever
    print("[启动] ✅ 导入 RAGRetriever（凯睿）")
except ImportError as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ RAGRetriever 导入失败（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ⚠️ 导入 RAGRetriever 失败: {e}，创建虚拟类")
    class RAGRetrieverClass:
        """虚拟 RAGRetriever —— 原模块缺失时的兜底替代"""
        def __init__(self, config=None, knowledge_base=None, vector_db=None):
            self.config = config or {}
        def retrieve(self, query, top_k=5, category=None, scene_type=None):
            print(f"  [Mock RAG] 收到查询: {query}")
            return [
                {
                    "title": f"【Mock RAG】关于'{query}'的政策文件",
                    "content": f"这是模拟的 RAG 检索结果。实际部署后，"
                       f"将显示与'{query}'相关的真实知识库内容。",
                    "score": 0.85,
                    "category": "政策",
                    "source": "mock",
                },
            ]
        def expand_query(self, query, scene_type=None):
            return query
except Exception as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ RAGRetriever 导入异常（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ❌ RAGRetriever 导入异常: {e}")
    class RAGRetrieverClass:
        def __init__(self, config=None, **kwargs):
            pass
        def retrieve(self, query, **kwargs):
            return [{"title": "Mock", "content": "Mock", "score": 0.5, "source": "mock"}]

# 3. ContentGenerator（内容生成模块）
try:
    from src.generator import ContentGenerator
    ContentGeneratorClass = ContentGenerator
    print("[启动] ✅ 导入 ContentGenerator（凯睿）")
except ImportError as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ ContentGenerator 导入失败（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ⚠️ 导入 ContentGenerator 失败: {e}，创建虚拟类")
    class ContentGeneratorClass:
        """虚拟 ContentGenerator —— 原模块缺失时的兜底替代"""
        def __init__(self, config=None, prompt_engine=None):
            self.config = config or {}
            self.prompt_engine = prompt_engine
        def generate(self, topic, context=None, content_type="article",
                     scene_type="municipal", keywords=None, **kwargs):
            print(f"  [Mock Generator] 生成主题: {topic}")
            return {
                "markdown": f"# 【Mock 内容】{topic}\n\n这是模拟生成的内容。",
                "html": f"<h1>{topic}</h1><p>模拟内容</p>",
                "generation_time_ms": 0,
                "content_type": content_type,
                "scene_type": scene_type,
            }
except Exception as e:
    if _FORCE_REAL:
        print(f"[启动] ❌ ContentGenerator 导入异常（防 Mock 模式，直接报错）: {e}")
        raise
    print(f"[启动] ❌ ContentGenerator 导入异常: {e}")
    class ContentGeneratorClass:
        def __init__(self, config=None, prompt_engine=None):
            pass
        def generate(self, topic, **kwargs):
            return {"markdown": f"# Mock: {topic}", "html": "", "generation_time_ms": 0}


# ---------- 胡圳刚的模块 ----------

# 4. DataStorage（数据存储模块）
try:
    from src.data_storage import DataStorage
    DataStorageClass = DataStorage
    print("[启动] ✅ 导入 DataStorage（胡圳刚）")
except ImportError as e:
    print(f"[启动] ⚠️ 导入 DataStorage 失败: {e}，创建虚拟类")
    class DataStorageClass:
        def __init__(self, config):
            self.config = config
        def save(self, collection, data):
            print(f"  [Mock Storage] 模拟保存到 {collection}")
            return 0
        def query(self, collection, filters=None):
            return []
        def delete(self, collection, doc_id):
            return False

# 5. KnowledgeBase（知识库模块 - 胡圳刚）
try:
    from src.knowledge_base import KnowledgeBase
    KnowledgeBaseClass = KnowledgeBase
    print("[启动] ✅ 导入 KnowledgeBase（胡圳刚）")
except ImportError as e:
    print(f"[启动] ⚠️ 导入 KnowledgeBase 失败: {e}，创建虚拟类")
    class KnowledgeBaseClass:
        def __init__(self, config):
            self.config = config
        def search(self, query, top_k=5, category=None):
            return [{"title": "Mock", "content": "Mock", "score": 0.5}]
        def add_documents(self, documents):
            return 0

# ---------- 凯睿的附加模块 ----------

# 6. Evaluator（质量评估模块 - 凯睿）
try:
    from src.evaluator import Evaluator
    EvaluatorClass = Evaluator
    print("[启动] ✅ 导入 Evaluator（凯睿）")
except ImportError as e:
    print(f"[启动] ⚠️ 导入 Evaluator 失败: {e}，创建虚拟类")
    class EvaluatorClass:
        def __init__(self, config=None, prompt_engine=None):
            pass
        def evaluate(self, content, title="", scene_type="municipal"):
            return {"accuracy_score": 0.7, "compliance_score": 0.8, "readability_score": 0.75, "brand_alignment_score": 0.7, "overall": 0.74, "result": "needs_revision", "comments": "Mock"}


# ==================== 导入本方模块 ====================

try:
    from src.workflow import WorkflowEngine
    print("[启动] ✅ 导入 WorkflowEngine（曾睿）")
except ImportError as e:
    print(f"[启动] ❌ WorkflowEngine 导入失败: {e}")
    print("[启动] 💥 本方模块缺失，系统无法启动")
    sys.exit(1)

try:
    from src.scheduler import TaskScheduler
    print("[启动] ✅ 导入 TaskScheduler（曾睿）")
except ImportError as e:
    print(f"[启动] ❌ TaskScheduler 导入失败: {e}")
    sys.exit(1)


# ==================== 初始化核心组件 ====================

def init_system():
    """初始化整个系统

    实例化所有组件，注册工作流阶段，配置定时任务。

    Returns:
        tuple: (engine, scheduler, components) 三元组
    """
    print("\n" + "=" * 60)
    print("  🚀 公众号智能创作平台 —— 系统启动")
    print("=" * 60)

    # 1. 创建 PromptEngine（生成器的依赖）
    try:
        prompt_engine = PromptEngineClass(config)
        print("[初始化] ✅ PromptEngine 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ PromptEngine 实例化失败: {e}")
        traceback.print_exc()
        prompt_engine = None

    # 2. 创建 ContentGenerator
    try:
        generator = ContentGeneratorClass(config=config, prompt_engine=prompt_engine)
        print("[初始化] ✅ ContentGenerator 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ ContentGenerator 实例化失败: {e}")
        traceback.print_exc()
        generator = None

    # 3. 创建 RAGRetriever
    try:
        rag_system = RAGRetrieverClass(config=config)
        print("[初始化] ✅ RAGRetriever 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ RAGRetriever 实例化失败: {e}")
        traceback.print_exc()
        rag_system = None

    # 4. 创建 DataStorage
    try:
        db_config = config.get("database", {})
        data_storage = DataStorageClass(db_config)
        print("[初始化] ✅ DataStorage 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ DataStorage 实例化失败: {e}")
        traceback.print_exc()
        data_storage = None

    # 5. 创建 KnowledgeBase（胡圳刚）
    try:
        kb_config = config.get("database", {"path": "data/knowledge.json"})
        knowledge_base = KnowledgeBaseClass(kb_config)
        print("[初始化] ✅ KnowledgeBase 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ KnowledgeBase 实例化失败: {e}")
        traceback.print_exc()
        knowledge_base = None

    # 6. 创建 Evaluator（凯睿）
    try:
        evaluator = EvaluatorClass(config=config, prompt_engine=prompt_engine)
        print("[初始化] ✅ Evaluator 实例化完成")
    except Exception as e:
        print(f"[初始化] ❌ Evaluator 实例化失败: {e}")
        traceback.print_exc()
        evaluator = None

    # ==================== 5. 实例化 WorkflowEngine 并注册阶段 ====================
    engine = WorkflowEngine(config=config)

    if rag_system is not None and knowledge_base is not None:
        # 将 KnowledgeBase 注入到 RAG 检索器中（凯睿的 RAGRetriever 支持此参数）
        rag_system.knowledge_base = knowledge_base
        print("[初始化] ✅ KnowledgeBase 已注入 RAGRetriever")

    if rag_system is not None:
        # 注册 RAG 检索为 "rag_search" 阶段
        # 凯睿的 retrieve 签名: retrieve(query, top_k, category, scene_type)
        engine.register_stage("rag_search", rag_system.retrieve)
    else:
        print("[初始化] ⚠️ RAG 模块不可用，跳过 rag_search 注册")

    if generator is not None:
        # 注册内容生成为 "generate_article" 阶段
        # 凯睿的 generate 签名: generate(topic, context, content_type, scene_type, keywords, ...)
        # WorkflowEngine 会自动将 input_data 字典解包为 **kwargs 传入
        engine.register_stage("generate_article", generator.generate)
    else:
        print("[初始化] ⚠️ 生成器模块不可用，跳过 generate_article 注册")

    if evaluator is not None:
        # 注册质量评估为 "evaluate" 阶段
        # 凯睿的 evaluate 签名: evaluate(content, title, scene_type)
        engine.register_stage("evaluate", evaluator.evaluate)
    else:
        print("[初始化] ⚠️ 评估模块不可用，跳过 evaluate 注册")

    # ==================== 注册阶段间数据转换器 ====================
    # RAG 检索结果 → 生成器的 reference 参数
    engine.register_transform("rag_search", WorkflowEngine.rag_to_generator_transform)
    # 生成器输出 → 评估器的 content 参数
    engine.register_transform("generate_article", WorkflowEngine.generator_to_evaluator_transform)

    # ==================== 注册爬虫模块（胡圳刚）====================
    spider_manager = None
    try:
        from src.spiders.spider_manager import SpiderManager
        spider_manager = SpiderManager()
        engine.register_stage("crawl_news", spider_manager.full_workflow)
        print("[初始化] ✅ SpiderManager 已注册为 'crawl_news' 阶段")
    except ImportError:
        print("[初始化] ⚠️ SpiderManager 不可用，跳过爬虫注册")
    except Exception as e:
        print(f"[初始化] ⚠️ SpiderManager 注册失败: {e}")

    print(f"[初始化] 📋 已注册的工作流阶段: {engine.list_stages()}")

    # ==================== 6. 实例化 TaskScheduler ====================
    scheduler = TaskScheduler(config=config, workflow_engine=engine)

    # 配置默认定时任务
    scheduler_cfg = config.get("scheduler", {})

    # 每天凌晨运行数据清洗流水线（胡圳刚的数据脚本）
    scheduler.add_daily_task(
        task_name="data_pipeline",
        func=scheduler._run_data_pipeline,
        hour=scheduler_cfg.get("data_pipeline_hour", 2),
        minute=scheduler_cfg.get("data_pipeline_minute", 0),
    )

    # 打印已注册的任务
    tasks = scheduler.list_tasks()
    print(f"[初始化] ⏰ 已注册的定时任务: {len(tasks)} 个")
    for t in tasks:
        print(f"  - {t}")

    # 收集所有组件
    components = {
        "config": config,
        "prompt_engine": prompt_engine,
        "generator": generator,
        "rag_system": rag_system,
        "knowledge_base": knowledge_base,
        "data_storage": data_storage,
        "evaluator": evaluator,
    }

    print("\n" + "=" * 60)
    print("  ✅ 系统初始化完成，所有模块就绪")
    print("=" * 60 + "\n")

    return engine, scheduler, components


# ==================== 主入口 ====================

if __name__ == "__main__":
    # 初始化系统
    engine, scheduler, components = init_system()

    print("=" * 60)
    print("  🔥 全链路点亮测试 —— 广州周五特供版")
    print(f"  当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}")
    print(f"  防 Mock 模式: {'开启 🔒' if _FORCE_REAL else '关闭'}")
    print("=" * 60 + "\n")

    # ---- 广州周五特供测试用例 ----
    test_input = {
        "topic": "广州海珠区周末去哪玩",
        "location": "广州",          # 必须包含，触发业务规则
        "current_date": "2026-05-08", # 注入日期，触发时间策略
        "current_day": "Friday",     # 兼容：也注入星期
        "user_mood": "relaxed",      # 模拟周五下午的松弛感
    }

    print(f"📋 测试输入: {test_input}\n")

    # 执行链式流水线：RAG 检索 → 内容生成
    print("🚀 执行流水线: rag_search → generate_article")
    print("-" * 60)
    try:
        pipeline_result = engine.run_pipeline(
            stages=["rag_search", "generate_article"],
            input_data=test_input,
        )
        print("-" * 60)

        if pipeline_result["status"] == "success":
            # 从 stages_completed 取生成阶段的原始输出（避免转换器覆盖）
            stages_done = pipeline_result.get("stages_completed", {})
            gen_stage = stages_done.get("generate_article", {}).get("data", {})
            final = pipeline_result.get("data", {})

            # 优先从生成阶段取 markdown，其次从转换后的 final 取 content
            md = gen_stage.get("markdown", "") or final.get("content", "") or final.get("markdown", "")

            print(f"\n✅ 流水线成功！")
            print(f"  生成耗时: {gen_stage.get('generation_time_ms', 'N/A')}ms")
            print(f"  场景类型: {gen_stage.get('scene_type', final.get('scene_type', 'N/A'))}")

            # 探针检测：检查生成内容是否包含时空特征词
            probe_words = ["周末", "海珠", "大湾区", "饮茶", "广州", "周五"]
            found = [w for w in probe_words if w in md]
            missing = [w for w in probe_words if w not in md]

            print(f"\n🔬 探针检测结果:")
            print(f"  命中关键词: {found if found else '无'}")
            print(f"  未命中: {missing if missing else '无'}")

            if found:
                print(f"  ✅ 系统「活了」！生成内容包含真实上下文感知。")
            else:
                print(f"  ⚠️ 内容未包含预期关键词，可能走了 Mock 路径。")

            # 输出生成内容预览
            print(f"\n📝 生成内容预览:")
            print("=" * 60)
            # 输出前 1500 字符
            preview = md[:1500] if len(md) > 1500 else md
            print(preview)
            if len(md) > 1500:
                print(f"\n... (共 {len(md)} 字符，已截断)")
            print("=" * 60)

            # 保存完整输出到文件
            output_path = os.path.join(_project_root, "test_output.md")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"\n💾 完整内容已保存到: {output_path}")

        else:
            print(f"\n❌ 流水线失败！")
            print(f"  失败阶段: {pipeline_result.get('failed_stage', 'N/A')}")
            print(f"  错误信息: {pipeline_result.get('message', 'N/A')}")
            print(f"\n💡 提示: 这说明某个真实模块报错了，根据上面的错误信息排查依赖。")
            print(f"   常见原因: pip install langchain-openai openai httpx")

    except Exception as e:
        print(f"\n💥 测试异常: {e}")
        traceback.print_exc()
        print(f"\n💡 这是真实错误（非 Mock），请根据报信息安装缺失依赖。")
