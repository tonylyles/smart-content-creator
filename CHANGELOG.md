# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 安全
- 从版本历史中移除误提交的敏感凭据（`.env`、数据库文件、编译产物）

### 新增
- 开源基础设施：`LICENSE`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`.github/`（Issue/PR 模板与 CI）、`.gitattributes`、`.editorconfig`

## [1.0.0] - 2026-05

### 新增
- 五阶段内容生产流水线：数据采集 → 知识检索 → 内容生成 → 质量评估 → 微信发布
- 15 个行业/政策/产品数据源的新闻爬虫
- RAG 语义检索 + 关键词混合搜索
- DeepSeek 驱动的场景感知内容生成
- 五维质量评估（准确率 / 合规 / 可读 / 品牌 / 专业）
- 微信公众号排版适配引擎与 Selenium 自动化发布
- APScheduler 定时调度 + DAG Pipeline + 闭环重试
- Gradio Web 界面
