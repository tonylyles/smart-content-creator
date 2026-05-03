"""内容质量评估 - 刘凯睿负责

功能：
- 技术准确率评估
- 合规性检查（广告法+环保政策）
- 可读性分析
- 品牌调性匹配度
- LLM/规则引擎双模式
- 三级审核支持
"""
import re
from typing import Optional, List


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


class Evaluator:
    """内容质量评估器

    双模式架构：
    - 有LLM → 深度语义评审
    - 无LLM → 多维规则引擎评审
    """

    def __init__(self, config=None, prompt_engine=None):
        self.config = config or {}
        self.prompt_engine = prompt_engine
        self._llm = None
        self._has_llm = False

    def _get_llm(self):
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
        """评估内容质量

        Args:
            content: 文章内容
            title: 文章标题
            scene_type: 场景类型 (municipal/industrial)

        Returns:
            dict: {
                accuracy_score, compliance_score,
                readability_score, brand_alignment_score,
                overall, result, comments
            }
        """
        llm = self._get_llm()
        if llm:
            return self._llm_evaluate(title, content, scene_type)
        return self._rule_evaluate(title, content, scene_type)

    # ==================== LLM 评审 ====================
    def _llm_evaluate(self, title, content, scene_type):
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
                    "comments": data.get("comments", ""),
                }
                result["overall"] = sum([
                    result["accuracy_score"], result["compliance_score"],
                    result["readability_score"], result["brand_alignment_score"],
                ]) / 4
                scores = [result["accuracy_score"], result["compliance_score"],
                         result["readability_score"], result["brand_alignment_score"]]
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
        scores = {
            "accuracy_score": 0.82,
            "compliance_score": 0.90,
            "readability_score": 0.85,
            "brand_alignment_score": 0.88,
        }

        # --- 技术准确率 ---
        tech_kws = SCENE_TECH_KEYWORDS.get(scene_type, [])
        tech_match = sum(1 for kw in tech_kws if kw in content)
        scores["accuracy_score"] += min(0.15, tech_match * 0.03)

        # 数据支撑
        data_points = len(re.findall(r'\d+[%％]', content)) + len(re.findall(r'\d+\.\d+', content))
        scores["accuracy_score"] += min(0.05, data_points * 0.01)

        # --- 合规性 ---
        compliance = self.check_compliance(content)
        if not compliance["is_compliant"]:
            scores["compliance_score"] -= 0.3
        positive = ["符合", "达标", "合规", "满足标准"]
        scores["compliance_score"] += min(0.05, sum(1 for s in positive if s in content) * 0.02)

        # --- 可读性 ---
        if 10 <= len(title) <= 60:
            scores["readability_score"] += 0.05
        if len(content) > 500:
            scores["readability_score"] += 0.02
        if len(content) > 1000:
            scores["readability_score"] += 0.03
        heading_count = content.count("##") + content.count("###")
        scores["readability_score"] += min(0.05, heading_count * 0.01)
        if "|" in content:
            scores["readability_score"] += 0.02

        # --- 品牌匹配 ---
        if "吉康环境" in content or "吉康" in content:
            scores["brand_alignment_score"] += 0.08
        brand_values = ["让绿色成为生产力", "创新驱动", "技术实力"]
        scores["brand_alignment_score"] += min(0.04, sum(1 for v in brand_values if v in content) * 0.02)

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

        scores["comments"] = self._generate_comments(scores, compliance)
        return scores

    def _generate_comments(self, scores, compliance):
        parts = []
        if scores["accuracy_score"] >= 0.9:
            parts.append("✅ 技术描述准确，数据支撑充分")
        elif scores["accuracy_score"] >= 0.8:
            parts.append("⚠️ 技术描述基本准确，建议补充更多数据")
        else:
            parts.append("❌ 技术描述需核实")

        if compliance["is_compliant"]:
            parts.append("✅ 合规性检查通过")
        else:
            parts.append(f"❌ 合规风险：{', '.join(compliance['violations'])}")

        if scores["readability_score"] >= 0.9:
            parts.append("✅ 文章结构清晰")
        if scores["brand_alignment_score"] >= 0.9:
            parts.append("✅ 品牌调性匹配度高")
        elif scores["brand_alignment_score"] < 0.8:
            parts.append("❌ 需增强品牌元素")

        return "；".join(parts)

    def check_compliance(self, content):
        """合规性检查

        Returns:
            dict: {"is_compliant": bool, "violations": list}
        """
        found = [kw for kw in VIOLATION_KEYWORDS if kw in content]
        return {"is_compliant": len(found) == 0, "violations": found}

    # ==================== 兼容旧接口 ====================
    def _score_relevance(self, content):
        return self.evaluate(content).get("accuracy_score", 0)

    def _score_quality(self, content):
        return self.evaluate(content).get("compliance_score", 0)

    def _score_originality(self, content):
        return self.evaluate(content).get("brand_alignment_score", 0)

    def _score_readability(self, content):
        return self.evaluate(content).get("readability_score", 0)
