"""Dashboard 路由：页面 + JSON API。

数据组装：把 store 历史 + 窗口模拟器状态聚合成卡片所需的视图模型。
估算值会明确标注，提醒用户用官方渠道核对。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.quota.tracker import WindowSimulator

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
    return templates.TemplateResponse(
        request,
        "index.html",
        {"cards": cards, "history": history, "now": _fmt(datetime.now(timezone.utc))},
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
