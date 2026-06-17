"""窗口模拟器：基于历史快照推算当前额度状态与下次重置时间。

两种模式：
- 固定窗口（MiniMax 实测如此）：窗口起止来自 remains 接口的真实数据，
  重置时间 = interval_end。跨过 end 后查询会返回新窗口。
- 回退估算（智谱查不到额度）：用最近一次探测时间 + 配置的 quota_5h，
  按「整点对齐的 5 小时固定窗口」假设推算（UTC 整点 0/5/10/15/20）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.store import QuotaSnapshot, Store

UTC = timezone.utc
WINDOW_HOURS = 5


@dataclass
class WindowStatus:
    """当前窗口状态。"""

    provider: str
    has_real_data: bool  # 是否有真实查询数据（MiniMax=True，智谱估算=False）
    interval_start: datetime | None
    interval_end: datetime | None  # 下次重置时间
    remaining_pct: float | None
    seconds_until_reset: float | None
    is_expired: bool  # 当前快照的窗口是否已过（需要重新查询）
    note: str = ""


class WindowSimulator:
    def __init__(self, store: Store, quota_5h: int = 0) -> None:
        self.store = store
        self.quota_5h = quota_5h

    def status(self, provider: str, now: datetime | None = None) -> WindowStatus:
        now = now or datetime.now(UTC)
        snap = self.store.latest(provider)
        if snap is None:
            return WindowStatus(
                provider=provider,
                has_real_data=False,
                interval_start=None,
                interval_end=None,
                remaining_pct=None,
                seconds_until_reset=None,
                is_expired=True,
                note="无历史快照",
            )

        # 有 interval_end 的（MiniMax）：以真实数据为准
        if snap.interval_end is not None:
            return self._status_from_snapshot(snap, now, real=True)

        # 无 interval_end（智谱）：回退估算
        return self._estimate_status(provider, snap, now)

    def _status_from_snapshot(
        self, snap: QuotaSnapshot, now: datetime, *, real: bool
    ) -> WindowStatus:
        end = snap.interval_end or now
        seconds_until = (end - now).total_seconds()
        is_expired = seconds_until <= 0
        return WindowStatus(
            provider=snap.provider,
            has_real_data=real,
            interval_start=snap.interval_start,
            interval_end=end,
            remaining_pct=snap.interval_remaining_pct,
            seconds_until_reset=seconds_until if not is_expired else 0,
            is_expired=is_expired,
            note="真实查询数据" if real else "估算",
        )

    def _estimate_status(
        self, provider: str, snap: QuotaSnapshot, now: datetime
    ) -> WindowStatus:
        """智谱回退：按整点对齐的 5h 固定窗口估算（UTC 0/5/10/15/20 起算）。

        以「现在」所在窗口为准（而非探测时刻），保证跨窗口后能正确判过期。
        若探测距今已超过一个窗口周期，估算不可信，标记 expired 促使重新探测。
        """
        recorded = snap.recorded_at or now
        stale = (now - recorded).total_seconds() > WINDOW_HOURS * 3600
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_of_day = (now - today_midnight).total_seconds() / 3600
        window_start_hour = int(hour_of_day // WINDOW_HOURS) * WINDOW_HOURS
        start = today_midnight + timedelta(hours=window_start_hour)
        end = start + timedelta(hours=WINDOW_HOURS)
        seconds_until = (end - now).total_seconds()
        is_expired = stale  # 估算窗口本身跟随 now 不会过期，仅当探测老旧才判过期
        return WindowStatus(
            provider=provider,
            has_real_data=False,
            interval_start=start,
            interval_end=end,
            remaining_pct=None,  # 估算模式下无法知道剩余
            seconds_until_reset=seconds_until if not is_expired else 0,
            is_expired=is_expired,
            note="智谱估算（探测老旧，估算不可信）" if stale else "智谱估算（整点对齐 5h 窗口假设）",
        )
