"""FastAPI 应用入口。

启动时：
1. 加载配置（yaml + 环境变量）
2. 初始化存储
3. 启动调度器（定时探测 + 卡点重置）
4. 挂载 Dashboard 路由

运行：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_settings
from app.dashboard.routes import router as dashboard_router
from app.scheduler import Scheduler
from app.store import Store

# 全局单例（lifespan 内初始化）
settings = load_settings()
store = Store(settings.storage.db_path)
scheduler = Scheduler(settings, store=store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    scheduler.start()
    yield
    # 关闭
    scheduler.shutdown()


app = FastAPI(
    title="auto-coding-reset",
    description="监控与调度 MiniMax / 智谱 编程套餐的 5 小时滚动窗口额度",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.settings = settings
app.state.store = store
app.state.scheduler = scheduler

app.include_router(dashboard_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
