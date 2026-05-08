"""内容生成引擎 - 刘凯睿负责

功能：
- LLM驱动内容生成（有API Key时）
- 模板引擎生成（演示模式）
- 5种内容类型支持
- 市政/工业场景切换
- Markdown/HTML双格式输出
- 项目战报快捷生成
"""
import time
import json
import random
import re
from datetime import datetime
from typing import List, Optional

from src.prompt_engine import PromptEngine, SCENE_CONFIG, TYPE_TEMPLATES


class ContentGenerator:
    """内容生成引擎

    双模式架构：
    - 有LLM → 调用大模型生成
    - 无LLM → 模板引擎生成（演示用）
    """

    def __init__(self, config, prompt_engine=None):
        self.config = config
        self.prompt_engine = prompt_engine or PromptEngine(config)
        self._llm = None
        self._has_llm = False

    def _get_llm(self):
        """获取LLM实例（延迟加载，自动适配 DeepSeek）"""
        if self._llm is None and not self._has_llm:
            try:
                from langchain_openai import ChatOpenAI
                gen_config = self.config.get("generator", {})
                llm_config = self.config.get("llm", {})
                # API Key 优先级：generator.api_key > llm.api_key > 环境变量
                api_key = (gen_config.get("api_key", "")
                           or llm_config.get("api_key", "")
                           or "")
                if api_key:
                    # 检测是否为 DeepSeek（Key 以 sk- 开头且 base_url 包含 deepseek）
                    base_url = (gen_config.get("base_url")
                                or llm_config.get("base_url", "")
                                or "https://api.openai.com/v1")
                    model_name = gen_config.get("model", "gpt-4")

                    # DeepSeek 自动适配
                    if "deepseek" in base_url.lower():
                        model_name = "deepseek-chat"  # 强制覆盖
                        print(f"[Generator] 🔧 DeepSeek 模式: model={model_name}, base_url={base_url}")

                    self._llm = ChatOpenAI(
                        model=model_name,
                        api_key=api_key,
                        base_url=base_url,
                        max_tokens=gen_config.get("max_tokens", 4096),
                        temperature=gen_config.get("temperature", 0.7),
                    )
                    print(f"[Generator] ✅ LLM 就绪: model={model_name}, base_url={base_url}")
            except ImportError as e:
                print(f"[Generator] ❌ langchain-openai 未安装，无法使用 LLM: {e}")
            self._has_llm = True
        return self._llm

    def generate(self, topic, context=None, content_type="article",
                 scene_type="municipal", keywords=None,
                 custom_instructions=None, reference=None,
                 content_type_hint=None, tone=None, target_audience=None,
                 content_tone=None, **kwargs):
        """生成内容

        Args:
            topic: 文章标题
            context: 上下文（兼容旧接口）
            content_type: 内容类型
            scene_type: 场景类型
            keywords: 关键词
            custom_instructions: 额外指令
            reference: RAG参考知识
            content_type_hint: 业务规则注入的内容类型提示
            tone: 业务规则注入的语调
            target_audience: 目标受众
            content_tone: 内容语气
        """
        start_time = time.time()
        keywords = keywords or ["环保", "绿色发展"]

        llm = self._get_llm()
        if llm:
            markdown_content = self._generate_with_llm(
                topic, context, content_type, scene_type,
                keywords, custom_instructions, reference,
                content_type_hint, tone, target_audience, content_tone,
            )
            print(f"[Generator] 📝 LLM 返回内容长度: {len(markdown_content) if markdown_content else 0}")
        else:
            markdown_content = self._generate_from_template(
                topic, content_type, scene_type, keywords,
                custom_instructions, reference,
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

    def generate_batch(self, topics, **kwargs):
        """批量生成"""
        results = []
        for topic in topics:
            result = self.generate(topic, **kwargs)
            results.append(result)
        return results

    # ==================== LLM 生成 ====================
    def _generate_with_llm(self, topic, context, content_type, scene_type,
                           keywords, custom_instructions, reference,
                           content_type_hint=None, tone=None,
                           target_audience=None, content_tone=None):
        from langchain_core.messages import SystemMessage, HumanMessage
        prompts = self.prompt_engine.build_prompt(
            topic, context, content_type, scene_type,
            keywords, custom_instructions, reference,
            content_type_hint=content_type_hint,
            tone=tone,
            target_audience=target_audience,
            content_tone=content_tone,
        )
        # 使用 invoke（同步调用），而非 ainvoke（异步）
        response = self._get_llm().invoke([
            SystemMessage(content=prompts["system_prompt"]),
            HumanMessage(content=prompts["user_prompt"]),
        ])
        return response.content

    # ==================== 模板生成（演示模式）====================
    def _generate_from_template(self, topic, content_type, scene_type,
                                 keywords, custom_instructions, reference):
        scene = SCENE_CONFIG.get(scene_type, SCENE_CONFIG["municipal"])
        kw = "、".join(keywords)
        now = datetime.now().strftime("%Y年%m月")
        ref_section = ""
        if reference:
            ref_section = f"\n## 行业知识参考\n{reference}\n"

        generators = {
            "article": self._tpl_article,
            "battle_report": self._tpl_battle_report,
            "policy_analysis": self._tpl_policy_analysis,
            "tech_trend": self._tpl_tech_trend,
            "news_digest": self._tpl_news_digest,
        }
        generator = generators.get(content_type, self._tpl_article)
        return generator(topic, scene, kw, now, keywords, ref_section)

    def _tpl_article(self, title, scene, kw, now, keywords, ref):
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
{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_battle_report(self, title, scene, kw, now, keywords, ref):
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
{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_policy_analysis(self, title, scene, kw, now, keywords, ref):
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
{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_tech_trend(self, title, scene, kw, now, keywords, ref):
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
{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    def _tpl_news_digest(self, title, scene, kw, now, keywords, ref):
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
{ref}
---

*吉康环境 —— 让绿色成为生产力*
"""

    # ==================== HTML 转换 ====================
    def _markdown_to_html(self, markdown_text: str) -> str:
        try:
            import markdown as md
            html = md.markdown(markdown_text, extensions=["extra", "tables", "toc"])
        except ImportError:
            # 简单回退
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
