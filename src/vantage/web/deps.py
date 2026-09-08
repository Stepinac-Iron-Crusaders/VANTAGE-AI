"""Shared dependencies for the Vantage web app (async sessions, templates)."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from vantage.core.logging import get_logger
from vantage.db.session import get_session

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

templates.env.filters["pct"] = lambda v: (
    f"{v:.0%}" if v is not None else "n/a"
)
templates.env.filters["f1"] = lambda v: (
    f"{v:.1f}" if v is not None else "n/a"
)
templates.env.filters["short"] = lambda v: (
    str(v)[:80] + "…" if v is not None and len(str(v)) > 80 else (v or "")
)


async def get_db():
    async with get_session() as session:
        yield session


def render(request: Request, template: str, context: dict):
    return templates.TemplateResponse(
        request, template, context | {"active": template}
    )