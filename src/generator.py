"""内容生成引擎 - 刘凯睿负责

功能：
- LLM驱动内容生成（有API Key时）
- 模板引擎生成（演示模式）
- 5种内容类型支持
- 市政/工业场景切换
- Markdown/HTML双格式输出
- 项目战报快捷生成
- 时间节点感知生成
- 基于评估建议的重新生成
"""
import time
import json
import random
import re
from datetime import datetime
from typing import List, Optional

from src.prompt_engine import PromptEngine, SCENE_CONFIG, TYPE_TEMPLATES


class ContentGenerator:
    """内容生成引擎.

    双模式架构：
    - 有LLM → 调用大模型生成
    - 无LLM → 模板引擎生成（演示用）

    Attributes:
        config: 全局配置字典.
        prompt_engine: 提示词引擎实例.
    """

    def __init__(self, config, prompt_engine=None):
        """初始化内容生成引擎.

        Args:
            config: 全局配置字典.
            prompt_engine: 提示词引擎实例，默认自动创建.
        """
        self.config = config
        self.prompt_engine = prompt_engine or PromptEngine(config)
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
                        max_tokens=gen_config.get("max_tokens", 4096),
                        temperature=gen_config.get("temperature", 0.7),
                    )
            except ImportError:
                pass
            self._has_llm = True
        return self._llm

    def generate(self, topic, context=None, content_type="article",
                 scene_type="municipal", keywords=None,
                 custom_instructions=None, reference=None,
                 timeline=None):
        """生成内容.

        Args:
            topic: 文章标题.
            context: 上下文（兼容旧接口）.
            content_type: 内容类型，可选值：
                article/battle_report/policy_analysis/tech_trend/news_digest.
            scene_type: 场景类型，可选值：municipal/industrial.
            keywords: 关键词列表.
            custom_instructions: 额外指令.
            reference: RAG参考知识.
            timeline: 时间节点列表，格式为 [{"phase": str, "deadline": str}].

        Returns:
            dict: {"markdown": str, "html": str, "generation_time_ms": int,
                   "content_type": str, "scene_type": str}
        """
        start_time = time.time()
        keywords = keywords or ["环保", "绿色发展"]

        # 应用场景业务规则（如 industrial_humidity_solution）
        (content_type, keywords, custom_instructions,
         content_type_hint, tone, target_audience) = self._apply_business_rules(
            topic, content_type, scene_type, keywords, custom_instructions,
        )

        llm = self._get_llm()
        if llm:
            markdown_content = self._generate_with_llm(
                topic, context, content_type, scene_type,
                keywords, custom_instructions, reference, timeline,
                content_type_hint=content_type_hint, tone=tone,
                target_audience=target_audience,
            )
        else:
            markdown_content = self._generate_from_template(
                topic, content_type, scene_type, keywords,
                custom_instructions, reference, timeline,
            )

        html_content = self._markdown_to_html(markdown_content)
        generation_time = int((time.time() - start_time) * 1000)

        return {
            "markdown": markdown_content,
            "html": html_content,
            "generation_time_ms": generation_time,
            "content_type": content_type,
            "scene_type": scene_type,
        }

    def regenerate(self, original_title, original_content,
                   evaluation_result, scene_type="municipal"):
        """基于评估结果重新生成内容.

        Args:
            original_title: 原文标题.
            original_content: 原文Markdown内容.
            evaluation_result: 评估结果字典，含 scores 和 suggestions.
            scene_type: 场景类型.

        Returns:
            dict: 同 generate() 返回格式.
        """
        start_time = time.time()

        llm = self._get_llm()
        if llm:
            markdown_content = self._regenerate_with_llm(
                original_title, original_content,
                evaluation_result, scene_type,
            )
        else:
            markdown_content = self._regenerate_from_template(
                original_title, original_content,
                evaluation_result, scene_type,
            )

        html_content = self._markdown_to_html(markdown_content)
        generation_time = int((time.time() - start_time) * 1000)

        return {
            "markdown": markdown_content,
            "html": html_content,
            "generation_time_ms": generation_time,
            "content_type": "revision",
            "scene_type": scene_type,
        }

    def generate_batch(self, topics, **kwargs):
        """批量生成内容.

        Args:
            topics: 主题列表.
            **kwargs: 传递给 generate() 的其他参数.

        Returns:
            list[dict]: 生成结果列表.
        """
        results = []
        for topic in topics:
            result = self.generate(topic, **kwargs)
            results.append(result)
        return results

    # ==================== 业务规则 ====================

    def _apply_business_rules(self, topic, content_type, scene_type,
                              keywords, custom_instructions):
        """应用场景业务规则，根据场景类型自动调整生成参数.

        适用于特定解决方案场景（如 industrial_humidity_solution），
        自动注入地理策略、时间策略、内容类型提示等业务规则。

        Args:
            topic: 文章标题.
            content_type: 原始内容类型.
            scene_type: 场景类型.
            keywords: 原始关键词.
            custom_instructions: 原始自定义指令.

        Returns:
            tuple: (adjusted_content_type, adjusted_keywords,
                    adjusted_custom_instructions, content_type_hint,
                    tone, target_audience)
        """
        content_type_hint = None
        tone = None
        target_audience = None

        if scene_type == "industrial_humidity_solution":
            # === 地理策略：根据关键词注入地域相关信息 ===
            geo_keywords = {
                "广东": ["广东地区高温高湿气候特点", "广东环保法规要求"],
                "华东": ["华东地区梅雨季湿度挑战", "长三角环保标准"],
                "北方": ["北方地区冬季干燥采暖需求", "北方工业区环保要求"],
                "西南": ["西南地区高湿环境治理", "川渝环保政策"],
            }
            extra_kw = []
            for region, region_kw in geo_keywords.items():
                if region in str(topic) or region in str(keywords):
                    extra_kw.extend(region_kw)
                    break
            keywords = list(keywords or []) + extra_kw

            # === 时间策略：根据当前月份调整 ===
            month = datetime.now().month
            if month in (3, 4, 5):
                season_hint = "当前正值春夏交替，回南天/梅雨季将至，湿度控制需求旺盛"
            elif month in (6, 7, 8):
                season_hint = "当前为夏季高温高湿期，工业除湿需求达到峰值"
            elif month in (9, 10, 11):
                season_hint = "当前为秋季干燥期，但部分工业场景仍需精确控湿"
            else:
                season_hint = "当前为冬季，部分北方工业区需兼顾采暖与湿度控制"
            extra_instructions = f"\n[季节背景] {season_hint}。"

            # === 内容类型提示 ===
            content_type_hint = "technical_analysis"
            tone = "professional_and_insightful"
            target_audience = "工业环保工程师、企业EHS负责人"

            # 确保关键词包含核心术语
            core_terms = ["湿度控制", "节能降耗", "恒温恒湿"]
            for term in core_terms:
                if term not in keywords:
                    keywords.append(term)

            # 组装自定义指令
            custom_instructions = (custom_instructions or "") + extra_instructions

        return (content_type, keywords, custom_instructions,
                content_type_hint, tone, target_audience)

    # ==================== LLM 生成 ====================

    def _generate_with_llm(self, topic, context, content_type, scene_type,
                           keywords, custom_instructions, reference, timeline,
                           content_type_hint=None, tone=None,
                           target_audience=None):
        """使用LLM生成内容.

        Args:
            topic: 文章标题.
            context: 上下文信息.
            content_type: 内容类型.
            scene_type: 场景类型.
            keywords: 关键词列表.
            custom_instructions: 额外指令.
            reference: RAG参考知识.
            timeline: 时间节点列表.
            content_type_hint: 内容类型提示（由业务规则注入）.
            tone: 写作语气（由业务规则注入）.
            target_audience: 目标受众（由业务规则注入）.

        Returns:
            str: 生成的Markdown内容.
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        prompts = self.prompt_engine.build_prompt(
            topic, context, content_type, scene_type,
            keywords, custom_instructions, reference, timeline,
            content_type_hint=content_type_hint, tone=tone,
            target_audience=target_audience,
        )
        response = self._get_llm().invoke([
            SystemMessage(content=prompts["system_prompt"]),
            HumanMessage(content=prompts["user_prompt"]),
        ])
        return response.content

    def _regenerate_with_llm(self, original_title, original_content,
                             evaluation_result, scene_type):
        """使用LLM重新生成内容.

        Args:
            original_title: 原文标题.
            original_content: 原文内容.
            evaluation_result: 评估结果.
            scene_type: 场景类型.

        Returns:
            str: 修改后的Markdown内容.
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        prompts = self.prompt_engine.build_revision_prompt(
            original_title, original_content,
            evaluation_result, scene_type,
        )
        response = self._get_llm().invoke([
            SystemMessage(content=prompts["system_prompt"]),
            HumanMessage(content=prompts["user_prompt"]),
        ])
        return response.content

    # ==================== 模板生成（演示模式）====================

    def _generate_from_template(self, topic, content_type, scene_type,
                                keywords, custom_instructions, reference,
                                timeline=None):
        """使用模板引擎生成内容（演示模式）.

        Args:
            topic: 文章标题.
            content_type: 内容类型.
            scene_type: 场景类型.
            keywords: 关键词列表.
            custom_instructions: 额外指令.
            reference: RAG参考知识.
            timeline: 时间节点列表.

        Returns:
            str: 生成的Markdown内容.
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])
        kw = "、".join(keywords)
        now = datetime.now().strftime("%Y年%m月")
        ref_section = ""
        if reference:
            ref_section = f"\n## 行业知识参考\n{reference}\n"

        # 时间节点段落
        timeline_section = ""
        if timeline:
            items = []
            for item in timeline:
                phase = item.get("phase", "")
                deadline = item.get("deadline", "")
                if phase:
                    items.append(f"- **{phase}**：{deadline}")
            if items:
                timeline_section = f"\n## 📅 时间节点\n" + "\n".join(items) + "\n"

        generators = {
            "article": self._tpl_article,
            "battle_report": self._tpl_battle_report,
            "policy_analysis": self._tpl_policy_analysis,
            "tech_trend": self._tpl_tech_trend,
            "news_digest": self._tpl_news_digest,
        }
        generator = generators.get(content_type, self._tpl_article)
        return generator(topic, scene, kw, now, keywords, ref_section, timeline_section)

    def _regenerate_from_template(self, original_title, original_content,
                                  evaluation_result, scene_type):
        """基于评估结果模板化重新生成（演示模式）.

        Args:
            original_title: 原文标题.
            original_content: 原文内容.
            evaluation_result: 评估结果.
            scene_type: 场景类型.

        Returns:
            str: 修改后的Markdown内容.
        """
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])
        suggestions = evaluation_result.get("suggestions", [])
        suggestion_text = "\n".join(f"- {s}" for s in suggestions) if suggestions else "- 暂无具体建议"

        # 在原文基础上追加修改说明
        return f"""# {original_title}（修改版）

