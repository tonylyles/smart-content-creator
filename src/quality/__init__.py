"""质量评估子模块 - 刘凯睿负责

包含：
- term_checker: 术语规范检查器
- logic_analyzer: 逻辑一致性分析器
- readability_eval: 可读性评估器
- suggestion_engine: 修改建议引擎
"""
from src.quality.term_checker import TermChecker
from src.quality.logic_analyzer import LogicAnalyzer
from src.quality.readability_eval import ReadabilityEvaluator
from src.quality.suggestion_engine import SuggestionEngine

__all__ = ["TermChecker", "LogicAnalyzer", "ReadabilityEvaluator", "SuggestionEngine"]
