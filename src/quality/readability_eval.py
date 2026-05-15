"""可读性评估器 - 刘凯睿负责

功能：
- 中文文本可读性评分
- 段落结构分析
- 句子复杂度评估
- 信息密度计算
- 排版规范检查
- 阅读体验评估
"""
import re
import math
from typing import Dict, List, Optional, Tuple


# ==================== 评估参数 ====================

# 段落长度阈值
PARAGRAPH_LENGTH = {
    "ideal_min": 50,
    "ideal_max": 300,
    "too_short": 30,
    "too_long": 500,
}

# 句子长度阈值（字符数）
SENTENCE_LENGTH = {
    "ideal_max": 60,
    "long_threshold": 80,
    "very_long_threshold": 120,
}

# 小标题理想间隔（每N个段落一个小标题）
HEADING_INTERVAL = {
    "ideal_min": 2,
    "ideal_max": 8,
}

# 中文停用词
STOP_WORDS = {
    "的", "了", "是", "在", "和", "与", "或", "等", "及",
    "也", "都", "而", "但", "又", "则", "这", "那", "其",
}

# 排版规范
LAYOUT_RULES = {
    "list_marker": r'^[\-\*\d]+\.',  # 列表标记
    "heading_marker": r'^#{1,4}\s',   # 标题标记
    "table_marker": r'\|.*\|',         # 表格标记
    "emphasis_marker": r'\*\*.*\*\*',  # 强调标记
}


