"""FastAPI 進入點。"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .api import auth_routes, records, residents, system, visitors
from .config import get_config
from .db import init_engine
from .migrate import upgrade_db
from .services.events import bus
from .services.settings import settings_store

log = logging.getLogger("app")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(start_background: bool | None = None) -> FastAPI:
    cfg = get_config()
    cfg.ensure_dirs()
    run_bg = cfg.enable_workers if start_background is None else start_background

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        stop = asyncio.Event()
        tasks = []
        mgr = None
        if run_bg:
            from .services.lanes import get_lane_manager
            from .services.scheduler import run_scheduler

            mgr = get_lane_manager()
            await asyncio.to_thread(mgr.start_all)
            tasks.append(asyncio.create_task(run_scheduler(stop)))
            # 背景預先載入辨識模型（首次會下載）
            from .vision.recognizer import get_recognizer

            rec = get_recognizer()
            if hasattr(rec, "warmup"):
                asyncio.get_running_loop().run_in_executor(None, rec.warmup)
        yield
        stop.set()
        for t in tasks:
            t.cancel()
        if mgr is not None:
            await asyncio.to_thread(mgr.stop_all)
            from .services import lanes

            lanes.lane_manager = None

    init_engine()
    upgrade_db()
    settings_store.invalidate()

    app = FastAPI(title="社區出入管理系統", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=cfg.get_secret_key(),
        session_cookie="gate_session",
        max_age=cfg.session_max_age_sec,
        same_site="strict",
        https_only=False,
    )
    for r in (auth_routes.router, residents.router, visitors.router, records.router, system.router):
        app.include_router(r)

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # ---- 前端靜態檔（Vite build 輸出到 backend/app/static） ----
    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith(("api/", "ws/")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            f = (STATIC_DIR / full_path).resolve()
            if full_path and f.is_file() and STATIC_DIR.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(STATIC_DIR / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        async def no_frontend():
            return JSONResponse({"detail": "前端尚未建置，請執行 cd frontend && npm install && npm run build"})

    return app
