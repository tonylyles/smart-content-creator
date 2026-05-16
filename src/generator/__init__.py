"""generator子模块 - 刘凯睿负责

包含：
- ContentGenerator: 内容生成器（主模块，从 generator.py 导入）
- layout_engine: 排版权式引擎
- multimodal_processor: 多模态处理器
"""
import importlib
import importlib.util
import sys
from pathlib import Path

# 导入子模块
from src.generator.layout_engine import LayoutEngine
from src.generator.multimodal_processor import MultimodalProcessor

# 从上级 generator.py 导入 ContentGenerator
# 由于 generator/ 目录的 __init__.py 会遮蔽 generator.py，
# 需要用 importlib 直接加载源文件
_generator_py = Path(__file__).resolve().parent.parent / "generator.py"
if _generator_py.exists():
    _spec = importlib.util.spec_from_file_location(
        "src._generator_module", str(_generator_py)
    )
    _generator_mod = importlib.util.module_from_spec(_spec)
    sys.modules["src._generator_module"] = _generator_mod
    _spec.loader.exec_module(_generator_mod)
    ContentGenerator = _generator_mod.ContentGenerator
else:
    ContentGenerator = None

__all__ = ["ContentGenerator", "LayoutEngine", "MultimodalProcessor"]
