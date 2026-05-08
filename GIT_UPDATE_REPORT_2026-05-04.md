# AuraScribe 智能内容创作平台 — Git 更新分析报告

> **更新时间**：2026-05-04  
> **提交版本**：`a87c42e` feat: 刘凯睿 - 完成RAG检索、内容生成、提示词引擎、质量评估、用户界面模块  
> **分析人**：橙子 🦞  

---

## 一、更新概览

本次 `git pull` 拉取了 3 个新提交，核心变化是 **刘凯睿负责的 RAG + 生成 + 评估 + UI 四大模块全面落地**，以及 **胡圳刚负责的爬虫模块**。

| 指标 | 数据 |
|------|------|
| 变更文件数 | 8 个（+1 删除） |
| 新增代码行 | **+1412 行 / -40 行** |
| 新增目录 | `src/rag/`（3 文件）、`src/spiders/`（5 文件）已存在但本次有更新 |
| 删除文件 | 竞赛文件夹内的 Word 临时锁文件（`~$...docx`） |

---

## 二、依赖变更

### requirements.txt 完整内容

```
# 爬虫依赖
requests>=2.31.0
beautifulsoup4>=4.12.2

# RAG相关
sentence-transformers>=2.2.2    ← 新增
faiss-cpu>=1.7.4                 ← 新增（已有）

# 定时任务
schedule>=1.2.0                  ← 新增

# 数据库
sqlite3                          ← Python 内置，无需 pip 安装

# 其他
python-dotenv>=1.0.0
```

### 新增依赖说明

| 库 | 版本 | 用途 | 安装状态 |
|---|------|------|:---:|
| `sentence-transformers` | ≥2.2.2 | 本地 Embedding 向量化模型（RAG 语义检索基础） | ✅ 已安装 (5.4.1) |
| `faiss-cpu` | ≥1.7.4 | FAISS 向量相似度搜索（CPU 版） | ✅ 已安装 (1.13.2) |
| `beautifulsoup4` | ≥4.12.2 | HTML 解析（新闻爬虫用） | ✅ 已安装 (4.14.3) |
| `schedule` | ≥1.2.0 | 定时任务调度器 | ✅ 已安装 (1.2.2) |

> **可选依赖**（代码中 try/except 降级处理，不装也能跑）：  
> `gradio` → Web 界面 | `langchain-openai` + `qdrant-client` → LLM 生产模式 | `markdown` → HTML 渲染

---

## 三、架构变化详解

### 3.1 `src/rag/` — RAG 检索增强生成模块（刘凯睿）

#### 模块结构

```
src/rag/
├── __init__.py       # 导出 RAGRetriever + VectorDB
├── retriever.py      # 混合检索器（133 行）
└── vector_db.py      # 向量数据库接口（234 行）
```

#### 核心设计：三级降级策略

```
优先级    检索方式              条件                    能力
───────── ──────────────────  ─────────────────────  ─────────────
  ① 最高   Qdrant 向量语义检索   有 Qdrant + Embedding   语义理解、精准召回
  ② 中等   knowledge_base 关键词 有知识库数据            关键词匹配 + 相关性排序
  ③ 保底   基础关键词匹配        无任何外部依赖           停用词过滤 + 简单匹配
```

#### RAGRetriever（retriever.py）

| 方法 | 功能 |
|------|------|
| `retrieve(query, top_k, category, scene_type)` | 主入口，按优先级尝试三种检索 |
| `_keyword_search()` | 停用词过滤 + 正则分词提取中文/英文关键词 |
| `_rank_results()` | 综合评分 = 基础分 + 关键词命中奖励（每词 +0.1，上限 0.3） |
| `expand_query(query, scene_type)` | 查询扩展——内置环保同义词词典（如"污水处理"→"水处理/污水治理/废水处理"），并按场景追加"市政"/"工业"后缀 |

#### VectorDB（vector_db.py）

