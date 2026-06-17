"""窗口模拟器单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.quota.tracker import WindowSimulator
from app.store import QuotaSnapshot, Store

UTC = timezone.utc


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(str(tmp_path / "test.db"))


def _add(store: Store, provider: str, *, end=None, remaining=None, recorded=None) -> None:
    store.add_snapshot(
        QuotaSnapshot(
            provider=provider,
            recorded_at=recorded or datetime.now(UTC),
            interval_end=end,
            interval_remaining_pct=remaining,
        )
    )


def test_no_snapshot_returns_expired(store: Store):
    sim = WindowSimulator(store)
    st = sim.status("minimax")
    assert st.has_real_data is False
    assert st.is_expired is True
    assert st.interval_end is None
    assert "无历史快照" in st.note


def test_fixed_window_minimax_real_data(store: Store):
    """MiniMax：真实 end_time，距重置 1 小时。"""
    now = datetime.now(UTC)
    end = now + timedelta(hours=1)
    _add(store, "minimax", end=end, remaining=80, recorded=now)

    sim = WindowSimulator(store)
    st = sim.status("minimax", now=now)
    assert st.has_real_data is True
    assert st.is_expired is False
    assert st.remaining_pct == 80
    assert abs(st.seconds_until_reset - 3600) < 5
    assert st.interval_end == end


def test_fixed_window_expired_when_past_end(store: Store):
    """窗口 end 已过 → is_expired=True，seconds_until_reset=0。"""
    now = datetime.now(UTC)
    end = now - timedelta(minutes=10)  # 已过期
    _add(store, "minimax", end=end, remaining=20, recorded=now - timedelta(hours=1))

    sim = WindowSimulator(store)
    st = sim.status("minimax", now=now)
    assert st.is_expired is True
    assert st.seconds_until_reset == 0


def test_zhipu_estimate_no_end(store: Store):
    """智谱无 end_time → 回退估算，落在某个 5h 整点窗口内。"""
    # 探测发生在 02:30 UTC，应落入 00:00-05:00 窗口
    recorded = datetime(2026, 6, 18, 2, 30, tzinfo=UTC)
    _add(store, "zhipu", end=None, recorded=recorded)

    sim = WindowSimulator(store)
    # 估算「现在」= 03:00，仍在该窗口内
    now = datetime(2026, 6, 18, 3, 0, tzinfo=UTC)
    st = sim.status("zhipu", now=now)
    assert st.has_real_data is False
    assert st.is_expired is False
    assert st.interval_start == datetime(2026, 6, 18, 0, 0, tzinfo=UTC)
    assert st.interval_end == datetime(2026, 6, 18, 5, 0, tzinfo=UTC)
    assert st.remaining_pct is None  # 估算无法知道剩余
    assert abs(st.seconds_until_reset - 2 * 3600) < 5


def test_zhipu_estimate_rolls_with_now(store: Store):
    """智谱估算：窗口随 now 滚动，now 跨过 05:00 后落入 05-10 新窗口。"""
    recorded = datetime(2026, 6, 18, 2, 30, tzinfo=UTC)
    _add(store, "zhipu", end=None, recorded=recorded)

    sim = WindowSimulator(store)
    now = datetime(2026, 6, 18, 5, 30, tzinfo=UTC)  # 过了 05:00，进入新窗口
    st = sim.status("zhipu", now=now)
    # 估算模式下窗口跟随 now，始终落在某个当前窗口内，不会「过期」
    assert st.is_expired is False
    assert st.interval_start == datetime(2026, 6, 18, 5, 0, tzinfo=UTC)
    assert st.interval_end == datetime(2026, 6, 18, 10, 0, tzinfo=UTC)
    assert abs(st.seconds_until_reset - 4.5 * 3600) < 5


def test_zhipu_estimate_marks_stale_when_probe_old(store: Store):
    """智谱估算：探测时间超过一个窗口周期 → 标记 is_expired 促使重新探测。"""
    old_recorded = datetime(2026, 6, 18, 2, 30, tzinfo=UTC)
    _add(store, "zhipu", end=None, recorded=old_recorded)

    sim = WindowSimulator(store)
    # 探测发生在 6 小时前，已超过 5h 窗口，估算不可信
    now = old_recorded + timedelta(hours=6)
    st = sim.status("zhipu", now=now)
    assert st.is_expired is True
    assert "估算不可信" in st.note or st.is_expired
