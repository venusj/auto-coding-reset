# 安全说明

## API Key 与机密信息

本项目会处理你的 **MiniMax / 智谱 API Key**，这些凭证一旦泄露可能被他人盗用并消耗你的套餐额度或造成经济损失。请务必：

- ✅ 将 Key 配置在 `.env` 文件或环境变量中。`.env` 已被 `.gitignore` 忽略。
- ✅ `config.yaml` 中**只填档位数值**（`quota_5h` / `quota_weekly` 等），**绝不填 Key**——Key 通过 `api_key_env` 指向环境变量。
- ✅ 提交前自检：确认 `git status` 不会把 `.env` / `config.yaml` 纳入提交。
- ❌ **绝不**在 Issue、PR、截图、日志、聊天中粘贴真实 Key。
- ❌ **绝不**把 Key 写进任何提交到仓库的文件。

### 如果你不小心泄露了 Key

1. 立即到对应厂商控制台**吊销 / 重置**该 Key：
   - 智谱：[open.bigmodel.cn](https://open.bigmodel.cn) 控制台 → API Keys
   - MiniMax：[platform.minimaxi.com](https://platform.minimaxi.com) 控制台 → API Keys
2. 生成新 Key，更新你的 `.env`；
3. 如果 Key 已被推送到公开仓库，请同时联系厂商说明情况。

## 漏洞与安全漏洞上报

如果你发现本项目存在安全漏洞（如导致 Key 泄露、未授权访问等），**请不要公开提 Issue**。

请通过以下方式私下联系维护者：

- 在 GitHub 上创建一个 **私密** Security Advisory：仓库 → Security → Report a vulnerability
- 或发送邮件至项目维护者（见仓库 Owner 主页）

请在报告中说明：
- 问题描述与影响范围；
- 复现步骤；
- 建议的修复方式（可选）。

维护者会在收到报告后尽快回复并协调修复。感谢你帮助提升项目安全！
