# smart-content-creator

> 企业公众号智能内容创作与发布平台 · AI-powered content creation & publishing platform for WeChat Official Accounts

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/Gradio-4%2B-orange.svg)](https://www.gradio.app/)

一个端到端的公众号内容自动化生产流水线：从**行业资讯采集**到**知识增强生成**、**质量评估**，最终**一键发布到微信公众号**。本项目最初为环保设备企业定制，但其架构是通用的，可适配任意行业的知识库与内容风格。

## 功能特性

| 模块 | 说明 |
|------|------|
| 数据采集 | 15 个行业/政策/产品数据源，自动爬取 + 分类，支持 JS 渲染页面 |
| 知识检索 | RAG 语义检索 + 关键词混合搜索，无结果时自动回退本地知识库 |
| 内容生成 | LLM 生成 + 场景感知业务规则（地域 / 时间 / 受众 / 调性） |
| 质量评估 | 五维评估（准确率 / 合规 / 可读 / 品牌 / 专业）+ 质量子模块增强 |
| 配图建议 | 自动生成封面图 / 插图方案，含 AI 生图提示词 |
| 微信发布 | 排版适配引擎 + Selenium 自动化 + 模拟模式（本地预览 HTML） |
| 定时调度 | APScheduler + DAG Pipeline + 闭环重试 + SLA 监控 |

## 工作流程

```
数据采集 ──► 知识检索 ──► 内容生成 ──► 质量评估 ──► 微信发布
  (15源)      (RAG混合)    (LLM增强)     (五维评分)      (排版适配)
```

## 快速开始

### 环境要求

- Python 3.10+
- Docker（可选，用于 Qdrant 向量数据库）

### 安装

```bash
git clone https://github.com/tonylyles/smart-content-creator.git
cd smart-content-creator
pip install -r requirements.txt
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入你的 API Key（至少需要 LLM_API_KEY）
# LLM_API_KEY=sk-your-api-key-here
# LLM_BASE_URL=https://api.deepseek.com/v1
```

> 未配置 `LLM_API_KEY` 时，系统会以容错模式启动（生成示例内容），便于快速体验流程。

### 启动

```bash
# 方式一：一键启动（Windows）
启动.bat

# 方式二：手动启动
python run_ui.py

# 方式三：命令行全链路测试
python src/main.py
```

浏览器访问 http://127.0.0.1:7860

### 向量数据库（可选）

默认使用 Qdrant 作为向量数据库：

```bash
docker-compose up -d
```

## 项目结构

```
smart-content-creator/
├── src/
│   ├── main.py                    # 系统入口（容错装配）
│   ├── config.py                  # 全局配置
│   ├── workflow.py                # 工作流引擎
│   ├── scheduler.py               # 定时调度器 + DAG Pipeline
│   ├── prompt_engine.py           # 提示词引擎
│   ├── generator.py               # 内容生成器
│   ├── evaluator.py               # 质量评估器
│   ├── ui.py                      # Gradio Web 界面
│   ├── publisher/                 # 微信发布模块
│   │   └── wechat_publisher.py    # 发布器 + 排版适配引擎
│   ├── generator/                 # 生成子模块（排版/多模态）
│   ├── quality/                   # 质量子模块（术语/逻辑/可读性/建议）
│   ├── rag/                       # RAG 检索（混合检索 + 向量库）
│   ├── spiders/                   # 爬虫（15 数据源 + 管理 + 分类）
│   └── data_storage.py, knowledge_base.py, data_cleaner.py
├── data/
│   └── jikang_knowledge.md        # 示例知识库（可替换为你的行业知识）
├── tests/                         # 测试脚本
├── run_ui.py                      # UI 启动脚本
├── init_knowledge.py              # 知识库初始化
├── docker-compose.yml             # Qdrant 容器配置
└── requirements.txt               # Python 依赖
```

## 技术栈

- **LLM**：DeepSeek（可通过 `LLM_BASE_URL` 兼容任意 OpenAI 协议服务）
- **向量数据库**：Qdrant
- **Web 框架**：Gradio
- **爬虫**：requests + BeautifulSoup + Selenium
- **调度**：APScheduler + SQLAlchemy

## 如何适配你的行业

本项目采用「场景感知」设计，通过配置即可适配不同行业：

1. 替换 `data/jikang_knowledge.md` 为你所在领域的知识库
2. 在 `src/config.py` 中调整「地域 → 场景」映射与业务规则
3. 在 `src/prompt_engine.py` 中定制内容调性与受众
4. 更新 `src/spiders/news_crawler.py` 中的数据源列表

## 贡献

欢迎提交 Issue 与 Pull Request，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。行为规范见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可证

[MIT](LICENSE)

## 免责声明

本项目的公众号发布功能仅用于自动化内容排版与流程演示，请遵守微信公众号平台的相关规范与当地法律法规。`data/` 目录下的知识库内容仅为示例，不代表任何企业的官方立场。
