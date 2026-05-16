# smart-content-creator

企业公众号智能内容创作与发布平台 — 广东吉康环境系统科技有限公司

## 快速启动

1. 双击 `启动.bat` 即可启动（自动检测Python环境、安装依赖、打开浏览器）
2. 或手动启动：`python run_ui.py`
3. 浏览器访问：http://127.0.0.1:7860

## 系统要求

- Python 3.10+
- Docker（用于 Qdrant 向量数据库，可选）
- 依赖安装：`pip install -r requirements.txt`

## 项目结构

```
smart-content-creator/
├── src/
│   ├── main.py                    # 系统入口
│   ├── config.py                  # 全局配置
│   ├── workflow.py                # 工作流引擎
│   ├── scheduler.py               # 定时调度器
│   ├── prompt_engine.py           # 提示词引擎
│   ├── generator.py               # 内容生成器
│   ├── evaluator.py               # 质量评估器
│   ├── ui.py                      # Gradio Web界面
│   ├── publisher/                 # 微信发布模块
│   │   ├── wechat_publisher.py    # 发布器 + 排版适配引擎
│   │   └── __init__.py
│   ├── generator/                 # 生成子模块
│   │   ├── layout_engine.py       # 排版权式引擎
│   │   └── multimodal_processor.py # 多模态处理（配图建议）
│   ├── quality/                   # 质量子模块
│   │   ├── term_checker.py        # 术语校验
│   │   ├── logic_analyzer.py      # 逻辑分析
│   │   ├── readability_eval.py    # 可读性评估
│   │   └── suggestion_engine.py   # 建议生成
│   ├── rag/                       # RAG检索模块
│   │   ├── retriever.py           # 混合检索器
│   │   └── vector_db.py           # 向量数据库接口
│   ├── spiders/                   # 爬虫模块
│   │   ├── news_crawler.py        # 新闻爬虫（15个数据源）
│   │   └── spider_manager.py      # 爬虫管理器
│   └── data_storage.py, knowledge_base.py, data_cleaner.py
├── data/
│   └── jikang_knowledge.md        # 吉康环境知识库
├── tests/                         # 测试脚本
├── run_ui.py                      # UI启动脚本
├── init_knowledge.py              # 知识库初始化脚本
├── 启动.bat                        # 一键启动
├── docker-compose.yml             # Qdrant 容器配置
└── requirements.txt               # Python 依赖
```

## 功能模块

| 模块 | 功能 |
|------|------|
| 数据采集 | 15个行业/政策/产品数据源，自动爬取+分类 |
| 知识检索 | RAG语义检索 + 关键词混合搜索 |
| 内容生成 | DeepSeek API + RAG增强 + 场景感知业务规则 |
| 质量评估 | 五维评估（准确率/合规/可读/品牌/专业性）+ quality子模块 |
| 配图建议 | 自动生成封面图/插图方案，含AI生图提示词 |
| 微信发布 | 排版适配引擎 + Selenium操控 + 模拟模式 |
| 定时调度 | APScheduler + DAG Pipeline + SLA监控 |

## 技术栈

- **LLM**: DeepSeek (deepseek-v4-flash)
- **向量数据库**: Qdrant
- **Web框架**: Gradio 6
- **爬虫**: requests + BeautifulSoup + Selenium
- **调度**: APScheduler + SQLAlchemy

## 团队

- 曾睿(Noah) — 工作流引擎/调度器/UI/发布模块
- 刘凯睿 — 内容生成/提示词引擎/质量子模块/排版引擎
- 胡圳刚 — 数据存储/知识库/数据清洗
