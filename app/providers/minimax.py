"""MiniMax Token Plan 接入。

能力：
- query_quota(): 调用 coding_plan/remains 查询额度（实测可用，非官方文档接口）
- probe(): 发最小 chat completion 探测请求（可选用于卡点占窗口）

注意：remains 接口来自社区发现，非官方文档公开，字段结构以实测为准。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import ProviderConfig
from app.providers import ProbeResult, Provider, QuotaResult, WindowInfo
from app.store import QuotaSnapshot

# 社区发现的额度查询接口（非官方文档公开，实测可用）
REMAINS_URL = "https://www.minimaxi.com/v1/api/openplatform/coding_plan/remains"
CHAT_URL = "https://api.minimaxi.com/v1/chat/completions"
# general = 文本/编码模型窗口；video = 视频窗口。我们用 general。
GENERAL_MODEL = "general"


class MiniMaxProvider(Provider):
    name = "minimax"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def query_quota(self) -> QuotaResult:
        """查询额度，返回结构化结果。失败时 interval/weekly 为空 WindowInfo。"""
        empty = QuotaResult(
            provider=self.name,
            interval=WindowInfo(),
            weekly=WindowInfo(),
        )
        try:
            resp = self.client.get(REMAINS_URL, headers=self._headers())
        except Exception as e:  # noqa: BLE001
            empty.note = f"请求异常: {e!r}"
            return empty

        if resp.status_code != 200:
            empty.note = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return empty

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            empty.note = f"响应非 JSON: {resp.text[:200]}"
            return empty

        if data.get("base_resp", {}).get("status_code") != 0:
            empty.note = f"接口返回错误: {data.get('base_resp')}"
            empty.raw = data
            return empty

        # 从 model_remains 里取 general（编码/文本）窗口
        remains_list = data.get("model_remains") or []
        general = next(
            (m for m in remains_list if m.get("model_name") == GENERAL_MODEL), None
        )
        if general is None:
            empty.note = "未找到 general 模型窗口"
            empty.raw = data
            return empty

        empty.interval = self._parse_window(
            general,
            prefix="current_interval",
            start_key="start_time",
            end_key="end_time",
        )
        empty.weekly = self._parse_window(
            general,
            prefix="current_weekly",
            start_key="weekly_start_time",
            end_key="weekly_end_time",
        )
        empty.raw = data
        empty.note = "ok"
        return empty

    def probe(self, *, reset: bool = False) -> ProbeResult:
        """发最小 chat completion。reset=True 时为卡点占窗口触发。"""
        payload = {
            "model": self.cfg.probe_model,
            "messages": [{"role": "user", "content": "1"}],
            "max_tokens": 1,
            "stream": False,
        }
        try:
            resp = self.client.post(CHAT_URL, headers=self._headers(), json=payload)
        except Exception as e:  # noqa: BLE001
            return ProbeResult(self.name, ok=False, error=f"请求异常: {e!r}")
        ok = resp.status_code == 200
        return ProbeResult(
            self.name,
            ok=ok,
            http_status=resp.status_code,
            error=None if ok else resp.text[:200],
        )

    @staticmethod
    def _parse_window(
        d: dict, *, prefix: str, start_key: str, end_key: str
    ) -> WindowInfo:
        """从 remains 响应解析一个窗口。时间戳为毫秒。"""

        def _ts(key: str) -> datetime | None:
            v = d.get(key)
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc) if v else None

        return WindowInfo(
            start=_ts(start_key),
            end=_ts(end_key),
            remaining_pct=d.get(f"{prefix}_remaining_percent"),
            used=d.get(f"{prefix}_usage_count"),
            total=d.get(f"{prefix}_total_count"),
        )


def quota_result_to_snapshot(res: QuotaResult, *, probe: ProbeResult | None = None, was_reset: bool = False) -> QuotaSnapshot:
    """把 QuotaResult 转成可入库的快照。"""
    return QuotaSnapshot(
        provider=res.provider,
        interval_start=res.interval.start,
        interval_end=res.interval.end,
        interval_remaining_pct=res.interval.remaining_pct,
        interval_used=res.interval.used,
        interval_total=res.interval.total,
        weekly_start=res.weekly.start,
        weekly_end=res.weekly.end,
        weekly_remaining_pct=res.weekly.remaining_pct,
        weekly_used=res.weekly.used,
        weekly_total=res.weekly.total,
        probe_ok=probe.ok if probe else None,
        probe_http_status=probe.http_status if probe else None,
        probe_was_reset=was_reset,
        note=res.note,
    )