class ReadabilityEvaluator:
    """可读性评估器.

    从多个维度评估中文文本的可读性：
    - 段落结构分析
    - 句子复杂度
    - 信息密度
    - 排版规范
    - 阅读体验综合评分

    Attributes:
        scene_type: 当前场景类型.
    """

    def __init__(self, scene_type: str = "municipal"):
        """初始化可读性评估器.

        Args:
            scene_type: 场景类型.
        """
        self.scene_type = scene_type

    def evaluate(self, content: str, title: str = "") -> dict:
        """执行完整的可读性评估.

        Args:
            content: 文章内容.
            title: 文章标题.

        Returns:
            dict: {
                "score": float,
                "paragraph_analysis": dict,
                "sentence_analysis": dict,
                "information_density": dict,
                "layout_score": dict,
                "reading_time_minutes": float,
                "summary": str
            }
        """
        para_result = self._analyze_paragraphs(content)
        sent_result = self._analyze_sentences(content)
        density_result = self._analyze_information_density(content)
        layout_result = self._analyze_layout(content)
        reading_time = self._estimate_reading_time(content)

        # 计算综合得分
        score = self._compute_overall_score(
            para_result, sent_result, density_result, layout_result
        )

        # 摘要
        parts = []
        if para_result["score"] < 0.7:
            parts.append(f"段落结构需优化（{para_result['long_count']}段过长）")
        if sent_result["score"] < 0.7:
            parts.append(f"句子偏复杂（长句占比{sent_result['long_ratio']:.0%}）")
        if density_result["score"] < 0.7:
            parts.append("信息密度不均")
        if layout_result["score"] < 0.7:
            parts.append("排版需改进")
        if not parts:
            parts.append("可读性良好")
        summary = "；".join(parts)

        return {
            "score": score,
            "paragraph_analysis": para_result,
            "sentence_analysis": sent_result,
            "information_density": density_result,
            "layout_score": layout_result,
            "reading_time_minutes": reading_time,
            "summary": summary,
        }

    def _analyze_paragraphs(self, content: str) -> dict:
        """分析段落结构.

        Args:
            content: 文章内容.

        Returns:
            dict: 段落分析结果.
        """
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            return {"score": 0.0, "total": 0, "long_count": 0, "short_count": 0}

        lengths = [len(p) for p in paragraphs]
        long_count = sum(1 for l in lengths if l > PARAGRAPH_LENGTH["too_long"])
        short_count = sum(1 for l in lengths if l < PARAGRAPH_LENGTH["too_short"])
        ideal_count = sum(
            1 for l in lengths
            if PARAGRAPH_LENGTH["ideal_min"] <= l <= PARAGRAPH_LENGTH["ideal_max"]
        )

        avg_len = sum(lengths) / len(lengths) if lengths else 0
        ideal_ratio = ideal_count / len(paragraphs) if paragraphs else 0

        score = 0.5 + ideal_ratio * 0.3 - long_count * 0.05 - short_count * 0.02
        score = max(0.0, min(1.0, score))

        return {
            "score": round(score, 2),
            "total": len(paragraphs),
            "avg_length": round(avg_len, 1),
            "long_count": long_count,
            "short_count": short_count,
            "ideal_ratio": round(ideal_ratio, 2),
        }

    def _analyze_sentences(self, content: str) -> dict:
        """分析句子复杂度.

        Args:
            content: 文章内容.

        Returns:
            dict: 句子分析结果.
        """
        # 按中文标点分句
        sentences = re.split(r'[。！？；\n]', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        if not sentences:
            return {"score": 0.5, "avg_length": 0, "long_ratio": 0, "very_long": 0}

        lengths = [len(s) for s in sentences]
        avg_len = sum(lengths) / len(lengths)
        long_count = sum(1 for l in lengths if l > SENTENCE_LENGTH["long_threshold"])
        very_long = sum(1 for l in lengths if l > SENTENCE_LENGTH["very_long_threshold"])
        long_ratio = long_count / len(sentences) if sentences else 0

        # 长句适度可以，过多则扣分
        score = 0.8
        if long_ratio > 0.3:
            score -= (long_ratio - 0.3) * 0.5
        if very_long > 0:
            score -= very_long * 0.03
        if avg_len < 30:
            score += 0.05  # 短句偏多略加分
        score = max(0.0, min(1.0, score))

        return {
            "score": round(score, 2),
            "total": len(sentences),
            "avg_length": round(avg_len, 1),
            "long_count": long_count,
            "very_long": very_long,
            "long_ratio": round(long_ratio, 2),
        }

    def _analyze_information_density(self, content: str) -> dict:
        """分析信息密度.

        评估内容中有效信息的占比，排除停用词和重复表述.

        Args:
            content: 文章内容.

        Returns:
            dict: 信息密度分析结果.
        """
        # 提取中文词组（简单2-4字分词）
        words = re.findall(r'[\u4e00-\u9fff]{2,4}', content)
        if not words:
            return {"score": 0.5, "unique_ratio": 0, "density": 0}

        # 去停用词
        content_words = [w for w in words if w not in STOP_WORDS]

        # 有效词占比
        effective_ratio = len(content_words) / len(words) if words else 0

        # 唯一词占比（衡量重复度）
        unique_words = set(content_words)
        unique_ratio = len(unique_words) / len(content_words) if content_words else 0

        # 信息密度（有效词/总字符）
        density = len(content_words) / len(content) if content else 0

        # 得分：有效词比例高 + 重复少 = 高分
        score = 0.4 + effective_ratio * 0.3 + unique_ratio * 0.2 + min(density * 5, 0.1)
        score = max(0.0, min(1.0, score))

        return {
            "score": round(score, 2),
            "total_words": len(words),
            "effective_words": len(content_words),
            "unique_ratio": round(unique_ratio, 2),
            "density": round(density, 3),
        }

    def _analyze_layout(self, content: str) -> dict:
        """分析排版规范.

        Args:
            content: 文章内容.

        Returns:
            dict: 排版分析结果.
        """
        lines = content.split("\n")

        heading_count = sum(1 for l in lines if re.match(LAYOUT_RULES["heading_marker"], l.strip()))
        list_count = sum(1 for l in lines if re.match(LAYOUT_RULES["list_marker"], l.strip()))
        table_count = sum(1 for l in lines if re.match(LAYOUT_RULES["table_marker"], l.strip()))
        emphasis_count = len(re.findall(LAYOUT_RULES["emphasis_marker"], content))

        # 排版元素丰富度
        has_variety = sum(1 for c in [heading_count, list_count, table_count, emphasis_count] if c > 0)

        # 小标题间隔
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if heading_count > 0 and len(paragraphs) > 0:
            heading_interval = len(paragraphs) / heading_count
        else:
            heading_interval = 999

        # 评分
        score = 0.5
        score += min(0.15, has_variety * 0.04)  # 元素多样性
        if heading_count >= 3:
            score += 0.1
        if HEADING_INTERVAL["ideal_min"] <= heading_interval <= HEADING_INTERVAL["ideal_max"]:
            score += 0.1
        if emphasis_count > 0:
            score += 0.05
        if table_count > 0:
            score += 0.05
        score = max(0.0, min(1.0, score))

        return {
            "score": round(score, 2),
            "heading_count": heading_count,
            "list_count": list_count,
            "table_count": table_count,
            "emphasis_count": emphasis_count,
            "heading_interval": round(heading_interval, 1),
        }

    def _estimate_reading_time(self, content: str) -> float:
        """估算阅读时间（中文阅读速度约300-500字/分钟）.

        Args:
            content: 文章内容.

        Returns:
            float: 预估阅读时间（分钟）.
        """
        char_count = len(content.replace("\n", "").replace(" ", ""))
        return round(char_count / 400, 1)

    def _compute_overall_score(self, para, sent, density, layout) -> float:
        """计算可读性综合得分.

        Args:
            para: 段落分析结果.
            sent: 句子分析结果.
            density: 信息密度分析结果.
            layout: 排版分析结果.

        Returns:
            float: 综合得分（0~1）.
        """
        weights = {
            "paragraph": 0.25,
            "sentence": 0.25,
            "density": 0.25,
            "layout": 0.25,
        }
        score = (
            para["score"] * weights["paragraph"]
            + sent["score"] * weights["sentence"]
            + density["score"] * weights["density"]
            + layout["score"] * weights["layout"]
        )
        return round(max(0.0, min(1.0, score)), 2)
