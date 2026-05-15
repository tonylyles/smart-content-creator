"""术语规范检查器 - 刘凯睿负责

功能：
- 专业术语拼写/用法校验
- 行业标准术语规范检查
- 术语上下文一致性校验
- 中英文术语对照验证
- 场景化术语推荐
"""
import re
from typing import Dict, List, Optional, Tuple


# ==================== 术语规范库 ====================

# 标准术语映射：常见错误写法 → 标准写法
TERM_CORRECTIONS = {
    # 市政环保
    "污水处理场": "污水处理厂",
    "污水厂": "污水处理厂",
    "排水厂": "污水处理厂",
    "雨污合流": "雨污分流（应为分流制）",
    "COD去除": "COD去除率",
    "氨氮去除": "氨氮去除率",
    # 工业环保
    "VOC": "VOCs（挥发性有机物，英文缩写应带s）",
    "voc": "VOCs",
    "零排放": "零排放（需注明是废水零排放或固废零排放）",
    "危废": "危险废物（正式文件中应使用全称）",
    # 通用
    "脱硫脱硝": "脱硫脱硝（建议明确顺序：先脱硫后脱硝）",
    "中水": "再生水（行业标准术语）",
    "污泥处置": "污泥处理处置（处理+处置是完整流程）",
}

# 场景标准术语库
SCENE_STANDARD_TERMS = {
    "municipal": {
        "core": [
            "污水处理厂", "固废处理", "环境监测", "雨污分流",
            "提标改造", "再生水", "污泥处理处置", "黑臭水体",
        ],
        "process": [
            "A²O", "MBR", "MBBR", "SBR", "CAST",
            "生化处理", "深度处理", "膜过滤", "活性炭吸附",
        ],
        "indicator": [
            "COD", "BOD₅", "氨氮", "总磷", "总氮", "SS",
            "pH", "溶解氧", "大肠菌群",
        ],
    },
    "industrial": {
        "core": [
            "VOCs", "废气治理", "废水零排放", "危险废物",
            "清洁生产", "环境影响评价", "排污许可",
        ],
        "process": [
            "催化燃烧", "RTO", "RCO", "活性炭吸附脱附",
            "反渗透", "蒸发结晶", "DTRO", "EDR", "MVR",
        ],
        "indicator": [
            "NMHC", "颗粒物", "SO₂", "NOx",
            "COD", "氨氮", "特征污染物",
        ],
    },
}

# 中英文术语对照
TERM_BILINGUAL = {
    "污水处理": "Wastewater Treatment",
    "固废处理": "Solid Waste Treatment",
    "环境监测": "Environmental Monitoring",
    "VOCs": "Volatile Organic Compounds",
    "危险废物": "Hazardous Waste",
    "清洁生产": "Cleaner Production",
    "环境影响评价": "Environmental Impact Assessment (EIA)",
    "排污许可": "Pollutant Discharge Permit",
    "再生水": "Reclaimed Water",
    "膜生物反应器": "Membrane Bioreactor (MBR)",
    "移动床生物膜反应器": "Moving Bed Biofilm Reactor (MBBR)",
}

# 禁止使用的非规范缩写
FORBIDDEN_ABBREVIATIONS = {
    "环评": "环境影响评价（首次出现应使用全称）",
    "危废": "危险废物（正式文档应使用全称）",
    "固废": "固体废物（正式文档应使用全称）",
    "排污": "污染物排放（应明确表述）",
}


