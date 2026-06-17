"""调度编排：定时探测 + 查询 + end_time 卡点重置。

核心流程（每个 provider）：
1. 定时探测任务：按 probe_cron 跑，查询额度（MiniMax）+ 探测连通（两家）。
2. 卡点重置任务：取最近快照的 interval_end，在其 +delay 后触发：
   - 先查询/探测，判断窗口是否已翻转；
   - 若 reset_send_request=True，发一次最小请求「占住」新窗口起点。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.config import Settings
from app.providers.minimax import MiniMaxProvider, quota_result_to_snapshot
from app.providers.zhipu import ZhipuProvider
from app.quota.tracker import WindowSimulator
from app.store import Store

UTC = timezone.utc


class Scheduler:
    def __init__(self, settings: Settings, store: Store | None = None) -> None:
        self.settings = settings
        self.store = store or Store(settings.storage.db_path)
        self._providers = self._build_providers()
        self._sched = BackgroundScheduler(timezone=UTC)
        self.sim = WindowSimulator(self.store)

    def _build_providers(self) -> dict:
        provs: dict = {}
        s = self.settings
        if s.provider("minimax"):
            provs["minimax"] = MiniMaxProvider(s.providers["minimax"])
        if s.provider("zhipu"):
            provs["zhipu"] = ZhipuProvider(s.providers["zhipu"])
        return provs

    # ---- 单次动作 ----
    def probe_and_record(self, provider: str, *, reset: bool = False) -> dict:
        """对一家做「查询 + 探测」并落库。reset=True 表示卡点重置触发。"""
        p = self._providers.get(provider)
        if p is None:
            return {"provider": provider, "ok": False, "error": "provider 未启用"}

        qr = p.query_quota()
        pr = p.probe(reset=reset)
        snap = quota_result_to_snapshot(qr, probe=pr, was_reset=reset)
        self.store.add_snapshot(snap)
        return {
            "provider": provider,
            "ok": pr.ok,
            "http": pr.http_status,
            "remaining_pct": qr.interval.remaining_pct,
            "reset_time": qr.interval.end,
            "was_reset": reset,
            "note": qr.note,
        }

    def schedule_reset_job(self, provider: str) -> str | None:
        """根据最近快照的 interval_end 安排一次卡点重置任务，返回 job_id。"""
        st = self.sim.status(provider)
        if st.interval_end is None or st.is_expired:
            # 没有窗口结束时间或已过期：不安排，等下一次常规探测刷新
            return None
        delay = self.settings.trigger.reset_probe_delay_seconds
        run_at = st.interval_end + timedelta(seconds=delay)
        if run_at <= datetime.now(UTC):
            return None  # 已过点，跳过
        job_id = f"reset_{provider}_{int(run_at.timestamp())}"
        # 避免重复安排同一时刻
        if self._sched.get_job(job_id):
            return job_id
        self._sched.add_job(
            self._reset_routine,
            DateTrigger(run_date=run_at, timezone=UTC),
            args=[provider],
            id=job_id,
            replace_existing=True,
        )
        return job_id

    def _reset_routine(self, provider: str) -> None:
        """卡点重置实际执行：探测看是否翻转，按配置决定是否发请求占窗口。"""
        # 先探测/查询一次
        send = self.settings.trigger.reset_send_request
        result = self.probe_and_record(provider, reset=send)
        # 探测后再为新窗口安排下一次卡点
        self.schedule_reset_job(provider)
        return result

    # ---- 调度生命周期 ----
    def start(self) -> None:
        s = self.settings
        # 常规探测任务
        for name in self._providers:
            self._sched.add_job(
                self.probe_and_record,
                CronTrigger.from_crontab(_to_5field(s.trigger.probe_cron), timezone=UTC),
                args=[name],
                id=f"probe_{name}",
                replace_existing=True,
            )
            # 启动时立刻跑一次，建立首份快照并安排卡点
            self._sched.add_job(
                self._initial_probe,
                DateTrigger(run_date=datetime.now(UTC) + timedelta(seconds=5), timezone=UTC),
                args=[name],
                id=f"initial_{name}",
                replace_existing=True,
            )
        self._sched.start()

    def _initial_probe(self, provider: str) -> None:
        self.probe_and_record(provider)
        self.schedule_reset_job(provider)

    def shutdown(self) -> None:
        for p in self._providers.values():
            p.close()
        if self._sched.running:
            self._sched.shutdown(wait=False)


def _to_5field(cron: str) -> str:
    """把 6 段（带秒）cron 转成标准 5 段（分 时 日 月 周）。"""
    parts = cron.split()
    if len(parts) == 6:
        return " ".join(parts[1:])  # 丢弃秒字段
    return cron