> 基于评估意见修改 | {scene['name']} | {datetime.now().strftime("%Y年%m月")}

## 📝 修改说明

本次修改针对以下问题进行优化：
{suggestion_text}

---

{original_content}

---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_article(self, title, scene, kw, now, keywords, ref, timeline_section=""):
        return f"""# {title}

> 本文由 AuraScribe AI 自动生成 | {scene['name']} | {now}

## 行业背景

当前，{scene['name']}领域正经历深刻变革。随着国家环保政策持续收紧、公众环保意识不断提升，{kw}等方向已成为行业关注的焦点。吉康环境凭借多年深耕，始终站在行业前沿，以技术创新驱动绿色发展。

## 现状与挑战

在{scene['name']}领域，当前面临的核心挑战包括：

- **政策要求升级**：新标准对{keywords[0] if keywords else '环保治理'}提出更高要求，企业需加快技术升级步伐
- **成本压力增大**：原材料价格上涨，叠加环保投入增加，企业运营成本持续攀升
- **技术迭代加速**：传统工艺已难以满足新标准，亟需引入新技术、新工艺
- **数据化管理需求**：从粗放式管理向精细化、数字化管理转型迫在眉睫

## 吉康环境的解决方案

### 1. 技术创新驱动

吉康环境持续加大研发投入，核心技术包括：

- **高效处理工艺**：膜分离+催化氧化组合工艺，处理效率提升40%
- **智能监控平台**：IoT+AI实时监测系统，7×24小时精准管控
- **资源化利用**：废弃物转化为再生资源，实现循环经济闭环

### 2. 项目落地保障

| 服务环节 | 吉康环境优势 |
|---------|------------|
| 方案设计 | 定制化方案，覆盖100+行业场景 |
| 工程实施 | 专业化施工团队，按期交付率99% |
| 运维管理 | 全生命周期服务，远程运维+定期巡检 |
| 达标保障 | 出水/排放达标率100% |

### 3. 数字化赋能

吉康环境自主研发的智慧环保管理平台，帮助客户降低运营成本20%以上。

## 成功案例

吉康环境已在全国30个省市成功实施200+项目，客户满意度≥95%。

## 展望

未来，吉康环境将继续深耕{scene['name']}领域，以"让绿色成为生产力"为使命，持续为客户创造价值。
{timeline_section}{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_battle_report(self, title, scene, kw, now, keywords, ref, timeline_section=""):
        projects = ["滨海新区污水处理提标改造工程", "长三角化工园区VOCs综合治理项目",
                     "西部工业园区废水零排放示范工程", "城市固废资源化循环经济产业园"]
        project = random.choice(projects)
        return f"""# 项目战报 | {project}

