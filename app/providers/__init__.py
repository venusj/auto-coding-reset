"""Provider 抽象基类与公共数据结构。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import ProviderConfig


@dataclass
class WindowInfo:
    """一个窗口（5h 或周）的额度信息。可能部分缺失（智谱查不到）。"""

    start: datetime | None = None
    end: datetime | None = None  # 重置时间
    remaining_pct: float | None = None
    used: int | None = None
    total: int | None = None


@dataclass
class QuotaResult:
    """一次额度查询的结果。"""

    provider: str
    interval: WindowInfo  # 5h 窗口
    weekly: WindowInfo  # 周窗口
    raw: dict | None = None  # 原始响应，便于调试
    note: str | None = None


@dataclass
class ProbeResult:
    """一次探测请求的结果。"""

    provider: str
    ok: bool
    http_status: int | None = None
    error: str | None = None


class Provider(ABC):
    """厂商接入抽象。"""

    name: str

    def __init__(self, cfg: ProviderConfig, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        # 外部传入 client 便于测试注入 mock；否则惰性创建
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def api_key(self) -> str | None:
        return self.cfg.api_key

    @abstractmethod
    def query_quota(self) -> QuotaResult:
        """查询额度。无法查询的 provider 返回空 WindowInfo。"""
        ...

    @abstractmethod
    def probe(self, *, reset: bool = False) -> ProbeResult:
        """发一次最小探测请求。reset=True 表示这是卡点重置触发。"""
        ...
