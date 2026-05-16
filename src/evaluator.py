"""内容质量评估 - 刘凯睿负责

功能：
- 技术准确率评估
- 合规性检查（广告法+环保政策）
- 可读性分析（中文文本指标）
- 品牌调性匹配度
- 专业性评估指标
- 修改建议生成器
- LLM/规则引擎双模式
- 三级审核支持
- quality/ 子模块集成（术语校验、逻辑分析、可读性、建议生成）
"""
import re
from typing import Optional, List

# 尝试导入 quality/ 子模块（增强评估）
try:
    from src.quality.term_checker import TermChecker
    from src.quality.logic_analyzer import LogicAnalyzer
    from src.quality.readability_eval import ReadabilityEvaluator
    from src.quality.suggestion_engine import SuggestionEngine
    _QUALITY_AVAILABLE = True
except ImportError:
    _QUALITY_AVAILABLE = False


# 合规违禁词库
VIOLATION_KEYWORDS = [
    "绝对", "第一", "唯一", "最佳", "顶级", "首屈一指",
    "100%有效", "包治", "根治", "零风险", "无副作用",
    "国家级", "最高级", "王牌", "领袖品牌",
]

# 场景专业术语
SCENE_TECH_KEYWORDS = {
    "municipal": [
        "污水处理", "固废处理", "环境监测", "雨污分流", "提标改造",
        "MBR", "MBBR", "生化处理", "膜过滤", "活性炭", "COD", "氨氮",
    ],
    "industrial": [
        "VOCs", "废气治理", "零排放", "危废处置", "清洁生产",
        "催化燃烧", "反渗透", "蒸发结晶", "DTRO", "EDR", "MVR",
    ],
}

# 品牌核心价值词
BRAND_VALUE_KEYWORDS = [
    "让绿色成为生产力", "创新驱动", "技术实力", "吉康环境",
    "智慧环保", "绿色发展", "循环经济", "资源化",
]

# 可读性相关：中文长句阈值
LONG_SENTENCE_THRESHOLD = 80  # 超过此字符数视为长句
IDEAL_PARAGRAPH_LENGTH = (50, 300)  # 理想段落长度范围