> 吉康环境 · {scene['name']}项目战报 | {now}

---

## 📋 项目概况

| 项目信息 | 详情 |
|---------|------|
| 项目名称 | {project} |
| 项目类型 | {scene['name']} |
| 建设周期 | 8个月 |
| 项目投资 | 1.2亿元 |
| 服务模式 | EPC+O（设计-采购-施工-运维一体化） |
| 运行状态 | ✅ 稳定运行 |

## 🎯 项目目标

- 出水/排放指标优于国家一级A标准
- 运行成本较同类项目降低20%以上
- 实现智能化运维管理

## 🔧 技术方案

### 核心工艺路线

```
原水 → 预处理 → 生化处理(A²O+MBBR) → MBR膜过滤 → 深度处理 → 达标出水
                                                      ↓
                        污泥 → 浓缩脱水 → 热水解+厌氧消化 → 资源化利用
```

### 关键技术亮点

1. **MBBR+MBR组合工艺**：兼顾处理效率与出水水质
2. **AI智能加药系统**：节省药剂成本30%
3. **数字孪生运维平台**：故障预警响应<5分钟
4. **污泥资源化**：热水解+厌氧消化产沼气发电

## 📊 运行数据

| 指标 | 设计值 | 实际值 | 达标情况 |
|------|--------|--------|---------|
| COD | ≤50 mg/L | 28 mg/L | ✅ 优于标准 |
| NH₃-N | ≤5 mg/L | 1.2 mg/L | ✅ 优于标准 |
| TP | ≤0.5 mg/L | 0.18 mg/L | ✅ 优于标准 |
| SS | ≤10 mg/L | 4 mg/L | ✅ 优于标准 |

