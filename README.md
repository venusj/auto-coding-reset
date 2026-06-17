<div align="center">

# auto-coding-reset

**监控与调度 MiniMax / 智谱 编程套餐的 5 小时滚动窗口额度**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![status](https://img.shields.io/badge/status-alpha-orange.svg)](#项目状态)

</div>

> ⚠️ **早期项目（Alpha）**：当前处于 MVP 阶段，功能仍在迭代。欢迎使用并提 [Issue](https://github.com/venusj/auto-coding-reset/issues)。

## 这是什么

很多大模型厂商（MiniMax、智谱等）推出了**编程套餐 / Token Plan**，通常包含「5 小时滚动窗口」和「周限额」两重额度。这个项目帮你：

- ⏰ 按你设定的时间点**定时探测**两家套餐的连通性与可用性；
- 📊 在 Web 面板上**实时估算**每家当前的 5 小时可用额度、滚动恢复时间线、周限额消耗；
- 🔔 额度低于阈值或探测失败时**告警**；
- 🐳 一键 Docker 部署到 VPS，7×24 可靠运行。

## ⚠️ 必读：滚动窗口与合规说明

在开始前，请务必了解以下事实（详见 [FAQ](#faq)）：

1. **「5 小时窗口」是滚动恢复，不是固定翻转**。每消耗一笔额度，该笔在 **5 小时后单独回滚**。不存在「发一次请求重置窗口起点」的操作——主动发请求只会消耗额度。本项目的「定时触发」用途是**健康探测、滚动行为实测、额度估算校准**，而非重置窗口。

2. **两家均不提供公开的额度查询接口**。Dashboard 上的额度数字是**基于消耗记录的滚动估算值**，并非精确值。建议用官方渠道核对：智谱用 Claude Code 内的 `/glm-plan-usage` 插件，MiniMax 看 [Web 控制台](https://platform.minimaxi.com/subscribe/token-plan)。

3. **智谱 GLM Coding Plan 有「仅限指定工具使用」条款**。非官方工具调用可能不抵扣套餐额度或被降级。本项目对探测请求会尝试伪装为官方工具请求头，但**不保证抵扣套餐额度，使用风险自负**。

## ✨ 功能

- [x] 定时探测 MiniMax 与智谱套餐连通性（cron 可配）
- [x] 滚动窗口模拟器（5h 滑动求和 + 高峰预测）
- [x] Web Dashboard：额度估算、恢复时间线、触发历史
- [x] 阈值告警（webhook：Server酱 / 钉钉 / 飞书 / 自定义）
- [x] Docker 一键部署
- [ ] v2：本地路由代理，高峰期同时消耗两家额度

## 🚀 快速开始

### 1. 准备配置

```bash
cp .env.example .env          # 填入 ZHIPU_API_KEY / MINIMAX_API_KEY
cp config.example.yaml config.yaml  # 按你的套餐档位改 quota_5h / quota_weekly
```

### 2. Docker 部署（推荐 VPS）

```bash
docker compose up -d
# 打开 http://<你的服务器IP>:8000
```

### 3. 本地开发

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## ⚙️ 配置说明

见 [`config.example.yaml`](config.example.yaml) 内注释。关键项：

| 配置 | 说明 |
|---|---|
| `providers.*.base_url` | 智谱必须用 `…/api/coding/paas/v4`（带 `/coding/`） |
| `providers.*.probe_model` | 探测模型：智谱 `glm-4.5-air`，MiniMax `MiniMax-M2.5` |
| `providers.*.quota_5h` | 你套餐档位的 5h 额度（用于估算，按实际填） |
| `trigger.*_cron` | 探测频率 cron 表达式 |

## 🏗️ 技术栈

Python 3.11+ · FastAPI · APScheduler · httpx · SQLModel · Jinja2 · Docker

## 📄 文档

- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [安全与漏洞上报](SECURITY.md)

## ❓ FAQ

<details>
<summary><b>「发请求重置 5 小时窗口」为什么不行？</b></summary>

两家套餐的 5 小时窗口是**滚动恢复**：每笔消耗在 5 小时后逐笔回滚，没有一个全局起点可以被「重置」。主动发请求只会再消耗一笔额度。所以「定时触发」在本项目里是做探测与估算，而非挪动窗口。
</details>

<details>
<summary><b>Dashbaord 上的额度数字准吗？</b></summary>

是**估算值**。两家都没有公开的额度查询接口，数字来自本地对消耗记录的滚动求和。建议定期用官方渠道核对。
</details>

<details>
<summary><b>会不会违反厂商条款？</b></summary>

智谱 Coding Plan 明确「仅限官方指定工具使用」，用脚本裸调 API 可能不抵扣套餐额度。MiniMax 相对开放但未查到明确豁免。请在阅读厂商服务条款后自行评估，本项目不承担责任。
</details>

## 🤝 贡献

欢迎贡献！请先阅读 [贡献指南](CONTRIBUTING.md)。提 Issue / PR 前请先搜索是否已存在。

## 📜 许可证

[MIT](LICENSE) © 2026 启明星

## 项目状态

Alpha —— MVP 阶段，欢迎反馈。
