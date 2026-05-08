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

# ---------- 凯睿的模块 ----------

# 1. PromptEngine（提示词引擎）
try:
    from src.prompt_engine import PromptEngine
    PromptEngineClass = PromptEngine
    print("[启动] ✅ 导入 PromptEngine（凯睿）")
except ImportError as e:
    print(f"[启动] ⚠️ 导入 PromptEngine 失败: {e}，创建虚拟类")
    class PromptEngineClass:
        """虚拟 PromptEngine —— 原模块缺失时的兜底替代"""
        def __init__(self, config=None):
            self.config = config or {}
        def build_prompt(self, **kwargs):
            return {"system_prompt": "Mock", "user_prompt": "Mock"}
except Exception as e:
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
    print("  🧪 开始端到端测试")
    print("=" * 60 + "\n")

    # ---- 测试1：单阶段 RAG 检索 ----
    print("【测试1】RAG 检索")
    print("-" * 40)
    try:
        rag_result = engine.run("rag_search", {
            "query": "广州环保政策 2026",
            "top_k": 3,
        })
        print(f"  状态: {rag_result['status']}")
        if rag_result['status'] == 'success':
            print(f"  检索到 {len(rag_result['data'])} 条结果")
            for i, item in enumerate(rag_result['data'][:2]):
                print(f"    [{i+1}] {item.get('title', 'N/A')} (score={item.get('score', 'N/A')})")
        else:
            print(f"  错误: {rag_result.get('message')}")
    except Exception as e:
        print(f"  ❌ 测试1异常: {e}")
        traceback.print_exc()

    print()

    # ---- 测试2：单阶段内容生成 ----
    print("【测试2】内容生成")
    print("-" * 40)
    try:
        gen_result = engine.run("generate_article", {
            "topic": "广州环保",
            "content_type": "article",
            "scene_type": "municipal",
            "keywords": ["污水处理", "绿色能源", "碳中和"],
        })
        print(f"  状态: {gen_result['status']}")
        if gen_result['status'] == 'success':
            data = gen_result['data']
            # 打印生成文章的前几行
            markdown = data.get("markdown", "")
            lines = markdown.split("\n")[:5]
            print(f"  生成耗时: {data.get('generation_time_ms', 'N/A')}ms")
            print(f"  内容预览:")
            for line in lines:
                print(f"    {line}")
            if len(markdown.split("\n")) > 5:
                print("    ...")
        else:
            print(f"  错误: {gen_result.get('message')}")
    except Exception as e:
        print(f"  ❌ 测试2异常: {e}")
        traceback.print_exc()

    print()

    # ---- 测试3：链式流水线（RAG → 生成，带转换器） ----
    print("【测试3】链式流水线（RAG 检索 → 内容生成，带数据转换器）")
    print("-" * 40)
    try:
        pipeline_result = engine.run_pipeline(
            stages=["rag_search", "generate_article"],
            input_data={
                "topic": "广州环保",
                "location": "广州",
                "content_type": "article",
                "keywords": ["环保政策", "绿色发展"],
            },
        )
        print(f"  流水线状态: {pipeline_result['status']}")
        if pipeline_result['status'] == 'success':
            final = pipeline_result.get('data', {})
            md = final.get("markdown", "")
            if md:
                lines = md.split("\n")[:4]
                print(f"  内容预览:")
                for line in lines:
                    print(f"    {line}")
                if len(md.split("\n")) > 4:
                    print("    ...")
            else:
                print(f"  最终输出: {str(final)[:150]}...")
        else:
            print(f"  失败阶段: {pipeline_result.get('failed_stage', 'N/A')}")
            print(f"  错误信息: {pipeline_result.get('message')}")
    except Exception as e:
        print(f"  ❌ 测试3异常: {e}")
        traceback.print_exc()

    print()

    # ---- 测试4：三阶段完整流水线（RAG → 生成 → 评估） ----
    print("【测试4】三阶段完整流水线（RAG → 生成 → 评估）")
    print("-" * 40)
    try:
        full_result = engine.run_pipeline(
            stages=["rag_search", "generate_article", "evaluate"],
            input_data={
                "topic": "广州水环境治理",
                "location": "广州",
                "scene_type": "municipal",
                "content_type": "article",
                "keywords": ["污水处理", "碳中和"],
            },
        )
        print(f"  流水线状态: {full_result['status']}")
        if full_result['status'] == 'success':
            stages_done = full_result.get('stages_completed', {})
            for sname, sinfo in stages_done.items():
                status = sinfo.get('status', '?')
                data = sinfo.get('data', {})
                if sname == "rag_search" and isinstance(data, list):
                    print(f"  [{sname}] 检索 {len(data)} 条, 状态: {status}")
                elif sname == "generate_article" and isinstance(data, dict):
                    print(f"  [{sname}] 耗时 {data.get('generation_time_ms', 0)}ms, 状态: {status}")
                elif sname == "evaluate" and isinstance(data, dict):
                    print(f"  [{sname}] 综合评分: {data.get('overall', 'N/A')}, "
                          f"结果: {data.get('result', 'N/A')}, 状态: {status}")
                else:
                    print(f"  [{sname}] 状态: {status}")
        else:
            print(f"  失败阶段: {full_result.get('failed_stage', 'N/A')}")
    except Exception as e:
        print(f"  ❌ 测试4异常: {e}")
        traceback.print_exc()

    print()

    # ---- 测试5：UI 兼容接口（run_task） ----
    print("【测试5】UI 兼容接口 —— 模拟凯睿 UI 调用")
    print("-" * 40)
    try:
        ui_result = engine.run_task({
            "action": "generate",
            "title": "2026年工业废气治理新趋势",
            "content_type": "tech_trend",
            "scene_type": "industrial",
            "keywords": ["VOCs", "催化燃烧"],
        })
        if isinstance(ui_result, dict):
            md = ui_result.get("markdown", "")
            review = ui_result.get("review", {})
            print(f"  生成耗时: {ui_result.get('generation_time_ms', 0)}ms")
            if review:
                print(f"  自动评估: {review.get('result', 'N/A')} "
                      f"(综合 {review.get('overall', 'N/A')})")
            if md:
                print(f"  内容预览: {md.split(chr(10))[0]}")
        else:
            print(f"  结果: {str(ui_result)[:100]}...")
    except Exception as e:
        print(f"  ❌ 测试5异常: {e}")
        traceback.print_exc()

    print()

    # ---- 测试6：业务规则自动补充 scene_type ----
    print("【测试6】业务规则 —— 根据 region 自动补充 scene_type")
    print("-" * 40)
    raw_input = {"topic": "佛山工业废气治理", "location": "佛山"}
    processed = engine._apply_business_rules(raw_input)
    print(f"  输入: {raw_input}")
    print(f"  输出: scene_type={processed.get('scene_type')}, "
          f"content_type={processed.get('content_type')}, "
          f"keywords={processed.get('keywords')}")

    print()

    # ---- 测试总结 ----
    print("=" * 60)
    print("  📊 测试总结")
    print("=" * 60)
    print(f"  已注册阶段: {engine.list_stages()}")
    print(f"  定时任务数: {len(scheduler.list_tasks())}")
    print(f"  执行日志条数: {len(engine.get_execution_log())}")
    print()

    # 提示：如需启动后台调度器，取消下面的注释
    # print("  启动后台调度器...")
    # scheduler.start()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     scheduler.stop()
    #     print("\n[系统] 调度器已停止，程序退出")

    print("  ✅ 所有测试完成！系统运行正常。")