## 🏆 项目成效

- ✅ 出水达标率 **100%**
- ✅ 运行成本降低 **34%**
- ✅ 污泥减量 **55%**
- ✅ 智能化覆盖率 **90%**
- ✅ 客户满意度 **98分**

## 💬 客户评价

> "吉康环境的技术方案完全超出预期，不仅稳定达标，运行成本还比原方案降低了三分之一。"
> —— 项目甲方负责人
{timeline_section}{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_policy_analysis(self, title, scene, kw, now, keywords, ref, timeline_section=""):
        return f"""# {title}

> 政策解读 | AuraScribe AI 生成 | {now}

## 政策概要

近期，国家相关部门密集出台环保领域新政策，对{kw}等方面提出新要求。

## 核心要点解读

### 一、排放标准提升

新政策明确将{keywords[0] if keywords else '污染物'}排放限值加严20%-30%，过渡期18个月。

### 二、碳减排协同推进

1. **碳排放核算纳入环保验收**：新建项目需同步提交碳排放评估报告
2. **碳交易激励**：减排量可进入碳市场交易
3. **绿色金融支持**：达标企业可获更低利率绿色信贷

### 三、数字化转型要求

- 在线监测数据实时上传监管平台
- 鼓励采用AI技术优化运行参数

## 对行业的影响分析

| 时间维度 | 影响预测 |
|---------|---------|
| 短期(6-12月) | 技改需求激增50%+，合规成本上升15%-25% |
| 中期(1-2年) | 行业集中度提升，综合服务需求增长 |
| 长期(2-3年) | 创新驱动发展，新技术市场空间大幅拓展 |

## 吉康环境的应对策略

| 策略维度 | 具体举措 |
|---------|---------|
| 技术储备 | 新一代技术体系可满足新标准要求 |
| 产品升级 | 智慧环保平台迭代至3.0版本 |
| 服务延伸 | "环保管家"一站式服务 |
| 碳管理 | 碳排放核算体系，助力碳资产增值 |

## 建议

1. 提前布局改造，降低成本
2. 选择技术实力雄厚的服务商
3. 将碳减排纳入总体考量
{timeline_section}{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_tech_trend(self, title, scene, kw, now, keywords, ref, timeline_section=""):
        return f"""# {title}

> 技术趋势 | AuraScribe AI 生成 | {now}

## 趋势一：AI赋能智能治理

- **智能加药**：动态调整药剂投加量，节省20%-35%成本
- **预测性维护**：机器学习故障预警，非计划停机减少70%
- **工艺优化**：强化学习优化曝气策略，能耗降低15%-25%

吉康实践：AI治水大脑已落地多个项目，水质预测准确率≥92%。

## 趋势二：膜技术持续突破

| 技术方向 | 进展 | 影响 |
|---------|------|------|
| 抗污染膜 | 通量衰减率降低50% | 延长膜寿命 |
| 高效分离膜 | 纳滤精度至分子级 | 拓展资源化回收 |
| 低能耗膜 | 能耗降低40% | 降低零排放成本 |

## 趋势三：资源化循环利用

1. **废水资源回收**：磷回收、有机物能源化、高附加值物质提取
2. **固废高值化**：危废金属回收率>98%、污泥制陶粒

## 趋势四：数字孪生与智慧运营

```
物理设施 ←→ 数字孪生模型 ←→ 智能决策
   ↑              ↓              ↑
实时数据    仿真模拟优化    自动调控指令
```
{timeline_section}{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_news_digest(self, title, scene, kw, now, keywords, ref, timeline_section=""):
        return f"""# {title}

> 行业资讯速览 | AuraScribe AI 整理 | {now}

---

## 📌 政策动态

### 1. 生态环境部发布2024年水污染防治工作要点

重点推进印染、造纸、化工等行业水污染防治，鼓励先进治理技术实现废水循环利用。

**影响**：工业废水治理需求增长30%+

### 2. 全国碳市场扩容方案确定

钢铁、水泥、铝冶炼等行业将纳入碳市场，覆盖碳排放量增至约80亿吨。

**影响**：碳管理服务市场快速扩容

---

## 🔬 技术前沿

### 3. VOCs治理新技术突破

低温等离子体+催化氧化组合工艺，处理效率95%+，成本降低30%。

### 4. 膜技术回用率达80%+

新型抗污染膜使膜寿命延长50%，在电子、制药等行业广泛应用。

---

## 📊 市场观察

### 5. 固废处理市场突破8000亿元

危废处置、建筑垃圾资源化年增速超20%。
{timeline_section}{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    # ==================== HTML 转换 ====================

    def _markdown_to_html(self, markdown_text: str) -> str:
        """将Markdown转换为HTML.

        Args:
            markdown_text: Markdown格式文本.

        Returns:
            str: HTML格式文本.
        """
        try:
            import markdown as md
            html = md.markdown(markdown_text, extensions=["extra", "tables", "toc"])
        except ImportError:
            html = markdown_text.replace("\n", "<br>")
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body{{font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;max-width:800px;margin:0 auto;padding:24px;line-height:1.8;color:#2c3e2c}}
h1{{color:#1a5c2a;border-bottom:3px solid #2d8c4e;padding-bottom:8px}}h2{{color:#2d8c4e}}h3{{color:#3a7d3a}}
blockquote{{border-left:4px solid #2d8c4e;padding:8px 16px;color:#666;background:#f5faf5;border-radius:0 4px 4px 0}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}th{{background:#e8f5e9;color:#1a5c2a}}th,td{{border:1px solid #c8e6c9;padding:8px 14px}}pre{{background:#1a2a1a;color:#e0e0e0;padding:16px;border-radius:6px;overflow-x:auto}}code{{background:#f0f5f0;padding:2px 6px;border-radius:3px}}
</style></head><body>{html}</body></html>"""
