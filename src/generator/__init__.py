"""generator子模块 - 刘凯睿负责

包含：
- layout_engine: 排版权式引擎
- multimodal_processor: 多模态处理器
"""
from src.generator.layout_engine import LayoutEngine
from src.generator.multimodal_processor import MultimodalProcessor

__all__ = ["LayoutEngine", "MultimodalProcessor"]
