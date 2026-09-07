import asyncio
from typing import Any, Optional
import httpx
from pydantic import BaseModel, Field

from vantage.config.settings import get_settings
from vantage.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class TBAMatch(BaseModel):
    key: str
    comp_level: str
    set_number: int
    match_number: int
    alliances: dict
    scores: list[int] | None = None
    time: int | None = None
    actual_time: int | None = None
    predicted_time: int | None = None
    post_result_time: int | None = None
    winning_alliance: str | None = None
    status: str | None = None


class TBATeam(BaseModel):
    team_number: int
    name: str | None = None
    nickname: str | None = None
    city: str | None = None
    state_prov: str | None = None
    country: str | None = None
    rookies_year: int | None = None
    website: str | None = None


class TBAEvent(BaseModel):
    key: str
    name: str
    event_code: str | None = None
    event_type: int | None = None
    city: str | None = None
    state_prov: str | None = None
    country: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    season: int | None = None
    district: dict | None = None


class TBARanking(BaseModel):
    team_key: str
    rank: int
    rp: float | None = None
    auto_points: float | None = None
    teleop_points: float | None = None
    playoff_rp: float | None = None
    sort_order_info: dict | None = None


class TBAAPIError(Exception):
    pass


class TBAClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.tba_api_key
        self.base_url = base_url or settings.tba_base_url
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> "TBAClient":
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        timeout = httpx.Timeout(30.0, connect=10.0)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-TBA-Auth-Key": self.api_key} if self.api_key else {},
            limits=limits,
            timeout=timeout,
        )
        self._semaphore = asyncio.Semaphore(settings.tba_rate_limit)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> Any:
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
                    "TBA API error",
                    method=method,
                    path=path,
                    status=e.response.status_code,
                    error=str(e),
                )
                raise TBAAPIError(f"TBA {method} {path}: {e}") from e
            except httpx.RequestError as e:
                logger.error("TBA request failed", method=method, path=path, error=str(e))
                raise TBAAPIError(f"TBA {method} {path}: {e}") from e

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    async def get_team(self, team_number: int) -> TBATeam | None:
        try:
            data = await self.get(f"/team/frc{team_number}/simple")
            data["team_number"] = team_number
            return TBATeam(**data)
        except TBAAPIError:
            return None

    async def get_team_events(self, team_number: int, season: int) -> list[TBAEvent]:
        data = await self.get(f"/team/frc{team_number}/events/{season}/simple")
        return [TBAEvent(**d) for d in data]

    async def get_event_matches(self, event_key: str) -> list[TBAMatch]:
        data = await self.get(f"/event/{event_key}/matches/simple")
        return [TBAMatch(**d) for d in data]

    async def get_event_rankings(self, event_key: str) -> list[TBARanking]:
        data = await self.get(f"/event/{event_key}/rankings")
        rankings = data.get("rankings", []) if isinstance(data, dict) else data
        return [TBARanking(**d) for d in rankings]

    async def get_team_match_history(
        self, team_number: int, season: int
    ) -> list[TBAMatch]:
        data = await self.get(f"/team/frc{team_number}/matches/{season}")
        return [TBAMatch(**d) for d in data]

    async def get_match(self, match_key: str) -> TBAMatch | None:
        try:
            data = await self.get(f"/match/{match_key}/simple")
            return TBAMatch(**data)
        except TBAAPIError:
            return None

    async def get_event(self, event_key: str) -> TBAEvent | None:
        try:
            data = await self.get(f"/event/{event_key}/simple")
            return TBAEvent(**data)
        except TBAAPIError:
            return None

    async def get_event_teams(self, event_key: str) -> list[TBATeam]:
        data = await self.get(f"/event/{event_key}/teams/simple")
        return [TBATeam(**d) for d in data]

    async def get_team_years_participated(self, team_number: int) -> list[int]:
        return await self.get(f"/team/frc{team_number}/years_participated")

    async def get_district_events(self, district_key: str) -> list[TBAEvent]:
        data = await self.get(f"/district/{district_key}/events/simple")
        return [TBAEvent(**d) for d in data]

    async def get_top_teams(self, season: int, count: int = 100) -> list[dict]:
        return await self.get(f"/teams/{season}/top/OPR/{count}")


class TBAClientSync:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.tba_api_key
        self.base_url = base_url or settings.tba_base_url
        self._client: httpx.Client | None = None

    def __enter__(self) -> "TBAClientSync":
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-TBA-Auth-Key": self.api_key} if self.api_key else {},
            timeout=30.0,
        )
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