| 方法 | 功能 |
|------|------|
| `add_documents(docs)` | 文档分块（chunk_size=500, overlap=50）→ 向量化 → 存储 |
| `search(query, top_k, category)` | 语义检索或内存关键词回退 |
| `delete(doc_ids)` | 删除文档（Qdrant + 内存双清理） |
| `_chunk_text(text)` | 段落级分块，按 `\n\n` 切割，保留重叠区域保证上下文连贯 |

**双模式运行**：
- **生产模式**：Qdrant + OpenAI Embedding → 向量余弦相似度检索
- **演示模式**：Python list 内存存储 → 关键词集合交集计分

---

### 3.2 `src/spiders/` — 爬虫模块（胡圳刚）

#### 模块结构

```
src/spiders/
├── __init__.py           # 导出 4 个类
├── content_classifier.py # 内容分类器（事件/技术/政策）
├── release_planner.py    # 发布节奏规划器
├── news_crawler.py       # 新闻爬虫（11.9 KB，最重文件）
└── spider_manager.py     # 爬虫管理器（编排完整工作流）
```

#### SpiderManager 完整工作流

```
crawl_and_classify()          plan_release()
        │                           │
  NewsCrawler.crawl()         ReleasePlanner.generate_schedule()
        │                           │
  ContentClassifier.classify()     │
  (自动识别事件/技术/政策)          │
        │                           │
        └───────► full_workflow() ◄┘
                    │
              输出 JSON：
              ├── news_list[]（带分类标签和置信度）
              ├── plans[]（发布计划，含日期/类型/渠道）
              └── summary（统计分布）
```

**支持配置项**：
- 爬取类别：`tech` / `policy` / `industry`
- 发布频率：`daily` / `weekly` / `biweekly` / `monthly`
- 每日上限：默认 3 篇

---

## 四、核心逻辑改动点

### 4.1 `src/evaluator.py` — 质量评估器（+233 行）

#### 双模式架构

```
有 LLM API Key          无 LLM（默认）
───────────────         ─────────────
LLM 深度语义评审         多维规则引擎评审
→ 调用 ChatOpenAI       → 关键词匹配 + 启发式打分
→ JSON 结构化输出        → 四维加权评分
```

#### 四维评估体系

| 维度 | 权重 | 规则引擎评分逻辑 |
|------|------|----------------|
| **技术准确率** | 25% | 场景术语命中（每个 +0.03，上限 +0.15）+ 数据支撑（百分比/小数点，每个 +0.01，上限 +0.05），基准 0.82 |
| **合规性** | 25% | 广告法违禁词库扫描（17 个禁词，命中 -0.30）+ 正面词汇奖励（"符合/达标/合规"，每个 +0.02），基准 0.90 |
| **可读性** | 25% | 标题长度 10-60 字（+0.05）+ 内容长度 >500（+0.02）+ >1000（+0.03）+ 标题层级（+0.01/个）+ 表格存在（+0.02），基准 0.85 |
| **品牌调性匹配** | 25% | "吉康环境"出现（+0.08）+ 品牌口号/价值观命中（+0.02/个，上限 +0.04），基准 0.88 |

#### 判定标准

| 结果 | 条件 |
|------|------|
| ✅ **pass** | 四维均 ≥ 0.8 |
| ⚠️ **needs_revision** | 任一 < 0.8 但无 < 0.6 |
| ❌ **fail** | 任一维度 < 0.6 |

#### 合规违禁词库（17 词）

```
绝对 | 第一 | 唯一 | 最佳 | 顶级 | 首屈一指 |
100%有效 | 包治 | 根治 | 零风险 | 无副作用 |
国家级 | 最高级 | 王牌 | 领袖品牌
```

#### 场景专业术语

**市政（14 词）**：污水处理、固废处理、环境监测、雨污分流、提标改造、MBR、MBBR、生化处理、膜过滤、活性炭、COD、氨氮

**工业（11 词）**：VOCs、废气治理、零排放、危废处置、清洁生产、催化燃烧、反渗透、蒸发结晶、DTRO、EDR、MVR

---

### 4.2 `src/generator.py` — 内容生成引擎（+417 行）

#### 双模式架构