class Evaluator:
    """内容质量评估器.

    双模式架构：
    - 有LLM → 深度语义评审（含修改建议）
    - 无LLM → 多维规则引擎评审（含修改建议）

    Attributes:
        config: 全局配置字典.
        prompt_engine: 提示词引擎实例.
    """

    def __init__(self, config=None, prompt_engine=None):
        """初始化评估器.

        Args:
            config: 全局配置字典.
            prompt_engine: 提示词引擎实例.
        """
        self.config = config or {}
        self.prompt_engine = prompt_engine
        self._llm = None
        self._has_llm = False

    def _get_llm(self):
        """获取LLM实例（延迟加载）.

        Returns:
            ChatOpenAI实例或None.
        """
        if self._llm is None and not self._has_llm:
            try:
                from langchain_openai import ChatOpenAI
                gen_config = self.config.get("generator", {})
                api_key = gen_config.get("api_key", "") or self.config.get("llm_api_key", "")
                if api_key:
                    self._llm = ChatOpenAI(
                        model=gen_config.get("model", "gpt-4"),
                        api_key=api_key,
                        base_url=gen_config.get("base_url", "https://api.openai.com/v1"),
                        max_tokens=2048,
                        temperature=0.1,
                    )
            except ImportError:
                pass
            self._has_llm = True
        return self._llm

    def evaluate(self, content, title="", scene_type="municipal"):
        """评估内容质量.

        Args:
            content: 文章内容.
            title: 文章标题.
            scene_type: 场景类型，可选值：municipal/industrial.

        Returns:
            dict: {
                accuracy_score: float,
                compliance_score: float,
                readability_score: float,
                brand_alignment_score: float,
                professionalism_score: float,
                overall: float,
                result: str,
                comments: str,
                suggestions: list[str]
            }
        """
        llm = self._get_llm()
        if llm:
            return self._llm_evaluate(title, content, scene_type)
        return self._rule_evaluate(title, content, scene_type)

    # ==================== LLM 评审 ====================

    def _llm_evaluate(self, title, content, scene_type):
        """使用LLM进行深度评审.

        Args:
            title: 文章标题.
            content: 文章内容.
            scene_type: 场景类型.

        Returns:
            dict: 评估结果字典.
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        prompts = self.prompt_engine.build_review_prompt(title, content, scene_type)
        try:
            response = self._get_llm().invoke([
                SystemMessage(content=prompts["system_prompt"]),
                HumanMessage(content=prompts["user_prompt"]),
            ])
            return self._parse_llm_response(response.content)
        except Exception:
            return self._rule_evaluate(title, content, scene_type)

    def _parse_llm_response(self, text):
        """解析LLM评审响应.

        Args:
            text: LLM返回的文本.

        Returns:
            dict: 标准化的评估结果字典.
        """
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            import json
            try:
                data = json.loads(json_match.group())
                result = {
                    "accuracy_score": float(data.get("accuracy_score", 0.8)),
                    "compliance_score": float(data.get("compliance_score", 0.9)),
                    "readability_score": float(data.get("readability_score", 0.85)),
                    "brand_alignment_score": float(data.get("brand_alignment_score", 0.85)),
                    "professionalism_score": float(data.get("professionalism_score", 0.8)),
                    "comments": data.get("comments", ""),
                    "suggestions": data.get("suggestions", []),
                }
                result["overall"] = sum([
                    result["accuracy_score"], result["compliance_score"],
                    result["readability_score"], result["brand_alignment_score"],
                    result["professionalism_score"],
                ]) / 5
                scores = [
                    result["accuracy_score"], result["compliance_score"],
                    result["readability_score"], result["brand_alignment_score"],
                    result["professionalism_score"],
                ]
                if all(s >= 0.8 for s in scores):
                    result["result"] = "pass"
                elif any(s < 0.6 for s in scores):
                    result["result"] = "fail"
                else:
                    result["result"] = "needs_revision"
                return result
            except (json.JSONDecodeError, ValueError):
                pass
        return self._rule_evaluate("解析失败", text, "municipal")

    # ==================== 规则引擎评审 ====================

    def _rule_evaluate(self, title, content, scene_type):
        """使用规则引擎进行评审.

        Args:
            title: 文章标题.
            content: 文章内容.
            scene_type: 场景类型.

        Returns:
            dict: 评估结果字典.
        """
        scores = {
            "accuracy_score": 0.82,
            "compliance_score": 0.90,
            "readability_score": 0.85,
            "brand_alignment_score": 0.88,
            "professionalism_score": 0.80,
        }

        # --- 技术准确率 ---
        scores["accuracy_score"] += self._calc_accuracy(content, scene_type)

        # --- 合规性 ---
        compliance = self.check_compliance(content)
        if not compliance["is_compliant"]:
            scores["compliance_score"] -= 0.3
        positive = ["符合", "达标", "合规", "满足标准"]
        scores["compliance_score"] += min(0.05, sum(1 for s in positive if s in content) * 0.02)

        # --- 可读性（增强算法）---
        scores["readability_score"] += self._calc_readability(title, content)

        # --- 品牌匹配 ---
        scores["brand_alignment_score"] += self._calc_brand_alignment(content)

        # --- 专业性（新增）---
        scores["professionalism_score"] += self._calc_professionalism(content, scene_type)

        # --- quality/ 子模块增强（如果可用）---
        if _QUALITY_AVAILABLE:
            scores = self._quality_enhance(scores, title, content, scene_type)

        # 限制范围
        for k in scores:
            scores[k] = round(min(1.0, max(0.0, scores[k])), 2)

        # 综合判定
        all_scores = list(scores.values())
        scores["overall"] = round(sum(all_scores) / len(all_scores), 2)

        if all(s >= 0.8 for s in all_scores):
            scores["result"] = "pass"
        elif any(s < 0.6 for s in all_scores):
            scores["result"] = "fail"
        else:
            scores["result"] = "needs_revision"

        # 生成修改建议
        scores["suggestions"] = self._generate_suggestions(scores, compliance, content, scene_type)
        scores["comments"] = self._generate_comments(scores, compliance)
        return scores

    def _calc_accuracy(self, content, scene_type):
        """计算技术准确率加分.

        Args:
            content: 文章内容.
            scene_type: 场景类型.

        Returns:
            float: 加分值（0~0.20）.
        """
        bonus = 0.0
        tech_kws = SCENE_TECH_KEYWORDS.get(scene_type, [])
        tech_match = sum(1 for kw in tech_kws if kw in content)
        bonus += min(0.15, tech_match * 0.03)

        # 数据支撑
        data_points = len(re.findall(r'\d+[%％]', content)) + len(re.findall(r'\d+\.\d+', content))
        bonus += min(0.05, data_points * 0.01)
        return bonus

    def _calc_readability(self, title, content):
        """计算可读性加分（增强算法）.

        基于中文文本特征：
        - 标题长度
        - 段落结构
        - 句子长度分布
        - 小标题数量
        - 表格/列表使用

        Args:
            title: 文章标题.
            content: 文章内容.

        Returns:
            float: 加分值（-0.10~0.20）.
        """
        bonus = 0.0

        # 标题长度
        if 10 <= len(title) <= 60:
            bonus += 0.05
        elif len(title) > 60:
            bonus -= 0.03  # 标题过长扣分

        # 段落结构分析
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if paragraphs:
            avg_para_len = sum(len(p) for p in paragraphs) / len(paragraphs)
            low, high = IDEAL_PARAGRAPH_LENGTH
            if low <= avg_para_len <= high:
                bonus += 0.04
            elif avg_para_len > high:
                bonus -= 0.03  # 段落过长扣分

        # 句子长度分析（中文句号、感叹号、问号分句）
        sentences = re.split(r'[。！？\n]', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if sentences:
            long_sentences = sum(1 for s in sentences if len(s) > LONG_SENTENCE_THRESHOLD)
            long_ratio = long_sentences / len(sentences)
            if long_ratio > 0.3:
                bonus -= 0.05  # 长句过多扣分
            elif long_ratio < 0.1:
                bonus += 0.02  # 句式简洁加分

        # 内容长度
        if len(content) > 500:
            bonus += 0.02
        if len(content) > 1000:
            bonus += 0.03

        # 小标题数量
        heading_count = content.count("##") + content.count("###")
        bonus += min(0.05, heading_count * 0.01)

        # 表格/列表使用
        if "|" in content:
            bonus += 0.02
        if "- **" in content or "1. **" in content:
            bonus += 0.02

        return max(-0.10, min(0.20, bonus))

    def _calc_brand_alignment(self, content):
        """计算品牌匹配加分.

        Args:
            content: 文章内容.

        Returns:
            float: 加分值（0~0.12）.
        """
        bonus = 0.0
        if "吉康环境" in content or "吉康" in content:
            bonus += 0.08
        bonus += min(0.04, sum(1 for v in BRAND_VALUE_KEYWORDS if v in content) * 0.02)
        return bonus

    def _calc_professionalism(self, content, scene_type):
        """计算专业性加分.

        指标包括：
        - 专业术语密度
        - 数据引用率
        - 技术深度（工艺描述/参数细节）
        - 行业标准引用

        Args:
            content: 文章内容.
            scene_type: 场景类型.

        Returns:
            float: 加分值（-0.05~0.15）.
        """
        bonus = 0.0

        # 专业术语密度
        tech_kws = SCENE_TECH_KEYWORDS.get(scene_type, [])
        if tech_kws:
            total_chars = len(content)
            if total_chars > 0:
                tech_count = sum(content.count(kw) for kw in tech_kws)
                density = tech_count / (total_chars / 100)  # 每100字的术语数
                if 0.5 <= density <= 5.0:
                    bonus += 0.05  # 适中的术语密度
                elif density > 5.0:
                    bonus -= 0.03  # 术语堆砌扣分
                elif density > 0:
                    bonus += 0.02  # 有术语但偏少

        # 数据引用率
        data_refs = len(re.findall(r'\d+\.?\d*\s*(mg/L|ppm|%|吨|立方米|千瓦|万元|亿元)', content))
        bonus += min(0.05, data_refs * 0.015)

        # 技术深度指标
        depth_indicators = ["工艺", "流程", "参数", "指标", "标准", "系统", "平台", "方案"]
        depth_count = sum(1 for d in depth_indicators if d in content)
        bonus += min(0.03, depth_count * 0.01)

        # 行业标准引用
        standard_refs = len(re.findall(r'(GB|HJ|CJJ|DB)\s*\d+', content))
        bonus += min(0.02, standard_refs * 0.01)

        return max(-0.05, min(0.15, bonus))

    def _quality_enhance(self, scores, title, content, scene_type):
        """使用 quality/ 子模块增强评估结果

        如果 quality/ 模块可用，调用术语校验、逻辑分析、可读性评估、建议引擎，
        将结果合并到 scores 字典中。

        Args:
            scores: 当前评估得分字典
            title: 文章标题
            content: 文章内容
            scene_type: 场景类型

        Returns:
            dict: 增强后的评估得分字典
        """
        try:
            # 术语校验
            tc = TermChecker()
            term_result = tc.check(content)
            if isinstance(term_result, dict):
                term_score = term_result.get("accuracy", term_result.get("score", None))
                if term_score is not None and isinstance(term_score, (int, float)):
                    # quality 模块用 0-100 分，转换为 0-1
                    normalized = min(1.0, term_score / 100.0)
                    scores["accuracy_score"] = round((scores["accuracy_score"] + normalized) / 2, 2)

            # 逻辑分析
            la = LogicAnalyzer()
            logic_result = la.analyze(content)
            if isinstance(logic_result, dict):
                logic_score = logic_result.get("consistency", logic_result.get("score", None))
                if logic_score is not None and isinstance(logic_score, (int, float)):
                    normalized = min(1.0, logic_score / 100.0) if logic_score > 1 else logic_score
                    # 逻辑分数影响专业性
                    scores["professionalism_score"] = round(
                        (scores["professionalism_score"] + normalized) / 2, 2
                    )

            # 可读性评估
            re_eval = ReadabilityEvaluator()
            read_result = re_eval.evaluate(content)
            if isinstance(read_result, dict):
                read_score = read_result.get("overall", read_result.get("score", None))
                if read_score is not None and isinstance(read_score, (int, float)):
                    normalized = min(1.0, read_score / 100.0) if read_score > 1 else read_score
                    scores["readability_score"] = round(
                        (scores["readability_score"] + normalized) / 2, 2
                    )

            # 建议引擎（结果将在 _generate_suggestions 中合并）
            se = SuggestionEngine()
            quality_suggestions = se.generate_suggestions(scores, content)
            if quality_suggestions and isinstance(quality_suggestions, list):
                # 暂存到 scores，后面 _generate_suggestions 会合并
                scores["_quality_suggestions"] = quality_suggestions

        except Exception:
            pass  # quality 模块调用失败不影响主评估

        return scores

    def _generate_suggestions(self, scores, compliance, content, scene_type):
        """生成具体修改建议.

        根据各维度得分生成针对性的修改建议列表.

        Args:
            scores: 各维度得分字典.
            compliance: 合规性检查结果.
            content: 文章内容.
            scene_type: 场景类型.

        Returns:
            list[str]: 修改建议列表.
        """
        suggestions = []

        # 技术准确性建议
        if scores["accuracy_score"] < 0.85:
            tech_kws = SCENE_TECH_KEYWORDS.get(scene_type, [])
            missing = [kw for kw in tech_kws[:5] if kw not in content]
            if missing:
                suggestions.append(
                    f"建议增加专业技术术语，如：{', '.join(missing[:3])}，提升技术描述深度"
                )
            data_points = len(re.findall(r'\d+\.?\d*[%％]', content))
            if data_points < 3:
                suggestions.append("建议补充更多量化数据支撑，如处理效率、达标率等关键指标")

        # 合规性建议
        if not compliance["is_compliant"]:
            suggestions.append(
                f"存在广告法违禁词：{', '.join(compliance['violations'])}，请替换为合规表述"
            )

        # 可读性建议
        if scores["readability_score"] < 0.85:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            long_paras = [p for p in paragraphs if len(p) > 300]
            if long_paras:
                suggestions.append("部分段落过长，建议拆分为更短的段落以提升可读性")

            heading_count = content.count("##") + content.count("###")
            if heading_count < 3:
                suggestions.append("建议增加小标题，使文章结构更清晰")

            sentences = re.split(r'[。！？]', content)
            long_sents = [s for s in sentences if len(s.strip()) > LONG_SENTENCE_THRESHOLD]
            if len(long_sents) > 2:
                suggestions.append("存在较多长句，建议拆分为短句以提升阅读体验")

        # 品牌匹配建议
        if scores["brand_alignment_score"] < 0.9:
            if "吉康环境" not in content:
                suggestions.append("文章未提及品牌名称，建议自然融入'吉康环境'")
            brand_found = [v for v in BRAND_VALUE_KEYWORDS if v in content]
            if len(brand_found) < 2:
                suggestions.append("建议增加品牌价值元素，如'让绿色成为生产力'、'创新驱动'等")

        # 专业性建议
        if scores["professionalism_score"] < 0.85:
            tech_kws = SCENE_TECH_KEYWORDS.get(scene_type, [])
            if len([kw for kw in tech_kws if kw in content]) < 3:
                suggestions.append("专业术语使用较少，建议增加行业术语以提升专业感")
            data_refs = len(re.findall(r'\d+\.?\d*\s*(mg/L|ppm|%|吨|立方米)', content))
            if data_refs < 2:
                suggestions.append("建议增加带单位的技术数据（如mg/L、吨/日），增强技术说服力")

        # 如果各项都好
        if not suggestions:
            suggestions.append("内容质量良好，无需修改")

        # 合并 quality/ 子模块的建议
        quality_sugs = scores.pop("_quality_suggestions", None)
        if quality_sugs:
            for qs in quality_sugs:
                if isinstance(qs, str) and qs not in suggestions:
                    suggestions.append(qs)
                elif isinstance(qs, dict) and qs.get("text"):
                    suggestions.append(qs["text"])

        return suggestions

    def _generate_comments(self, scores, compliance):
        """生成评估意见摘要.

        Args:
            scores: 各维度得分字典.
            compliance: 合规性检查结果.

        Returns:
            str: 评估意见文本.
        """
        parts = []

        # 技术准确性
        if scores["accuracy_score"] >= 0.9:
            parts.append("✅ 技术描述准确，数据支撑充分")
        elif scores["accuracy_score"] >= 0.8:
            parts.append("⚠️ 技术描述基本准确，建议补充更多数据")
        else:
            parts.append("❌ 技术描述需核实")

        # 合规性
        if compliance["is_compliant"]:
            parts.append("✅ 合规性检查通过")
        else:
            parts.append(f"❌ 合规风险：{', '.join(compliance['violations'])}")

        # 可读性
        if scores["readability_score"] >= 0.9:
            parts.append("✅ 文章结构清晰，可读性佳")
        elif scores["readability_score"] < 0.8:
            parts.append("⚠️ 可读性有待提升，建议优化段落结构")

        # 品牌匹配
        if scores["brand_alignment_score"] >= 0.9:
            parts.append("✅ 品牌调性匹配度高")
        elif scores["brand_alignment_score"] < 0.8:
            parts.append("❌ 需增强品牌元素")

        # 专业性
        if scores["professionalism_score"] >= 0.9:
            parts.append("✅ 专业性强，术语与数据运用恰当")
        elif scores["professionalism_score"] < 0.8:
            parts.append("⚠️ 专业性不足，建议增加行业术语和量化数据")

        return "；".join(parts)

    def check_compliance(self, content):
        """合规性检查.

        Args:
            content: 文章内容.

        Returns:
            dict: {"is_compliant": bool, "violations": list[str]}
        """
        found = [kw for kw in VIOLATION_KEYWORDS if kw in content]
        return {"is_compliant": len(found) == 0, "violations": found}

    # ==================== 兼容旧接口 ====================

    def _score_relevance(self, content):
        """兼容旧接口：相关性评分."""
        return self.evaluate(content).get("accuracy_score", 0)

    def _score_quality(self, content):
        """兼容旧接口：质量评分."""
        return self.evaluate(content).get("compliance_score", 0)

    def _score_originality(self, content):
        """兼容旧接口：原创性评分."""
        return self.evaluate(content).get("brand_alignment_score", 0)

    def _score_readability(self, content):
        """兼容旧接口：可读性评分."""
        return self.evaluate(content).get("readability_score", 0)
