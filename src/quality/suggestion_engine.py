"""修改建议引擎 - 刘凯睿负责

功能：
- 基于多维度评估结果生成修改建议
- 优先级排序（按影响程度）
- 分类建议（内容/结构/合规/品牌）
- 可操作的具体修改指令
- 建议采纳追踪
"""
import re
from typing import Dict, List, Optional, Tuple

from src.quality.term_checker import TermChecker
from src.quality.logic_analyzer import LogicAnalyzer
from src.quality.readability_eval import ReadabilityEvaluator


# ==================== 建议优先级 ====================

PRIORITY_LEVELS = {
    "critical": {"label": "🔴 严重", "weight": 1.0},
    "important": {"label": "🟡 重要", "weight": 0.7},
    "suggestion": {"label": "🔵 建议", "weight": 0.4},
    "minor": {"label": "⚪ 微调", "weight": 0.2},
}

# 建议分类
SUGGESTION_CATEGORIES = {
    "compliance": "合规性",
    "accuracy": "准确性",
    "readability": "可读性",
    "brand": "品牌调性",
    "structure": "内容结构",
    "terminology": "术语规范",
    "logic": "逻辑一致性",
    "layout": "排版规范",
}


class SuggestionEngine:
    """修改建议引擎.

    整合术语检查、逻辑分析、可读性评估的结果，
    生成优先级排序、分类明确、可操作的修改建议。

    Attributes:
        term_checker: 术语检查器.
        logic_analyzer: 逻辑分析器.
        readability_eval: 可读性评估器.
        scene_type: 场景类型.
    """

    def __init__(self, scene_type: str = "municipal"):
        """初始化修改建议引擎.

        Args:
            scene_type: 场景类型.
        """
        self.scene_type = scene_type
        self.term_checker = TermChecker(scene_type)
        self.logic_analyzer = LogicAnalyzer(scene_type)
        self.readability_eval = ReadabilityEvaluator(scene_type)

    def generate_suggestions(self, content: str, title: str = "",
                             evaluation_result: dict = None) -> dict:
        """生成完整的修改建议.

        Args:
            content: 文章内容.
            title: 文章标题.
            evaluation_result: 外部评估结果（可选，用于增强建议）.

        Returns:
            dict: {
                "total_suggestions": int,
                "suggestions": list[dict],
                "priority_summary": dict,
                "category_summary": dict,
                "action_plan": str
            }
        """
        suggestions = []

        # 1. 术语检查
        term_result = self.term_checker.check(content, title)
        suggestions.extend(self._term_to_suggestions(term_result))

        # 2. 逻辑分析
        logic_result = self.logic_analyzer.analyze(content, title)
        suggestions.extend(self._logic_to_suggestions(logic_result))

        # 3. 可读性评估
        read_result = self.readability_eval.evaluate(content, title)
        suggestions.extend(self._readability_to_suggestions(read_result))

        # 4. 整合外部评估结果
        if evaluation_result:
            suggestions.extend(self._eval_to_suggestions(evaluation_result))

        # 按优先级排序
        suggestions.sort(key=lambda s: PRIORITY_LEVELS[s["priority"]]["weight"], reverse=True)

        # 去重
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            key = f"{s['category']}:{s['message']}"
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)

        # 生成摘要
        priority_summary = self._summarize_by_priority(unique_suggestions)
        category_summary = self._summarize_by_category(unique_suggestions)
        action_plan = self._generate_action_plan(unique_suggestions)

        return {
            "total_suggestions": len(unique_suggestions),
            "suggestions": unique_suggestions,
            "priority_summary": priority_summary,
            "category_summary": category_summary,
            "action_plan": action_plan,
        }

    def _term_to_suggestions(self, term_result: dict) -> List[dict]:
        """将术语检查结果转为建议.

        Args:
            term_result: 术语检查结果.

        Returns:
            list[dict]: 建议列表.
        """
        suggestions = []

        # 术语纠正
        for corr in term_result.get("corrections", []):
            suggestions.append({
                "priority": "critical",
                "category": "terminology",
                "message": f"术语'{corr['term']}'建议修正为：{corr['suggestion']}",
                "action": f"将'{corr['term']}'替换为标准表述",
                "location": corr.get("position", "正文"),
            })

        # 缺少核心术语
        core_terms = self.term_checker._get_core_terms()
        for term in term_result.get("missing_terms", []):
            if term in core_terms:
                priority = "important"
                action = f"在相关段落中自然融入术语'{term}'"
            else:
                priority = "suggestion"
                action = f"可选择性补充术语'{term}'"
            suggestions.append({
                "priority": priority,
                "category": "terminology",
                "message": f"缺少专业术语'{term}'",
                "action": action,
                "location": "全文",
            })

        # 禁止缩写
        for abbr in term_result.get("forbidden_abbreviations", []):
            suggestions.append({
                "priority": "important",
                "category": "terminology",
                "message": f"使用了非规范缩写'{abbr['abbreviation']}'",
                "action": abbr["full_form"],
                "location": "正文",
            })

        return suggestions

    def _logic_to_suggestions(self, logic_result: dict) -> List[dict]:
        """将逻辑分析结果转为建议.

        Args:
            logic_result: 逻辑分析结果.

        Returns:
            list[dict]: 建议列表.
        """
        suggestions = []

        # 数值矛盾
        for contra in logic_result.get("contradictions", []):
            suggestions.append({
                "priority": "critical",
                "category": "logic",
                "message": f"{contra['indicator']}数值矛盾：{', '.join(contra['values'])}",
                "action": f"统一{contra['indicator']}的数值表述，{contra['context']}",
                "location": "全文",
            })

        # 论证链缺失
        for gap in logic_result.get("argumentation_gaps", []):
            suggestions.append({
                "priority": "important",
                "category": "structure",
                "message": gap,
                "action": gap,
                "location": "相关段落",
            })

        # 时序矛盾
        for temporal in logic_result.get("temporal_issues", []):
            suggestions.append({
                "priority": "important",
                "category": "logic",
                "message": temporal["issue"],
                "action": temporal["detail"],
                "location": "相关段落",
            })

        # 品牌一致性
        brand = logic_result.get("brand_consistency", {})
        for conflict in brand.get("conflicts", []):
            suggestions.append({
                "priority": "critical",
                "category": "brand",
                "message": conflict,
                "action": "删除或修改与品牌形象矛盾的表述",
                "location": "正文",
            })

        return suggestions

    def _readability_to_suggestions(self, read_result: dict) -> List[dict]:
        """将可读性评估结果转为建议.

        Args:
            read_result: 可读性评估结果.

        Returns:
            list[dict]: 建议列表.
        """
        suggestions = []

        para = read_result.get("paragraph_analysis", {})
        if para.get("long_count", 0) > 0:
            suggestions.append({
                "priority": "important",
                "category": "readability",
                "message": f"有{para['long_count']}个段落超过{PARAGRAPH_LENGTH['too_long']}字，影响阅读体验",
                "action": "将长段落拆分为2-3个短段落",
                "location": "长段落处",
            })

        sent = read_result.get("sentence_analysis", {})
        if sent.get("long_ratio", 0) > 0.3:
            suggestions.append({
                "priority": "important",
                "category": "readability",
                "message": f"长句占比{sent['long_ratio']:.0%}，高于建议的30%",
                "action": "将超过80字的长句拆分为短句",
                "location": "长句处",
            })

        layout = read_result.get("layout_score", {})
        if layout.get("heading_count", 0) < 3:
            suggestions.append({
                "priority": "suggestion",
                "category": "layout",
                "message": f"仅{layout['heading_count']}个小标题，建议增加结构层次",
                "action": "每2-4个段落添加一个小标题",
                "location": "全文",
            })

        if layout.get("table_count", 0) == 0 and len(str(read_result)) > 200:
            suggestions.append({
                "priority": "minor",
                "category": "layout",
                "message": "建议使用表格展示对比数据",
                "action": "将数值对比信息整理为表格形式",
                "location": "数据密集处",
            })

        return suggestions

    def _eval_to_suggestions(self, evaluation_result: dict) -> List[dict]:
        """将外部评估结果转为建议.

        Args:
            evaluation_result: 外部评估结果.

        Returns:
            list[dict]: 建议列表.
        """
        suggestions = []

        # 合规性
        if evaluation_result.get("compliance_score", 1.0) < 0.8:
            suggestions.append({
                "priority": "critical",
                "category": "compliance",
                "message": "合规性评分低于0.8，存在广告法风险",
                "action": "检查并替换违禁词汇",
                "location": "全文",
            })

        # 准确性
        if evaluation_result.get("accuracy_score", 1.0) < 0.8:
            suggestions.append({
                "priority": "important",
                "category": "accuracy",
                "message": "技术准确性不足",
                "action": "补充专业术语和量化数据",
                "location": "技术描述段落",
            })

        # 品牌匹配
        if evaluation_result.get("brand_alignment_score", 1.0) < 0.8:
            suggestions.append({
                "priority": "important",
                "category": "brand",
                "message": "品牌调性匹配度不足",
                "action": "增加'吉康环境'品牌元素和技术实力描述",
                "location": "全文",
            })

        return suggestions

    def _summarize_by_priority(self, suggestions: List[dict]) -> dict:
        """按优先级汇总建议.

        Args:
            suggestions: 建议列表.

        Returns:
            dict: {优先级: 数量}.
        """
        summary = {}
        for level in PRIORITY_LEVELS:
            count = sum(1 for s in suggestions if s["priority"] == level)
            if count > 0:
                summary[level] = {
                    "label": PRIORITY_LEVELS[level]["label"],
                    "count": count,
                }
        return summary

    def _summarize_by_category(self, suggestions: List[dict]) -> dict:
        """按分类汇总建议.

        Args:
            suggestions: 建议列表.

        Returns:
            dict: {分类: 数量}.
        """
        summary = {}
        for s in suggestions:
            cat = s["category"]
            cat_label = SUGGESTION_CATEGORIES.get(cat, cat)
            if cat_label not in summary:
                summary[cat_label] = 0
            summary[cat_label] += 1
        return summary

    def _generate_action_plan(self, suggestions: List[dict]) -> str:
        """生成修改行动计划.

        Args:
            suggestions: 建议列表.

        Returns:
            str: 行动计划文本.
        """
        if not suggestions:
            return "✅ 内容质量良好，无需修改。"

        lines = ["📝 修改行动计划：", ""]

        # 按优先级分组
        for level in ["critical", "important", "suggestion", "minor"]:
            level_suggestions = [s for s in suggestions if s["priority"] == level]
            if not level_suggestions:
                continue

            label = PRIORITY_LEVELS[level]["label"]
            lines.append(f"{label} ({len(level_suggestions)}项)：")
            for i, s in enumerate(level_suggestions, 1):
                lines.append(f"  {i}. [{SUGGESTION_CATEGORIES.get(s['category'], s['category'])}] {s['action']}")
            lines.append("")

        return "\n".join(lines)