class TermChecker:
    """术语规范检查器.

    检查内容中的专业术语是否符合行业规范，包括：
    - 术语拼写/用法校验
    - 场景化术语覆盖度
    - 中英文术语对照
    - 非规范缩写检测

    Attributes:
        scene_type: 当前场景类型.
    """

    def __init__(self, scene_type: str = "municipal"):
        """初始化术语检查器.

        Args:
            scene_type: 场景类型，可选值：municipal/industrial.
        """
        self.scene_type = scene_type

    def check(self, content: str, title: str = "") -> dict:
        """执行完整的术语规范检查.

        Args:
            content: 文章内容.
            title: 文章标题.

        Returns:
            dict: {
                "score": float,
                "corrections": list[dict],
                "missing_terms": list[str],
                "forbidden_abbreviations": list[dict],
                "bilingual_coverage": float,
                "summary": str
            }
        """
        corrections = self._check_corrections(content, title)
        missing = self._check_missing_terms(content)
        forbidden = self._check_forbidden_abbreviations(content)
        biling_score = self._check_bilingual(content)

        # 计算综合得分
        base_score = 0.80
        # 有纠正项则扣分
        base_score -= min(0.20, len(corrections) * 0.04)
        # 缺少核心术语扣分
        core_missing = [t for t in missing if t in self._get_core_terms()]
        base_score -= min(0.15, len(core_missing) * 0.03)
        # 有禁止缩写扣分
        base_score -= min(0.10, len(forbidden) * 0.03)
        # 双语覆盖加分
        base_score += biling_score * 0.05

        score = round(max(0.0, min(1.0, base_score)), 2)

        # 生成摘要
        parts = []
        if corrections:
            parts.append(f"发现 {len(corrections)} 处术语用法需修正")
        if core_missing:
            parts.append(f"缺少 {len(core_missing)} 个核心术语")
        if forbidden:
            parts.append(f"发现 {len(forbidden)} 处非规范缩写")
        if not parts:
            parts.append("术语使用规范，未发现问题")
        summary = "；".join(parts)

        return {
            "score": score,
            "corrections": corrections,
            "missing_terms": missing,
            "forbidden_abbreviations": forbidden,
            "bilingual_coverage": round(biling_score, 2),
            "summary": summary,
        }

    def _check_corrections(self, content: str, title: str) -> List[dict]:
        """检查术语拼写/用法纠正.

        Args:
            content: 文章内容.
            title: 文章标题.

        Returns:
            list[dict]: [{"term": str, "suggestion": str, "position": str}]
        """
        full_text = title + " " + content
        results = []
        for wrong, correct in TERM_CORRECTIONS.items():
            if wrong in full_text:
                results.append({
                    "term": wrong,
                    "suggestion": correct,
                    "position": "标题" if wrong in title else "正文",
                })
        return results

    def _check_missing_terms(self, content: str) -> List[str]:
        """检查缺少的核心术语.

        Args:
            content: 文章内容.

        Returns:
            list[str]: 缺少的术语列表.
        """
        scene_terms = SCENE_STANDARD_TERMS.get(self.scene_type, {})
        all_terms = []
        for category in scene_terms.values():
            all_terms.extend(category)
        return [t for t in all_terms if t not in content]

    def _check_forbidden_abbreviations(self, content: str) -> List[dict]:
        """检查非规范缩写.

        Args:
            content: 文章内容.

        Returns:
            list[dict]: [{"abbreviation": str, "full_form": str}]
        """
        results = []
        for abbr, full_form in FORBIDDEN_ABBREVIATIONS.items():
            if abbr in content:
                results.append({
                    "abbreviation": abbr,
                    "full_form": full_form,
                })
        return results

    def _check_bilingual(self, content: str) -> float:
        """检查中英文术语对照覆盖度.

        如果文章中出现了中文术语，建议附带英文对照.

        Args:
            content: 文章内容.

        Returns:
            float: 双语覆盖率（0~1）.
        """
        if not TERM_BILINGUAL:
            return 0.0
        found = 0
        for cn_term in TERM_BILINGUAL:
            en_term = TERM_BILINGUAL[cn_term]
            if cn_term in content and en_term.split("(")[0].strip() in content:
                found += 1
        total = sum(1 for cn in TERM_BILINGUAL if cn in content)
        return found / total if total > 0 else 0.5

    def _get_core_terms(self) -> List[str]:
        """获取当前场景的核心术语列表.

        Returns:
            list[str]: 核心术语列表.
        """
        scene_terms = SCENE_STANDARD_TERMS.get(self.scene_type, {})
        return scene_terms.get("core", [])

    def get_term_suggestions(self, content: str, top_k: int = 5) -> List[dict]:
        """获取术语补充建议.

        根据内容已使用的术语，推荐相关但缺失的术语.

        Args:
            content: 文章内容.
            top_k: 返回数量.

        Returns:
            list[dict]: [{"term": str, "category": str, "reason": str}]
        """
        scene_terms = SCENE_STANDARD_TERMS.get(self.scene_type, {})
        suggestions = []

        for category, terms in scene_terms.items():
            for term in terms:
                if term not in content:
                    cat_label = {
                        "core": "核心术语",
                        "process": "工艺技术",
                        "indicator": "指标参数",
                    }.get(category, category)
                    suggestions.append({
                        "term": term,
                        "category": cat_label,
                        "reason": f"当前场景{cat_label}，建议补充",
                    })

        return suggestions[:top_k]