```
有 LLM API Key          无 LLM（模板演示模式）
───────────────         ─────────────────────
ChatOpenAI.invoke()     5 种内置 Jinja 风格模板
→ 动态 Prompt 构建      → 场景化占位符填充
→ RAG 知识注入          → 随机项目名/数据变化
```

#### 5 种内容类型模板

| 类型 key | 名称 | 结构 | 特色 |
|----------|------|------|------|
| `article` | 深度行业文章 | 背景→挑战→方案→案例→展望 | 含吉康解决方案表格 |
| `battle_report` | 项目战报 | 概况→目标→技术→数据→成效→评价 | **随机项目名** + 运行数据对比表 + 客户评价引用 |
| `policy_analysis` | 政策解读 | 概要→要点→影响→策略→建议 | 含时间维度影响预测表 |
| `tech_trend` | 技术趋势分析 | AI/膜技术/资源化/数字孪生四大趋势 | 含技术进展对比表 + 架构图 |
| `news_digest` | 资讯摘要 | 政策动态/技术前沿/市场观察 | 分类资讯速览 |

#### 战报模板随机池

```python
projects = [
    "滨海新区污水处理提标改造工程",
    "长三角化工园区VOCs综合治理项目",
    "西部工业园区废水零排放示范工程",
    "城市固废资源化循环经济产业园"
]
```

每次生成战报时随机选取一个，并附带完整的工艺流程图（ASCII art）、运行数据表（COD/氨氮/TP/SS 对比设计值与实际值）、成效指标（达标率/成本降低/减量率等）。

#### 输出格式

- **Markdown**：原始生成内容
- **HTML**：自动渲染，含品牌绿色主题 CSS（`#1a5c2a` / `#2d8c4e` 配色，衬线字体栈，圆角代码块）

---

### 4.3 `src/prompt_engine.py` — 提示词引擎（+240 行）

#### 场景配置差异

| 维度 | municipal（市政） | industrial（工业） |
|------|------------------|-------------------|
| 受众 | 市政部门决策者、环保局官员、城市管理者 | 企业EHS负责人、工厂管理层、工业环保工程师 |
| 风格 | 专业、权威、注重政策合规性和社会效益 | 技术导向、数据驱动、注重经济效益和合规要求 |
| 术语 | 污水处理厂、固废处理、环境监测、雨污分流、提标改造 | 废气治理、废水零排放、VOCs治理、危废处置、清洁生产 |

#### Prompt 构建流程

```
用户输入 (topic, type, scene, keywords, reference)
                │
        ┌───────┴───────┐
        ▼               ▼
  System Prompt    User Prompt
  (角色+受众+风格)  (标题+类型+关键词+字数
   +术语+品牌名      +知识参考+额外要求)
        │               │
        └───────┬───────┘
                ▼
        {"system_prompt": "...",
         "user_prompt": "..."}
```

新增 `build_review_prompt()` 为 Evaluator 提供 LLM 评审提示词（JSON 格式约束输出）。

---

### 4.4 `src/ui.py` — Gradio Web界面（+190 行）

#### 界面布局

```
🌿 AuraScribe 智能内容创作平台
├── Tab 1: ✨ AI创作
│   ├── 标题输入框
│   ├── 内容类型下拉（5 选 1）
│   ├── 场景类型下拉（municipal / industrial）
│   ├── 关键词输入（逗号分隔）
│   ├── [🚀 一键生成] 按钮
│   ├── Markdown 预览区
│   └── 审核结果文本框（四维分数 + 评论）
│
├── Tab 2: 🔍 知识检索
│   ├── 搜索查询输入
│   ├── [检索] 按钮
│   └── Markdown 结果列表（标题 + 相似度 + 摘要）
│
├── Tab 3: 📋 质量评估
│   ├── 标题输入
│   ├── 内容文本域（10 行）
│   ├── [评估] 按钮
│   └── JSON 评估结果
│
└── Tab 4: 📊 系统状态
    ├── [刷新状态] 按钮
    └── JSON 状态信息
```

**降级策略**：Gradio 未安装时自动切换到控制台交互菜单模式（4 选项 + 循环）。

