"""配置加载与校验。

配置来源优先级：环境变量 > config.yaml > 内置默认。
API Key 只从环境变量读取，绝不写入 yaml（yaml 可入库，Key 不可）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

DEFAULT_CONFIG_PATHS = ("config.yaml", "config.example.yaml")


class ProviderConfig(BaseModel):
    """单个厂商接入配置。"""

    enabled: bool = True
    base_url: str
    # 指向哪个环境变量名取 Key（不在配置里存明文 Key）
    api_key_env: str
    probe_model: str
    # 套餐档位：用于本地估算（MiniMax 可被实测覆盖，智谱无接口则纯靠它）
    quota_5h: int = 0
    quota_weekly: int = 0
    peak_hours: list[int] = Field(default_factory=list)

    @property
    def api_key(self) -> str | None:
        """从环境变量读取真实 Key。"""
        return os.environ.get(self.api_key_env)


class TriggerConfig(BaseModel):
    """定时触发配置。"""

    probe_cron: str = "0 0 */3 * * *"
    peak_warmup_cron: str | None = "0 0 13 * * *"
    max_tokens: int = 1
    # 卡点重置：到 end_time 后多久做第一次探测（秒）
    reset_probe_delay_seconds: int = 60
    # 卡点重置时是否主动发一次最小请求「占住」新窗口起点
    reset_send_request: bool = False


class NotifyConfig(BaseModel):
    enabled: bool = False
    webhook_url_env: str = "NOTIFY_WEBHOOK_URL"
    threshold_5h_pct: int = 20
    threshold_weekly_pct: int = 80

    @property
    def webhook_url(self) -> str | None:
        return os.environ.get(self.webhook_url_env)


class StorageConfig(BaseModel):
    db_path: str = "data/auto_coding.db"
    # 额度快照自动清理：保留最近 N 天
    snapshot_retention_days: int = 7


class AppConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @field_validator("providers")
    @classmethod
    def _known_providers(cls, v: dict[str, ProviderConfig]) -> dict[str, ProviderConfig]:
        known = {"zhipu", "minimax"}
        unknown = set(v) - known
        if unknown:
            raise ValueError(f"未知 provider: {unknown}，仅支持 {known}")
        return v

    def provider(self, name: str) -> ProviderConfig | None:
        p = self.providers.get(name)
        return p if p and p.enabled and p.api_key else None


def load_settings(path: str | Path | None = None) -> Settings:
    """从 yaml 加载配置。找不到文件则用全默认值。"""
    p = Path(path) if path else _find_config()
    if p and p.exists():
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Settings.model_validate(data)
    return Settings()


def _find_config() -> Path | None:
    for name in DEFAULT_CONFIG_PATHS:
        p = Path(name)
        if p.exists():
            return p
    return None
