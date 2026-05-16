"""对接验证脚本 - 验证曾睿/凯睿模块对接是否正常"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("  对接验证 - 刘凯睿 <-> 曾睿")
print("=" * 60)

errors = []

# 1. 验证 WorkflowEngine.set_pipeline 方法
print("\n[验证 1] WorkflowEngine.set_pipeline() 方法...")
try:
    from src.workflow import WorkflowEngine
    engine = WorkflowEngine()
    assert hasattr(engine, 'set_pipeline'), "缺少 set_pipeline 方法"
    assert hasattr(engine, 'run_full_pipeline'), "缺少 run_full_pipeline 方法"
    print("  ✅ WorkflowEngine 包含 set_pipeline + run_full_pipeline")
except Exception as e:
    errors.append(f"WorkflowEngine: {e}")
    print(f"  ❌ {e}")

# 2. 验证 run_task 支持 "run_pipeline" action
print("\n[验证 2] run_task('run_pipeline') action...")
try:
    engine = WorkflowEngine()
    # 不注入 pipeline 时应返回错误提示
    result = engine.run_task({"action": "run_pipeline", "topic": "测试"})
    assert result.get("status") == "error", f"应为 error，实际: {result}"
    print("  ✅ run_task 正确处理 run_pipeline action（Pipeline 未注入时返回错误）")
except Exception as e:
    errors.append(f"run_task: {e}")
    print(f"  ❌ {e}")

# 3. 验证 TaskScheduler.init_pipeline()
print("\n[验证 3] TaskScheduler.init_pipeline()...")
try:
    from src.scheduler import TaskScheduler
    scheduler = TaskScheduler()
    assert hasattr(scheduler, 'init_pipeline'), "缺少 init_pipeline 方法"
    assert hasattr(scheduler, 'run_pipeline_now'), "缺少 run_pipeline_now 方法"
    print("  ✅ TaskScheduler 包含 init_pipeline + run_pipeline_now")
except Exception as e:
    errors.append(f"TaskScheduler: {e}")
    print(f"  ❌ {e}")

# 4. 验证 Pipeline 端到端（Mock 模式）
print("\n[验证 4] Pipeline 端到端（Mock 模式）...")
try:
    from src.scheduler import TaskScheduler
    scheduler = TaskScheduler()

    # Mock 组件
    class MockGen:
        def generate(self, topic, **kwargs):
            return {"markdown": f"# {topic}\n\nMock 生成", "html": "", "generation_time_ms": 50}
        def regenerate(self, original_title, original_content, evaluation_result, scene_type="municipal"):
            return {"markdown": f"# {original_title}(修订)", "html": "", "generation_time_ms": 30}
    class MockEval:
        def evaluate(self, content, title="", scene_type="municipal"):
            return {"accuracy_score": 0.96, "compliance_score": 0.95, "overall": 0.92,
                    "result": "pass", "comments": "通过", "suggestions": []}

    scheduler.init_pipeline(generator=MockGen(), evaluator=MockEval())
    report = scheduler.run_pipeline_now(topic="对接测试", scene_type="municipal")
    assert report["status"] == "success", f"Pipeline 应成功: {report['status']}"
    assert report["sla_pass"], "SLA 应达标"
    print(f"  ✅ Pipeline 执行成功，耗时 {report['total_duration_ms']}ms")
except Exception as e:
    errors.append(f"Pipeline: {e}")
    print(f"  ❌ {e}")

# 5. 验证 WorkflowEngine + Pipeline 对接
print("\n[验证 5] WorkflowEngine.run_full_pipeline()...")
try:
    from src.workflow import WorkflowEngine
    from src.scheduler import TaskScheduler, ContentPipeline

    engine = WorkflowEngine()
    pipeline = ContentPipeline(
        generator=MockGen(),
        evaluator=MockEval(),
    )
    engine.set_pipeline(pipeline)
    report = engine.run_full_pipeline(topic="引擎对接测试")
    assert report["status"] == "success", f"应成功: {report['status']}"
    print(f"  ✅ 通过 WorkflowEngine 触发 Pipeline 成功")
except Exception as e:
    errors.append(f"Engine+Pipeline: {e}")
    print(f"  ❌ {e}")

# 6. 验证 UI 的 scheduler 参数
print("\n[验证 6] UI 调度面板（scheduler 参数）...")
try:
    from src.ui import AppUI
    engine = WorkflowEngine()
    # 不传 scheduler 应不报错（向后兼容）
    ui = AppUI(workflow_engine=engine, config={})
    assert ui.scheduler is None, "默认 scheduler 应为 None"
    # 传 scheduler
    scheduler = TaskScheduler()
    ui2 = AppUI(workflow_engine=engine, config={}, scheduler=scheduler)
    assert ui2.scheduler is scheduler, "scheduler 应被正确传入"
    print("  ✅ AppUI 支持可选 scheduler 参数（向后兼容）")
except Exception as e:
    errors.append(f"UI: {e}")
    print(f"  ❌ {e}")

# 7. 验证接口签名匹配
print("\n[验证 7] 接口签名匹配检查...")
try:
    from src.generator import ContentGenerator
    from src.evaluator import Evaluator
    import inspect

    # generate(topic, context, content_type, scene_type, keywords, custom_instructions, reference, timeline)
    gen_sig = inspect.signature(ContentGenerator.generate)
    gen_params = list(gen_sig.parameters.keys())
    assert "topic" in gen_params, "generate 缺少 topic 参数"
    assert "timeline" in gen_params, "generate 缺少 timeline 参数"
    print("  ✅ ContentGenerator.generate() 签名匹配")

    # regenerate(original_title, original_content, evaluation_result, scene_type)
    regen_sig = inspect.signature(ContentGenerator.regenerate)
    regen_params = list(regen_sig.parameters.keys())
    assert "original_title" in regen_params, "regenerate 缺少 original_title"
    assert "evaluation_result" in regen_params, "regenerate 缺少 evaluation_result"
    print("  ✅ ContentGenerator.regenerate() 签名匹配")

    # evaluate(content, title, scene_type)
    eval_sig = inspect.signature(Evaluator.evaluate)
    eval_params = list(eval_sig.parameters.keys())
    assert "content" in eval_params, "evaluate 缺少 content"
    assert "title" in eval_params, "evaluate 缺少 title"
    print("  ✅ Evaluator.evaluate() 签名匹配")

except Exception as e:
    errors.append(f"接口签名: {e}")
    print(f"  ❌ {e}")

# 总结
print("\n" + "=" * 60)
if not errors:
    print("  ✅ 全部 7 项验证通过！对接完成。")
else:
    print(f"  ❌ {len(errors)} 项验证失败：")
    for err in errors:
        print(f"    - {err}")
print("=" * 60)