---

## 五、功能测试记录

### 测试环境

| 项目 | 值 |
|------|-----|
| OS | Windows 11 (x64) |
| Python | 3.13 |
| 运行模式 | Demo/Template（无 API Key） |
| 测试时间 | 2026-05-04 09:56 GMT+8 |

### 依赖安装结果

```
✅ sentence_transformers 5.4.1
✅ torch                 2.11.0+cpu
✅ transformers          5.7.0
✅ faiss-cpu             1.13.2
✅ beautifulsoup4        4.14.3
✅ schedule              1.2.2
```

### 端到端测试

**测试命令**：直接调用各模块（绕过 WorkflowEngine）

```python
gen.generate(
    topic='2024年市政污水处理技术趋势分析',
    content_type='article',
    scene_type='municipal',
    keywords=['污水处理', 'MBR膜技术', '绿色发展']
)
```

**测试结果**：

| 指标 | 结果 |
|------|------|
| 生成耗时 | 4263 ms |
| 内容类型 | article ✅ |
| 场景类型 | municipal ✅ |
| **综合得分** | **0.96 / 1.00** |
| **判定结果** | **PASS ✅** |
| 技术准确率 | 0.93 |
| 合规性 | 0.92 |
| 可读性 | 0.99 |
| 品牌匹配度 | 1.00 |

### 已知问题

| 问题 | 原因 | 影响 | 建议 |
|------|------|------|------|
| `WorkflowEngine.stages` 为空 | 流水线未注册 stage | `main.py` 启动后 UI 操作返回空结果 | 需要与曾睿确认 stage 接口定义后补上注册逻辑 |
| 控制台 GBK 编码乱码 | Windows 默认 CP936 不支持 emoji/部分 Unicode | 仅影响控制台打印，不影响实际数据处理 | 文件输出/Web 界面正常 |
| `requirements.txt` 含 `sqlite3` | sqlite3 是 Python 内置模块，非 pip 包 | `pip install -r` 会报错 | 安装时跳过该行即可 |

---

## 六、启动指南

### 快速启动（演示模式）

```bash
cd C:\Users\ZhuanZ1\smart-content-creator\src
python main.py
```

→ 进入控制台交互模式（菜单：1.生成 2.检索 3.评估 4.状态 0.退出）

### Web 界面启动

```bash
pip install gradio
python main.py
# 浏览器打开 http://127.0.0.1:7860
```

### 生产模式（接入 LLM）

在 `src/.env` 或系统环境变量中配置：

```env
LLM_API_KEY=sk-your-api-key-here
BASE_URL=https://api.openai.com/v1    # 或国内代理地址
```

配置后重启即可自动切换到 LLM 生成 + 深度评审模式。

### 直接调用模块（推荐当前使用方式）

```python
import sys; sys.path.insert(0, 'src')
from src.config import load_config
from src.prompt_engine import PromptEngine
from src.generator import ContentGenerator
from src.evaluator import Evaluator

config = load_config()
pe = PromptEngine(config)
gen = ContentGenerator(config, pe)
ev = Evaluator(config, pe)

result = gen.generate(topic="你的标题", content_type="article", scene_type="municipal")
review = ev.evaluate(result["markdown"], "你的标题", "municipal")
print(review["result"])  # pass / needs_revision / fail
```

---

## 七、团队分工对照

| 成员 | 本次更新负责模块 | 文件 | 代码增量 |
|------|-----------------|------|---------|
| **刘凯睿** | RAG 检索 + 内容生成 + 提示词引擎 + 质量评估 + 用户界面 | `rag/*`, `generator.py`, `prompt_engine.py`, `evaluator.py`, `ui.py` | ~1200 行 |
| **胡圳刚** | 爬虫模块（分类/规划/抓取/管理） | `spiders/*` | ~27 KB |
| **曾睿** | 项目架构设计 + 工作流引擎（骨架已搭，stage 待对接） | `workflow.py`, `scheduler.py`, `config.py`, `main.py` | 骨架代码 |

---

*报告生成于 2026-05-04 by 橙子 🦞*
