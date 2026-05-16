"""提示词引擎 - 刘凯睿负责

功能：
- 多场景提示词模板管理（市政/工业）
- 多内容类型模板（文章/战报/政策解读/技术趋势/资讯摘要）
- 动态变量注入
- 品牌调性约束
- LLM/模板双模式支持
- 时间节点感知（支持里程碑注入）
- 用户偏好集成
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
    "industrial_humidity_solution": {
        "name": "工业湿度解决方案",
        "audience": "工业环保工程师、企业EHS负责人、设备采购决策者",
        "style": "技术导向、数据驱动、注重经济效益和合规要求，强调湿度控制方案的技术细节和节能效果",
        "terms": "湿度控制、恒温恒湿、转轮除湿、新风系统、VOCs治理、节能降耗、温湿度监测",
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

{timeline_section}

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

TIMELINE_TEMPLATE = """
## 时间节点规划
{timeline_content}
"""

REVISION_TEMPLATE = """
## 修改要求
请根据以下评审意见对原文进行修改：
{revision_instructions}
"""


class PromptEngine:
    """提示词管理与模板引擎.

    支持：
    - 多场景切换（市政/工业）
    - 多内容类型
    - 动态变量注入
    - RAG知识注入
    - 品牌调性约束
    - 时间节点感知
    - 用户偏好集成
    - 修改指令构建

    Attributes:
        config: 全局配置字典.
        templates: 已注册的模板字典.
        user_preferences: 用户偏好设置.
    """

    def __init__(self, config=None):
        """初始化提示词引擎.

        Args:
            config: 全局配置字典，默认为空字典.
        """
        self.config = config or {}
        self.templates = {}
        self.user_preferences = {
            "default_scene": "municipal",
            "default_content_type": "article",
            "default_word_count": "800-1500字",
            "tone": "professional",
            "auto_brand_injection": True,
        }
        self._register_defaults()

    def _register_defaults(self):
        """注册内置提示词模板."""
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
        """注册提示词模板.

        Args:
            name: 模板名称.
            template: 模板配置字典.
        """
        self.templates[name] = template

    def update_user_preferences(self, preferences):
        """更新用户偏好设置.

        Args:
            preferences: 用户偏好字典，支持以下键：
                - default_scene: 默认场景 (municipal/industrial)
                - default_content_type: 默认内容类型
                - default_word_count: 默认字数范围
                - tone: 写作语调 (professional/casual/technical)
                - auto_brand_injection: 是否自动注入品牌元素
        """
        self.user_preferences.update(preferences)

    def get_user_preferences(self):
        """获取当前用户偏好.

        Returns:
            dict: 用户偏好设置字典.
        """
        return self.user_preferences.copy()

    def build_prompt(self, topic, context=None, content_type="article",
                     scene_type="municipal", keywords=None,
                     custom_instructions=None, reference=None,
                     timeline=None,
                     content_type_hint=None, tone=None,
                     target_audience=None):
        """构建完整提示词.

        Args:
            topic: 文章标题/主题.
            context: 上下文信息（兼容旧接口）.
            content_type: 内容类型，可选值：
                article/battle_report/policy_analysis/tech_trend/news_digest.
            scene_type: 场景类型，可选值：
                municipal/industrial/industrial_humidity_solution.
            keywords: 关键词列表.
            custom_instructions: 额外指令.
            reference: RAG检索到的参考知识.
            timeline: 时间节点列表，格式为 [{"phase": str, "deadline": str}].
            content_type_hint: 内容类型提示（如 "technical_analysis"），
                会覆盖默认的 content_type 映射.
            tone: 写作语气（如 "professional_and_insightful"），
                会覆盖用户偏好设置.
            target_audience: 目标受众（如 "环保工程师"），
                会覆盖场景默认受众.

        Returns:
            dict: {"system_prompt": str, "user_prompt": str,
                   "scene": dict, "type_info": dict}
        """
        # 应用用户偏好覆盖默认值
        if content_type == "article" and self.user_preferences.get("default_content_type"):
            content_type = self.user_preferences["default_content_type"]
        if scene_type == "municipal" and self.user_preferences.get("default_scene"):
            scene_type = self.user_preferences["default_scene"]

        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])

        # content_type_hint: 允许外部覆盖 content_type 逻辑
        if content_type_hint:
            content_type = content_type_hint

        type_info = TYPE_TEMPLATES.get(content_type, TYPE_TEMPLATES["article"])
        kw = "、".join(keywords) if keywords else "环保、绿色发展"

        # 根据用户偏好调整语调（允许外部参数覆盖）
        if tone is None:
            tone = self.user_preferences.get("tone", "professional")
        tone_instruction = ""
        if tone == "casual":
            tone_instruction = "语言风格偏向轻松易读，减少专业术语堆砌。"
        elif tone == "technical":
            tone_instruction = "语言风格偏向技术深度，多使用专业术语和数据支撑。"
        elif tone == "professional_and_insightful":
            tone_instruction = "语言风格专业且富有洞察力，兼顾技术深度与行业前瞻性。"

        # 构建系统提示词
        audience = target_audience if target_audience else scene["audience"]
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            scene_name=scene["name"],
            audience=audience,
            style=scene["style"],
            terms=scene["terms"],
        )
        if tone_instruction:
            system_prompt += f"\n额外语调要求：{tone_instruction}"

        # 构建时间节点段落
        timeline_section = ""
        if timeline:
            timeline_items = []
            for item in timeline:
                phase = item.get("phase", "")
                deadline = item.get("deadline", "")
                if phase:
                    timeline_items.append(f"- **{phase}**：{deadline}")
            if timeline_items:
                timeline_section = TIMELINE_TEMPLATE.format(
                    timeline_content="\n".join(timeline_items)
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

        # 品牌自动注入
        brand_reminder = ""
        if self.user_preferences.get("auto_brand_injection", True):
            brand_reminder = "务必在文中自然融入'吉康环境'品牌元素和技术实力展示。"

        # 字数范围
        word_count = (self.user_preferences.get("default_word_count")
                      or self.config.get("generator", {}).get("word_count", "800-1500字"))

        # 构建用户提示词
        user_prompt = USER_PROMPT_TEMPLATE.format(
            type_label=type_info["label"],
            title=topic,
            scene_name=scene["name"],
            keywords=kw,
            word_count=word_count,
            timeline_section=timeline_section,
            context_section=context_section,
            custom_section=custom_section,
        )
        if brand_reminder:
            user_prompt += f"\n{brand_reminder}"

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "scene": scene,
            "type_info": type_info,
        }

    def build_review_prompt(self, title, content, scene_type="municipal"):
        """构建审核提示词.

        Args:
            title: 文章标题.
            content: 文章内容.
            scene_type: 场景类型.

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
5. 专业性 (0-1)：专业术语密度与使用是否恰当

