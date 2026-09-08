"""Vantage FRC web dashboard: FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vantage.config.settings import get_settings
from vantage.core.logging import get_logger
from vantage.db.session import close_db, init_db
from vantage.web import api, pages

logger = get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("starting vantage web", app=settings.app_name)
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Vantage FRC Copilot",
        description="AI tactical intelligence and scouting dashboard for FRC",
        version="0.4.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.include_router(pages.router)
    app.include_router(api.router)
    app.mount(
        "/static", StaticFiles(directory=str(_STATIC_DIR)), name="static"
    )
    return app


app = create_app()