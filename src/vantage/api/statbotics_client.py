import asyncio
from typing import Any

import httpx
from pydantic import BaseModel

from vantage.config.settings import get_settings
from vantage.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class StatboticsTeamEPA(BaseModel):
    team: int
    season: int | None = None
    opr: float | None = None
    dpr: float | None = None
    ccwm: float | None = None
    auto_epa: float | None = None
    teleop_epa: float | None = None
    endgame_epa: float | None = None
    rp: float | None = None
    matches_played: int | None = None
    norm_epa: dict | None = None
    record: dict | None = None
    raw_data: dict | None = None


class StatboticsMatchEPA(BaseModel):
    key: str
    team: int
    season: int
    auto_epa: float | None = None
    teleop_epa: float | None = None
    endgame_epa: float | None = None
    overall_epa: float | None = None
    auto_points: float | None = None
    teleop_points: float | None = None
    rp_points: float | None = None
    pred_winner: str | None = None
    pred_red_score: float | None = None
    pred_blue_score: float | None = None
    pred_red_prob: float | None = None


class StatboticsError(Exception):
    pass


class StatboticsClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.statbotics_base_url
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> "StatboticsClient":
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        timeout = httpx.Timeout(30.0, connect=10.0)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            limits=limits,
            timeout=timeout,
        )
        self._semaphore = asyncio.Semaphore(settings.statbotics_rate_limit)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        async with self._semaphore:
            url = f"/{path.lstrip('/')}"
            try:
                resp = await self._client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "Statbotics API error",
                    method=method,
                    path=path,
                    status=e.response.status_code,
                    error=str(e),
                )
                raise StatboticsError(f"Statbotics {method} {path}: {e}") from e
            except httpx.RequestError as e:
                logger.error(
                    "Statbotics request failed",
                    method=method,
                    path=path,
                    error=str(e),
                )
                raise StatboticsError(f"Statbotics {method} {path}: {e}") from e

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    async def get_team_epa(
        self, team_number: int, season: int | None = None
    ) -> StatboticsTeamEPA | None:
        try:
            params = {}
            if season:
                params["season"] = season
            data = await self.get(f"/team/{team_number}", params=params)
            data["team"] = team_number
            data["season"] = season or data.get("last_active_year")
            return StatboticsTeamEPA(**data)
        except (StatboticsError, Exception):
            return None

    async def get_match_epa(self, match_key: str) -> list[StatboticsMatchEPA] | None:
        try:
            data = await self.get(f"/match/{match_key}")
            epas = data.get("epas", {})
            pred = data.get("pred", {}) or {}
            results = []
            for team_key, epa_data in epas.items():
                match_epa = StatboticsMatchEPA(
                    key=data.get("key"),
                    team=int(team_key),
                    season=data.get("year"),
                    auto_epa=epa_data.get("auto_epa"),
                    teleop_epa=epa_data.get("teleop_epa"),
                    endgame_epa=epa_data.get("endgame_epa"),
                    overall_epa=epa_data.get("epa"),
                    pred_winner=pred.get("winner"),
                    pred_red_score=pred.get("red_score"),
                    pred_blue_score=pred.get("blue_score"),
                    pred_red_prob=pred.get("red_win_prob"),
                )
                results.append(match_epa)
            return results
        except (StatboticsError, Exception):
            return None

    async def get_team_matches(self, team_number: int, season: int) -> list[dict]:
        return await self.get(f"/team/{team_number}/matches/season/{season}")

    async def get_event_teams(self, event_key: str, season: int) -> list[dict]:
        return await self.get(f"/event/{season}/{event_key}")

    async def get_teams(self, season: int) -> list[dict]:
        return await self.get(f"/teams/{season}")


class StatboticsClientSync:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.statbotics_base_url
        self._client: httpx.Client | None = None

    def __enter__(self) -> "StatboticsClientSync":
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def get(self, path: str) -> Any:
        if not self._client:
            raise RuntimeError("Client not initialized")
        resp = self._client.get(f"/{path.lstrip('/')}")
        resp.raise_for_status()
        return resp.json()