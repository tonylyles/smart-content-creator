"""逻辑一致性分析器 - 刘凯睿负责

功能：
- 数据前后矛盾检测
- 论证逻辑链完整性检查
- 因果关系合理性校验
- 时序一致性检查
- 品牌主张一致性
"""
import re
from typing import Dict, List, Optional, Tuple


# ==================== 逻辑规则定义 ====================

# 数值矛盾检测模式：同一指标出现不同数值
NUMERIC_PATTERNS = [
    (r'(\d+\.?\d*)\s*%', r'百分比数值'),
    (r'(\d+\.?\d*)\s*mg/L', r'浓度数值'),
    (r'(\d+\.?\d*)\s*吨', r'吨位数值'),
    (r'(\d+\.?\d*)\s*万元', r'金额数值'),
    (r'(\d+\.?\d*)\s*亿元', r'金额数值'),
]

# 品牌核心主张（不可矛盾）
BRAND_CLAIMS = {
    "positive": [
        "技术实力", "创新驱动", "行业前沿", "稳定达标",
        "客户满意", "绿色生产力", "循环经济",
    ],
    "negative": [
        "无法达标", "技术落后", "频繁故障", "投诉多",
    ],
}

# 论证结构关键词
ARGUMENTATION_KEYWORDS = {
    "cause": ["因为", "由于", "原因是", "基于", "鉴于"],
    "effect": ["因此", "所以", "导致", "使得", "从而", "进而"],
    "evidence": ["数据显示", "据统计", "案例表明", "实践证明", "研究显示"],
    "conclusion": ["综上", "总之", "可见", "可以看出", "这表明"],
}

# 时序标记
TEMPORAL_MARKERS = {
    "past": ["已", "曾经", "此前", "去年", "上半年"],
    "present": ["目前", "当前", "现", "正在", "今"],
    "future": ["将", "预计", "计划", "未来", "下一步"],
}


