"""Dashboard 路由：页面 + JSON API。

数据组装：把 store 历史 + 窗口模拟器状态聚合成卡片所需的视图模型。
估算值会明确标注，提醒用户用官方渠道核对。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.quota.tracker import WindowSimulator
from app.store import next_check_time

router = APIRouter()

# 模板目录：app/dashboard/templates
templates = Jinja2Templates(directory="app/dashboard/templates")

# 模拟器从 app.state 取（与 main 共享 store）
PROVIDERS = ["minimax", "zhipu"]
PROVIDER_LABELS = {"minimax": "MiniMax Token Plan", "zhipu": "智谱 GLM Coding Plan"}


def _sim(request: Request) -> WindowSimulator:
    return WindowSimulator(request.app.state.store)


def _fmt(dt: datetime | None) -> str:
    """ISO8601 带 +08:00，前端可直接 new Date()。None -> ''。"""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _card(request: Request, provider: str) -> dict:
    """组装单个厂商的卡片数据。"""
    store = request.app.state.store
    sim = _sim(request)
    st = sim.status(provider)
    latest = store.latest(provider)
    return {
        "name": provider,
        "label": PROVIDER_LABELS.get(provider, provider),
        "has_real_data": st.has_real_data,
        "remaining_pct": st.remaining_pct,  # 估算时为 None
        "interval_start": _fmt(st.interval_start),
        "interval_end": _fmt(st.interval_end),
        "seconds_until_reset": st.seconds_until_reset,
        "is_expired": st.is_expired,
        "note": st.note,
        "weekly_remaining_pct": latest.weekly_remaining_pct if latest else None,
        "weekly_end": _fmt(latest.weekly_end) if latest else "",
        "last_recorded": _fmt(latest.recorded_at) if latest else "",
        "last_probe_ok": latest.probe_ok if latest else None,
    }


def _history(request: Request, limit: int = 20) -> list[dict]:
    """汇总两家最近历史记录，按时间倒序。"""
    store = request.app.state.store
    rows: list[dict] = []
    for provider in PROVIDERS:
        for h in store.history(provider, limit):
            rows.append(
                {
                    "provider": provider,
                    "label": PROVIDER_LABELS.get(provider, provider),
                    "recorded_at": _fmt(h.recorded_at),
                    "interval_end": _fmt(h.interval_end),
                    "remaining_pct": h.interval_remaining_pct,
                    "weekly_remaining_pct": h.weekly_remaining_pct,
                    "probe_ok": h.probe_ok,
                    "was_reset": h.probe_was_reset,
                    "note": h.note,
                }
            )
    rows.sort(key=lambda r: r["recorded_at"], reverse=True)
    return rows[:limit]


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    cards = [_card(request, p) for p in PROVIDERS]
    history = _history(request, limit=20)
    checkpoints = _checkpoints_view(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "cards": cards,
            "history": history,
            "checkpoints": checkpoints,
            "now": _fmt(datetime.now(timezone.utc)),
        },
    )


@router.get("/api/status")
def api_status(request: Request) -> JSONResponse:
    """JSON API：供前端自动刷新。"""
    return JSONResponse(
        {
            "cards": [_card(request, p) for p in PROVIDERS],
            "history": _history(request, limit=20),
            "now": _fmt(datetime.now(timezone.utc)),
        }
    )


@router.post("/api/probe/{provider}")
def api_probe(provider: str, request: Request) -> JSONResponse:
    """手动触发一次探测（便于页面上点按钮立即刷新）。"""
    if provider not in PROVIDERS:
        return JSONResponse({"error": "未知 provider"}, status_code=400)
    scheduler = request.app.state.scheduler
    result = scheduler.probe_and_record(provider)
    # result.reset_time 是 datetime，需转字符串才能 JSON 序列化
    result["reset_time"] = _fmt(result.get("reset_time"))
    return JSONResponse(result)


# ---- 自定义监控时间点 ----
class CheckPointIn(BaseModel):
    label: str = "自定义点"
    time_hhmm: str  # "HH:MM" UTC
    probe_on_trigger: bool = True


def _checkpoints_view(request: Request) -> list[dict]:
    """组装自定义点列表（含下次触发时刻与倒计时）。"""
    store = request.app.state.store
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for cp, nxt in store.upcoming_checkpoints(limit=50):
        rows.append(
            {
                "id": cp.id,
                "label": cp.label,
                "time_hhmm": cp.time_hhmm,
                "probe_on_trigger": cp.probe_on_trigger,
                "next_at": _fmt(nxt),
                "seconds_until": (nxt - now).total_seconds(),
            }
        )
    return rows


@router.get("/api/checkpoints")
def api_list_checkpoints(request: Request) -> JSONResponse:
    return JSONResponse({"checkpoints": _checkpoints_view(request)})


@router.post("/api/checkpoints")
def api_add_checkpoint(body: CheckPointIn, request: Request) -> JSONResponse:
    """新增自定义点，成功后即时重排调度。"""
    store = request.app.state.store
    cp = store.add_checkpoint(
        body.label, body.time_hhmm, probe_on_trigger=body.probe_on_trigger
    )
    if cp is None:
        return JSONResponse(
            {"error": "时间格式非法（需 HH:MM）或该时间点已存在"}, status_code=400
        )
    # 即时重排调度任务
    request.app.state.scheduler.reschedule_checkpoints()
    return JSONResponse(
        {"ok": True, "id": cp.id, "checkpoints": _checkpoints_view(request)}
    )


@router.delete("/api/checkpoints/{cp_id}")
def api_delete_checkpoint(cp_id: int, request: Request) -> JSONResponse:
    store = request.app.state.store
    ok = store.delete_checkpoint(cp_id)
    if not ok:
        return JSONResponse({"error": "未找到该时间点"}, status_code=404)
    request.app.state.scheduler.reschedule_checkpoints()
    return JSONResponse({"ok": True, "checkpoints": _checkpoints_view(request)})