判定规则：五项均≥0.8→pass，任一项<0.6→fail，其他→needs_revision

严格按JSON格式输出：
{{"accuracy_score":0.0-1.0,"compliance_score":0.0-1.0,"readability_score":0.0-1.0,"brand_alignment_score":0.0-1.0,"professionalism_score":0.0-1.0,"comments":"评审意见","suggestions":["修改建议1","修改建议2"],"result":"pass/needs_revision/fail"}}"""

        user_prompt = f"""请评审以下{scene['name']}内容：

标题：{title}

内容：
{content}

输出JSON格式评审结果，必须包含suggestions字段提供具体修改建议。"""

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

    def build_revision_prompt(self, original_title, original_content,
                              evaluation_result, scene_type="municipal"):
        """构建修改提示词（基于评估结果生成修改版内容）.

        Args:
            original_title: 原文标题.
            original_content: 原文内容.
            evaluation_result: 评估结果字典，含 scores 和 suggestions.
            scene_type: 场景类型.

        Returns:
            dict: {"system_prompt": str, "user_prompt": str}
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])
        suggestions = evaluation_result.get("suggestions", [])
        suggestion_text = "\n".join(f"- {s}" for s in suggestions) if suggestions else "暂无具体建议"

        low_dims = []
        for dim in ["accuracy_score", "compliance_score", "readability_score",
                     "brand_alignment_score", "professionalism_score"]:
            score = evaluation_result.get(dim, 1.0)
            if score < 0.8:
                low_dims.append(f"{dim.replace('_score', '')}({score:.2f})")

        dim_summary = "、".join(low_dims) if low_dims else "无"

        system_prompt = f"""你是吉康环境的内容修改专家，专注于{scene['name']}领域。
请根据评估意见修改原文，重点提升以下薄弱维度：{dim_summary}。
修改时保持原文核心信息和结构，仅针对问题点进行优化。"""

        user_prompt = f"""请修改以下文章：

原标题：{original_title}

原文：
{original_content}

需要提升的维度：{dim_summary}

修改建议：
{suggestion_text}

请直接输出修改后的Markdown文章，不要包含```markdown标记。"""

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

    def get_scene_config(self, scene_type="municipal"):
        """获取场景配置.

        Args:
            scene_type: 场景类型.

        Returns:
            dict: 场景配置字典.
        """
        return SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])

    def get_type_template(self, content_type="article"):
        """获取内容类型模板信息.

        Args:
            content_type: 内容类型.

        Returns:
            dict: 内容类型模板字典.
        """
        return TYPE_TEMPLATES.get(content_type, TYPE_TEMPLATES["article"])

    def list_templates(self):
        """列出所有可用模板.

        Returns:
            dict: {模板key: 模板标签} 字典.
        """
        return {k: v["label"] for k, v in TYPE_TEMPLATES.items()}

    def list_scenes(self):
        """列出所有可用场景.

        Returns:
            dict: {场景key: 场景名称} 字典.
        """
        return {k: v["name"] for k, v in SCENE_CONFIG.items()}