class LogicAnalyzer:
    """逻辑一致性分析器.

    检查内容的逻辑一致性，包括：
    - 数值前后矛盾
    - 论证链完整性
    - 因果关系合理性
    - 时序一致性
    - 品牌主张一致性

    Attributes:
        scene_type: 当前场景类型.
    """

    def __init__(self, scene_type: str = "municipal"):
        """初始化逻辑分析器.

        Args:
            scene_type: 场景类型.
        """
        self.scene_type = scene_type

    def analyze(self, content: str, title: str = "") -> dict:
        """执行完整的逻辑一致性分析.

        Args:
            content: 文章内容.
            title: 文章标题.

        Returns:
            dict: {
                "score": float,
                "contradictions": list[dict],
                "argumentation_gaps": list[str],
                "temporal_issues": list[dict],
                "brand_consistency": dict,
                "summary": str
            }
        """
        contradictions = self._check_contradictions(content, title)
        arg_gaps = self._check_argumentation(content)
        temporal = self._check_temporal(content)
        brand = self._check_brand_consistency(content)

        # 计算得分
        base_score = 0.85
        base_score -= min(0.20, len(contradictions) * 0.08)
        base_score -= min(0.10, len(arg_gaps) * 0.03)
        base_score -= min(0.10, len(temporal) * 0.05)
        if not brand["consistent"]:
            base_score -= 0.10

        score = round(max(0.0, min(1.0, base_score)), 2)

        # 摘要
        parts = []
        if contradictions:
            parts.append(f"发现 {len(contradictions)} 处数值矛盾")
        if arg_gaps:
            parts.append(f"论证链有 {len(arg_gaps)} 处缺失")
        if temporal:
            parts.append(f"时序有 {len(temporal)} 处不一致")
        if not brand["consistent"]:
            parts.append("品牌主张存在矛盾")
        if not parts:
            parts.append("逻辑一致性良好")
        summary = "；".join(parts)

        return {
            "score": score,
            "contradictions": contradictions,
            "argumentation_gaps": arg_gaps,
            "temporal_issues": temporal,
            "brand_consistency": brand,
            "summary": summary,
        }

    def _check_contradictions(self, content: str, title: str) -> List[dict]:
        """检查数值前后矛盾.

        检测同一指标在文中出现不同数值的情况.

        Args:
            content: 文章内容.
            title: 文章标题.

        Returns:
            list[dict]: [{"indicator": str, "values": list[str], "context": str}]
        """
        contradictions = []

        # 检测达标率矛盾
        compliance_pattern = r'达标率[^\d]*(\d+\.?\d*)\s*[%％]'
        matches = re.findall(compliance_pattern, content)
        if len(set(matches)) > 1:
            contradictions.append({
                "indicator": "达标率",
                "values": list(set(matches)),
                "context": "文中出现多个不同的达标率数值",
            })

        # 检测成本降低矛盾
        cost_pattern = r'成本[降减]低[^\d]*(\d+\.?\d*)\s*[%％]'
        matches = re.findall(cost_pattern, content)
        if len(set(matches)) > 1:
            contradictions.append({
                "indicator": "成本降低",
                "values": list(set(matches)),
                "context": "文中出现多个不同的成本降低比例",
            })

        # 检测效率提升矛盾
        efficiency_pattern = r'(?:效率|处理效果)[提增升][^\d]*(\d+\.?\d*)\s*[%％]'
        matches = re.findall(efficiency_pattern, content)
        if len(set(matches)) > 1:
            contradictions.append({
                "indicator": "效率提升",
                "values": list(set(matches)),
                "context": "文中出现多个不同的效率提升比例",
            })

        return contradictions

    def _check_argumentation(self, content: str) -> List[str]:
        """检查论证链完整性.

        检测因果论证结构是否完整：有因无果或有果无因.

        Args:
            content: 文章内容.

        Returns:
            list[str]: 缺失项描述列表.
        """
        gaps = []

        has_cause = any(kw in content for kw in ARGUMENTATION_KEYWORDS["cause"])
        has_effect = any(kw in content for kw in ARGUMENTATION_KEYWORDS["effect"])
        has_evidence = any(kw in content for kw in ARGUMENTATION_KEYWORDS["evidence"])
        has_conclusion = any(kw in content for kw in ARGUMENTATION_KEYWORDS["conclusion"])

        if has_cause and not has_effect:
            gaps.append("有原因分析但缺少结果推导（建议补充'因此/所以'等因果衔接）")
        if has_effect and not has_cause:
            gaps.append("有结论推导但缺少原因分析（建议补充数据或论据支撑）")
        if not has_evidence and len(content) > 500:
            gaps.append("缺乏数据/案例支撑（建议补充'数据显示/案例表明'等实证引用）")
        if has_cause and has_effect and not has_conclusion:
            gaps.append("有论证过程但缺少总结（建议补充'综上/可见'等总结性语句）")

        return gaps

    def _check_temporal(self, content: str) -> List[dict]:
        """检查时序一致性.

        检测时序矛盾，如"已建成"与"计划建设"的冲突.

        Args:
            content: 文章内容.

        Returns:
            list[dict]: [{"issue": str, "detail": str}]
        """
        issues = []

        # 检测同一项目的时序矛盾
        project_patterns = [
            (r'已[建成完工]', "past"),
            (r'计划[建设投]', "future"),
            (r'预计[将达到]', "future"),
        ]

        # 找项目关键词附近的时序标记
        lines = content.split("\n")
        project_mentions = {}
        for line in lines:
            for pattern, tense in project_patterns:
                if re.search(pattern, line):
                    # 提取项目关键词
                    proj_match = re.search(r'([\u4e00-\u9fff]{2,6}(?:项目|工程|设施|系统))', line)
                    if proj_match:
                        proj_name = proj_match.group(1)
                        if proj_name not in project_mentions:
                            project_mentions[proj_name] = []
                        project_mentions[proj_name].append({
                            "tense": tense,
                            "line": line.strip()[:80],
                        })

        # 检查同一项目是否有时序矛盾
        for proj, mentions in project_mentions.items():
            tenses = set(m["tense"] for m in mentions)
            if "past" in tenses and "future" in tenses:
                issues.append({
                    "issue": f"'{proj}'时序矛盾",
                    "detail": "同一项目既有'已完成'又有'计划中'表述，请确认时序",
                })

        return issues

    def _check_brand_consistency(self, content: str) -> dict:
        """检查品牌主张一致性.

        确保文中没有与品牌核心价值相矛盾的表述.

        Args:
            content: 文章内容.

        Returns:
            dict: {"consistent": bool, "conflicts": list[str]}
        """
        conflicts = []

        # 检查是否出现与品牌主张矛盾的表述
        for neg_term in BRAND_CLAIMS["negative"]:
            if neg_term in content:
                conflicts.append(f"出现与品牌形象矛盾的表述：'{neg_term}'")

        # 检查品牌主张是否出现
        positive_found = [p for p in BRAND_CLAIMS["positive"] if p in content]

        return {
            "consistent": len(conflicts) == 0,
            "conflicts": conflicts,
            "positive_claims_found": positive_found,
            "positive_claims_count": len(positive_found),
        }
