"""Vantage FRC Phase 4: web dashboard for the AI tactical intelligence copilot."""

from vantage.web.api import router as api_router  # noqa: F401
from vantage.web.app import app  # noqa: F401
from vantage.web.data import (  # noqa: F401
    event_matches,
    event_rankings,
    replay_runs,
    research_records,
    team_epa_series,
)
from vantage.web.pages import router as pages_router  # noqa: F401
