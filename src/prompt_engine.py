"""提示词引擎 - 刘凯睿负责

功能：
- 多场景提示词模板管理（市政/工业）
- 多内容类型模板（文章/战报/政策解读/技术趋势/资讯摘要）
- 动态变量注入
- 品牌调性约束
- LLM/模板双模式支持
"""


# ==================== 场景配置 ====================
SCENE_CONFIG = {
    "municipal": {
        "name": "市政环保",
        "audience": "市政部门决策者、环保局官员、城市管理者",
        "style": "专业、权威、注重政策合规性和社会效益",
        "terms": "污水处理厂、固废处理、环境监测、雨污分流、提标改造",
    },
    "industrial": {
        "name": "工业环保",
        "audience": "企业EHS负责人、工厂管理层、工业环保工程师",
        "style": "技术导向、数据驱动、注重经济效益和合规要求",
        "terms": "废气治理、废水零排放、VOCs治理、危废处置、清洁生产",
    },
}

# ==================== 内容类型模板 ====================
TYPE_TEMPLATES = {
    "article": {
        "label": "深度行业文章",
        "structure": ["行业背景", "现状与挑战", "解决方案", "成功案例", "展望"],
    },
    "battle_report": {
        "label": "项目战报",
        "structure": ["项目概况", "项目目标", "技术方案", "运行数据", "项目成效", "客户评价"],
    },
    "policy_analysis": {
        "label": "政策解读",
        "structure": ["政策概要", "核心要点解读", "对行业的影响分析", "应对策略", "建议"],
    },
    "tech_trend": {
        "label": "技术趋势分析",
        "structure": ["引言", "趋势一", "趋势二", "趋势三", "趋势四", "展望与建议"],
    },
    "news_digest": {
        "label": "资讯摘要",
        "structure": ["政策动态", "技术前沿", "市场观察", "行业观察"],
    },
}

# ==================== 系统/用户提示词模板 ====================
SYSTEM_PROMPT_TEMPLATE = """你是吉康环境的资深营销文案专家，专注于{scene_name}领域。
目标受众：{audience}
写作风格：{style}
专业术语偏好：{terms}
品牌名称：吉康环境

请确保：技术准确、数据真实、符合品牌调性。输出格式为Markdown。"""

USER_PROMPT_TEMPLATE = """请撰写一篇{type_label}，标题为：{title}

要求：
- 品牌名称：吉康环境
- 场景类型：{scene_name}
- 关键词：{keywords}
- 输出格式：Markdown
- 字数：{word_count}
- 必须体现吉康环境的技术实力和行业地位

{context_section}

{custom_section}

直接输出Markdown格式文章，不要包含```markdown标记。"""

CONTEXT_TEMPLATE = """
## 专业知识参考
{reference}
"""

CUSTOM_TEMPLATE = """
## 额外要求
{instructions}
"""


class PromptEngine:
    """提示词管理与模板引擎

    支持：
    - 多场景切换（市政/工业）
    - 多内容类型
    - 动态变量注入
    - RAG知识注入
    - 品牌调性约束
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.templates = {}
        # 注册默认模板
        self._register_defaults()

    def _register_defaults(self):
        """注册内置提示词模板"""
        for type_key, type_info in TYPE_TEMPLATES.items():
            self.register_template(
                type_key,
                {
                    "label": type_info["label"],
                    "structure": type_info["structure"],
                    "scene_aware": True,
                },
            )

    def register_template(self, name, template):
        """注册提示词模板

        Args:
            name: 模板名称
            template: 模板配置字典
        """
        self.templates[name] = template

    def build_prompt(self, topic, context=None, content_type="article",
                     scene_type="municipal", keywords=None,
                     custom_instructions=None, reference=None):
        """构建完整提示词

        Args:
            topic: 文章标题/主题
            context: 上下文信息（兼容旧接口）
            content_type: 内容类型 (article/battle_report/policy_analysis/tech_trend/news_digest)
            scene_type: 场景类型 (municipal/industrial)
            keywords: 关键词列表
            custom_instructions: 额外指令
            reference: RAG检索到的参考知识

        Returns:
            dict: {"system_prompt": str, "user_prompt": str}
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])
        type_info = TYPE_TEMPLATES.get(content_type, TYPE_TEMPLATES["article"])
        kw = "、".join(keywords) if keywords else "环保、绿色发展"

        # 构建系统提示词
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            scene_name=scene["name"],
            audience=scene["audience"],
            style=scene["style"],
            terms=scene["terms"],
        )

        # 构建知识参考段落
        context_section = ""
        if reference:
            context_section = CONTEXT_TEMPLATE.format(reference=reference)
        elif context:
            context_section = CONTEXT_TEMPLATE.format(reference=str(context))

        # 构建额外要求段落
        custom_section = ""
        if custom_instructions:
            custom_section = CUSTOM_TEMPLATE.format(instructions=custom_instructions)

        # 字数范围
        word_count = self.config.get("generator", {}).get("word_count", "800-1500字")

        # 构建用户提示词
        user_prompt = USER_PROMPT_TEMPLATE.format(
            type_label=type_info["label"],
            title=topic,
            scene_name=scene["name"],
            keywords=kw,
            word_count=word_count,
            context_section=context_section,
            custom_section=custom_section,
        )

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "scene": scene,
            "type_info": type_info,
        }

    def build_review_prompt(self, title, content, scene_type="municipal"):
        """构建审核提示词

        Args:
            title: 文章标题
            content: 文章内容
            scene_type: 场景类型

        Returns:
            dict: {"system_prompt": str, "user_prompt": str}
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])

        system_prompt = f"""你是吉康环境的内容质量评审专家，专注于{scene['name']}领域。
请从以下维度评估内容：
1. 技术准确率 (0-1)：技术描述是否准确
2. 合规性 (0-1)：是否符合广告法和环保政策
3. 可读性 (0-1)：文章结构是否清晰
4. 品牌调性匹配度 (0-1)：是否符合吉康环境品牌形象

判定规则：四项均≥0.8→pass，任一项<0.6→fail，其他→needs_revision

严格按JSON格式输出：
{{"accuracy_score":0.0-1.0,"compliance_score":0.0-1.0,"readability_score":0.0-1.0,"brand_alignment_score":0.0-1.0,"comments":"评审意见","result":"pass/needs_revision/fail"}}"""

        user_prompt = f"""请评审以下{scene['name']}内容：

标题：{title}

内容：
{content}

输出JSON格式评审结果。"""

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

    def get_scene_config(self, scene_type="municipal"):
        """获取场景配置"""
        return SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])

    def get_type_template(self, content_type="article"):
        """获取内容类型模板信息"""
        return TYPE_TEMPLATES.get(content_type, TYPE_TEMPLATES["article"])

    def list_templates(self):
        """列出所有可用模板"""
        return {k: v["label"] for k, v in TYPE_TEMPLATES.items()}

    def list_scenes(self):
        """列出所有可用场景"""
        return {k: v["name"] for k, v in SCENE_CONFIG.items()}
