"""SQLite 存储层：额度快照历史 + 触发/请求记录。

设计：每次额度查询与每次探测请求都落一条记录，完整保留历史；
按配置自动清理超过 snapshot_retention_days 天的快照。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, create_engine, select

UTC = timezone.utc


def _utcnow_naive() -> datetime:
    """当前 UTC，naive（SQLite 不存 tz，统一存 UTC naive）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    """aware -> UTC naive；naive 视作 UTC 保持不变；None -> None。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


def _as_utc(dt: datetime | None) -> datetime | None:
    """读出时把 naive 当作 UTC，补回 tzinfo。"""
    return dt.replace(tzinfo=UTC) if dt else None


class QuotaSnapshot(SQLModel, table=True):
    """额度快照：一次查询/探测得到的额度状态。"""

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)  # minimax / zhipu
    recorded_at: datetime = Field(default_factory=_utcnow_naive, index=True)

    # 当前 5h 窗口
    interval_start: datetime | None = Field(default=None)  # 窗口开始
    interval_end: datetime | None = Field(default=None, index=True)  # 窗口结束（重置时间）
    interval_remaining_pct: float | None = Field(default=None)  # 剩余百分比
    interval_used: int | None = Field(default=None)
    interval_total: int | None = Field(default=None)

    # 周窗口
    weekly_start: datetime | None = Field(default=None)
    weekly_end: datetime | None = Field(default=None)
    weekly_remaining_pct: float | None = Field(default=None)
    weekly_used: int | None = Field(default=None)
    weekly_total: int | None = Field(default=None)

    # 探测请求本身的结果（HTTP 状态、是否触发重置请求）
    probe_ok: bool | None = Field(default=None)
    probe_http_status: int | None = Field(default=None)
    probe_was_reset: bool = Field(default=False)  # 是否为「卡点重置」触发的探测
    note: str | None = Field(default=None)


class Store:
    """存储门面。"""

    def __init__(self, db_path: str = "data/auto_coding.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self.engine)

    def add_snapshot(self, snap: QuotaSnapshot) -> None:
        # 统一转 UTC naive 再入库（SQLite 不存时区）
        snap.recorded_at = _to_utc_naive(snap.recorded_at) or _utcnow_naive()
        snap.interval_start = _to_utc_naive(snap.interval_start)
        snap.interval_end = _to_utc_naive(snap.interval_end)
        snap.weekly_start = _to_utc_naive(snap.weekly_start)
        snap.weekly_end = _to_utc_naive(snap.weekly_end)
        with Session(self.engine) as s:
            s.add(snap)
            s.commit()

    def latest(self, provider: str) -> QuotaSnapshot | None:
        with Session(self.engine) as s:
            stmt = (
                select(QuotaSnapshot)
                .where(QuotaSnapshot.provider == provider)
                .order_by(QuotaSnapshot.recorded_at.desc())  # type: ignore[union-attr]
            )
            snap = s.exec(stmt).first()
            return self._with_utc(snap) if snap else None

    def history(
        self, provider: str, limit: int = 100
    ) -> list[QuotaSnapshot]:
        with Session(self.engine) as s:
            stmt = (
                select(QuotaSnapshot)
                .where(QuotaSnapshot.provider == provider)
                .order_by(QuotaSnapshot.recorded_at.desc())  # type: ignore[union-attr]
                .limit(limit)
            )
            return [self._with_utc(s) for s in s.exec(stmt).all()]

    def cleanup(self, retention_days: int = 7) -> int:
        """删除早于 retention_days 天的快照，返回删除条数。"""
        cutoff = _utcnow_naive() - timedelta(days=retention_days)
        with Session(self.engine) as s:
            stmt = select(QuotaSnapshot).where(QuotaSnapshot.recorded_at < cutoff)
            old = list(s.exec(stmt).all())
            for o in old:
                s.delete(o)
            s.commit()
            return len(old)

    def next_reset_time(self, provider: str) -> datetime | None:
        """取最近一次快照里记录的窗口结束时间（= 下一次重置时间，aware UTC）。"""
        snap = self.latest(provider)
        return snap.interval_end if snap else None

    # ---- 自定义监控时间点 CRUD ----
    def list_checkpoints(self) -> list[CheckPoint]:
        with Session(self.engine) as s:
            return list(s.exec(select(CheckPoint)).all())

    def add_checkpoint(self, label: str, time_hhmm: str, *, probe_on_trigger: bool = True) -> CheckPoint | None:
        """新增自定义点。HH:MM 非法或重复返回 None。"""
        if _parse_hhmm(time_hhmm) is None:
            return None
        with Session(self.engine) as s:
            # 去重：同一时间点只存一条
            exists = s.exec(
                select(CheckPoint).where(CheckPoint.time_hhmm == time_hhmm)
            ).first()
            if exists:
                return None
            cp = CheckPoint(
                label=label or "自定义点",
                time_hhmm=time_hhmm,
                probe_on_trigger=probe_on_trigger,
            )
            s.add(cp)
            s.commit()
            s.refresh(cp)
            return cp

    def delete_checkpoint(self, cp_id: int) -> bool:
        with Session(self.engine) as s:
            cp = s.get(CheckPoint, cp_id)
            if cp is None:
                return False
            s.delete(cp)
            s.commit()
            return True

    def enabled_checkpoints(self) -> list[CheckPoint]:
        with Session(self.engine) as s:
            stmt = select(CheckPoint).where(CheckPoint.enabled == True)  # noqa: E712
            return list(s.exec(stmt).all())

    def upcoming_checkpoints(self, limit: int = 10) -> list[tuple[CheckPoint, datetime]]:
        """返回 (checkpoint, 下次触发时刻) 按时刻升序，最多 limit 条。"""
        now = datetime.now(UTC)
        items: list[tuple[CheckPoint, datetime]] = []
        for cp in self.enabled_checkpoints():
            nxt = next_check_time(cp.time_hhmm, now)
            if nxt:
                items.append((cp, nxt))
        items.sort(key=lambda x: x[1])
        return items[:limit]

    @staticmethod
    def _with_utc(snap: QuotaSnapshot) -> QuotaSnapshot:
        """读出后把 naive 当作 UTC 补回 tzinfo。"""
        snap.recorded_at = _as_utc(snap.recorded_at) or _utcnow_naive()
        snap.interval_start = _as_utc(snap.interval_start)
        snap.interval_end = _as_utc(snap.interval_end)
        snap.weekly_start = _as_utc(snap.weekly_start)
        snap.weekly_end = _as_utc(snap.weekly_end)
        return snap


class CheckPoint(SQLModel, table=True):
    """用户自定义的监控时间点（每天重复的 HH:MM，存 UTC）。

    用途：到点自动触发「查询+探测」全家厂商，并在 Dashboard 高亮倒计时。
    注意：这不改变厂商真实窗口（厂商是固定整点翻转），只是用户自定义的
    「我想在这个时间点检查/触发」参考点。
    """

    id: int | None = Field(default=None, primary_key=True)
    label: str = "自定义点"  # 显示名，如「编码前」
    time_hhmm: str = Field(index=True)  # "HH:MM" 格式，24h，UTC
    enabled: bool = Field(default=True)
    # 到点触发时是否对每家发一次最小探测请求（消耗极小）
    probe_on_trigger: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow_naive)


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    """解析 'HH:MM' -> (hour, minute)，非法返回 None。"""
    try:
        h, m = s.split(":")
        h_i, m_i = int(h), int(m)
        if 0 <= h_i < 24 and 0 <= m_i < 60:
            return h_i, m_i
    except (ValueError, AttributeError):
        pass
    return None


def next_check_time(time_hhmm: str, now: datetime | None = None) -> datetime | None:
    """给定 HH:MM（UTC），算出从 now 起下一个触发时刻（aware UTC）。

    若今天该时刻未到，返回今天；否则返回明天。
    """
    hm = _parse_hhmm(time_hhmm)
    if hm is None:
        return None
    now = now or datetime.now(UTC)
    today = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if today <= now:
        today += timedelta(days=1)
    return today
