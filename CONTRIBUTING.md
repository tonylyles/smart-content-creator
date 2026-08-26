# 贡献指南 Contributing

感谢你对 smart-content-creator 的关注！我们欢迎任何形式的贡献，包括但不限于：报告 bug、提出功能建议、改进文档、提交代码。

## 如何贡献

### 报告 Bug

1. 使用 [Issue 模板](.github/ISSUE_TEMPLATE/bug_report.md) 提交问题
2. 请提供：运行环境（Python 版本、操作系统）、复现步骤、期望结果与实际结果

### 提交代码

1. Fork 本仓库
2. 创建你的功能分支：`git checkout -b feat/your-feature`
3. 提交修改：`git commit -m 'feat: add your feature'`
4. 推送到分支：`git push origin feat/your-feature`
5. 提交 Pull Request

### Commit 规范

我们采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具链相关

## 开发环境

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境变量模板并填写
cp .env.example .env

# 启动 UI
python run_ui.py
```

## 代码风格

- 遵循 PEP 8
- 保持模块之间的接口签名兼容
- 新增功能请补充对应的测试（`tests/` 目录）

## 许可证

通过提交代码，你同意在 MIT 许可证下发布你的贡献。
