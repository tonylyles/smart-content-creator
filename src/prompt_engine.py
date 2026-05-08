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
    "industrial_humidity_solution": {
        "name": "高湿环境除湿解决方案",
        "audience": "华南地区工业企业EHS负责人、工厂厂长、污泥处理决策者",
        "style": "痛点驱动、数据佐证、注重节能降本与除湿效率，兼具广府文化亲切感",
        "terms": "低温除湿干化、回南天、高湿环境、闭式循环、非牛顿流体脱水、涡旋式热泵、含水率",
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

## 吉康环境核心产品（必须体现在文章中）

### 产品1：GKC系列低温除湿干化设备
- 型号：GKC-500/1000/2000/3000，处理量500-3000kg/批次
- 工作温度40-60℃，含水率从80%降至30%以下
- 节能率40%-60%，核心部件：涡旋式热泵压缩机
- 适用：市政污泥、工业污泥、食品渣料、化工废料

### 产品2：闭式循环除湿系统
- 闭式循环冷凝除湿+热泵驱动，零废气排放
- vs传统开式干燥：热量回收再利用，无尾气排放
- 智能控制：PLC+HMI自动调节温湿度

### 产品3：污泥低温除湿干化机
- 进料含水率80%-85% → 出料≤30%
- 能耗0.25-0.35 kWh/kg·H₂O，SUS304不锈钢
- 污泥减量60%以上

### 典型客户案例
- 广州某市政污水厂：GKC-2000，日处理20吨，年省300万元
- 东莞某食品厂：闭式循环系统，湿度85%→40%，合格率升15%
- 佛山某化工厂：非牛顿流体脱水，效率升25%，能耗降45%

### 品牌Slogan
"闭式循环，干化未来" / "低温除湿，绿色赋能"

请确保：
1. 必须引用具体产品型号和技术参数（不能只泛泛而谈）
2. 至少包含1个客户案例
3. 配图建议：每段关键内容后标注[配图建议：xxx]
4. 技术准确、数据真实、符合品牌调性
5. 输出格式为Markdown"""

USER_PROMPT_TEMPLATE = """请撰写一篇{type_label}，标题为：{title}

要求：
- 品牌名称：吉康环境
- 场景类型：{scene_name}
- 关键词：{keywords}
- 输出格式：Markdown
- 字数：{word_count}
- 必须引用吉康环境具体产品型号和参数（GKC系列/闭式循环系统等）
- 必须包含至少1个真实客户案例（可用提供的案例）
- 每个核心段落末尾标注配图建议，格式：`[配图建议：图片描述]`
- 配图建议类型：产品实拍、技术流程图、数据对比图、场景效果图、客户现场图
- 文章末尾加上品牌签名：`*吉康环境 · 低温除湿干化领域领跑者*`

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
                     custom_instructions=None, reference=None,
                     content_type_hint=None, tone=None, target_audience=None,
                     content_tone=None):
        """构建完整提示词

        Args:
            topic: 文章标题/主题
            context: 上下文信息（兼容旧接口）
            content_type: 内容类型 (article/battle_report/policy_analysis/tech_trend/news_digest)
            scene_type: 场景类型 (municipal/industrial/industrial_humidity_solution)
            keywords: 关键词列表
            custom_instructions: 额外指令
            reference: RAG检索到的参考知识
            content_type_hint: 业务规则注入的内容类型提示（如 technical_analysis）
            tone: 业务规则注入的语调（如 professional_and_insightful）
            target_audience: 业务规则注入的目标受众覆盖
            content_tone: 内容语气（如 friendly_and_casual 广府亲切感）

        Returns:
            dict: {"system_prompt": str, "user_prompt": str}
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])

        # content_type_hint 可以覆盖实际内容类型
        effective_content_type = content_type
        if content_type_hint == "technical_analysis":
            effective_content_type = "tech_trend"  # 映射到技术趋势模板
        type_info = TYPE_TEMPLATES.get(effective_content_type, TYPE_TEMPLATES["article"])

        kw = "、".join(keywords) if keywords else "环保、绿色发展"

        # 构建语调描述
        tone_desc = ""
        if tone == "professional_and_insightful":
            tone_desc = "语调要求：专业严谨且富有洞见，适合B2B决策者周末深度阅读。"
        if content_tone == "friendly_and_casual":
            tone_desc += "兼具广府文化的亲切感，适当使用粤语文化元素（如'饮茶'等）拉近距离。"

        # 受众覆盖
        audience = scene["audience"]
        if target_audience:
            audience = f"{audience}、{target_audience}"

        # 构建系统提示词
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            scene_name=scene["name"],
            audience=audience,
            style=scene["style"],
            terms=scene["terms"],
        )
        if tone_desc:
            system_prompt += f"\n{tone_desc}"

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
        word_count = self.config.get("generator", {}).get("word_count", "1500-2500字")

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
