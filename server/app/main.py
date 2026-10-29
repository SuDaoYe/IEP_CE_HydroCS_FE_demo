"""HydroCS integrated API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import BASE_DIR, settings
from .routers import admin, admin_data, auth, fields, geo, imagery, irrigation, segment, sync
from .services import era5, et_grid, imagery as imagery_service, regions, segmentation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("hydrocs")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    log.info("database ready at %s", settings.database_path)
    if settings.seed_demo:
        from .seed import ensure_seed

        ensure_seed()
    from .services import params as parameter_service

    parameter_service.migrate_legacy()
    log.info("segmentation backend: %s", segmentation.backend_status()["backend"])
    grid = et_grid.status()
    log.info("ET grid: %s", "ready" if grid.get("available") else grid.get("error"))
    cube = era5.status()
    log.info("ERA5 cube: %s", "ready" if cube.get("available") else cube.get("error"))
    yield


app = FastAPI(
    title="HydroCS 智能灌溉 API",
    version="1.0.0",
    description=(
        "卫星影像 → YOLO11s-seg 田块识别 → 面积 → 作物生育期 → 灌溉需水量。\n\n"
        "识别与需水解算均在服务端完成；客户端只负责渲染与离线缓存。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, fields.router, segment.router, irrigation.router,
               imagery.router, sync.router, geo.router, admin.router, admin_data.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    return {
        "ok": True,
        "app": settings.app_name,
        "segmentation": segmentation.backend_status(),
        "et_grid": et_grid.status(),
        "era5": era5.status(),
        "imagery": imagery_service.provider_catalog(),
    }


# --- optional single-port deployment: serve the built SPA -----------------
_DIST = BASE_DIR.parent / "web" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")


def run() -> None:  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)


__all__ = ["app", "run"]
