# 贡献指南

感谢你有兴趣为 **auto-coding-reset** 贡献代码！🎉 本文档帮助你快速参与。

## 行为准则

参与本项目即代表你同意遵守 [贡献者公约](CODE_OF_CONDUCT.md)。请在所有交流中保持友善、尊重。

## 🐛 提交 Issue

- 提 Issue 前请先搜索是否已有人提过。
- **Bug 报告**请使用 [Bug 模板](.github/ISSUE_TEMPLATE/bug_report.yml)，并附上：
  - 复现步骤、预期与实际行为；
  - `config.yaml` 中的非敏感配置（**务必抹掉 API Key**）；
  - 日志（同样抹掉敏感信息）。
- **特性建议**请使用 [特性模板](.github/ISSUE_TEMPLATE/feature_request.yml)，说明使用场景与期望效果。

> ⚠️ **绝对不要在 Issue / PR / 日志里粘贴真实 API Key。** 详见 [安全说明](SECURITY.md)。

## 🔧 开发环境

```bash
git clone git@github.com:venusj/auto-coding-reset.git
cd auto-coding-reset
pip install -e ".[dev]"        # 安装依赖与开发工具
pre-commit install             # 可选：安装提交前检查（如已配置）
```

开发时本地运行：

```bash
uvicorn app.main:app --reload
```

运行测试与代码检查：

```bash
pytest                         # 运行测试
ruff check .                   # 代码风格检查
ruff format .                  # 自动格式化
```

## 📝 提交规范（Conventional Commits）

本项目采用 [约定式提交](https://www.conventionalcommits.org/zh-hans/v1.0.0/)。提交信息格式：

```
<type>: <简短描述>
```

常用 `type`：

| type | 含义 |
|---|---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（非新增功能、非修复） |
| `test` | 测试相关 |
| `chore` | 构建 / 工具 / 杂项 |
| `build` | 构建系统或依赖 |

示例：`feat(quota): 新增滚动窗口高峰预测`

## 🔄 提交 Pull Request

1. 从 `main` 切出一个特性分支：`git checkout -b feat/my-feature`；
2. 保持每个提交聚焦，遵循上述提交规范；
3. 如果改动涉及新功能或修复 Bug，请补充测试；
4. 确保本地 `pytest` 与 `ruff check` 通过；
5. 提交 PR 并按 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 填写说明；
6. 等待 Review，根据反馈迭代。

## 📦 版本与发布

- 版本号遵循语义化版本（SemVer），起步 `0.1.0`；
- 重要变更写入 [CHANGELOG.md](CHANGELOG.md) 的 `[Unreleased]` 区块；
- 维护者会在合适时机打 Tag 并发布 Release。

## 💬 讨论

如有疑问，可在 [Discussions](https://github.com/venusj/auto-coding-reset/discussions)（如已开启）或 Issue 中交流。

再次感谢你的贡献！
