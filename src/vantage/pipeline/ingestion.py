import asyncio
from datetime import datetime
from typing import Any
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete, and_

from vantage.db.session import get_session
from vantage.models.models import (
    Team,
    Event,
    Match,
    MatchAlliance,
    EventRanking,
    TeamRanking,
    MatchStats,
    TeamHistory,
    EPAMetric,
    AllianceSelection,
)
from vantage.api.tba_client import (
    TBAClient,
    TBATeam,
    TBAEvent,
    TBAMatch,
    TBARanking,
)
from vantage.api.statbotics_client import StatboticsClient

logger = structlog.get_logger(__name__)


class FRCDataPipeline:
    def __init__(self):
        self.tba_client: TBAClient | None = None
        self.statbotics_client: StatboticsClient | None = None

    async def __aenter__(self) -> "FRCDataPipeline":
        self.tba_client = TBAClient()
        self.statbotics_client = StatboticsClient()
        await self.tba_client.__aenter__()
        await self.statbotics_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.tba_client:
            await self.tba_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.statbotics_client:
            await self.statbotics_client.__aexit__(exc_type, exc_val, exc_tb)

    async def ingest_team(self, team_number: int) -> Team | None:
        async with get_session() as session:
            team = await self._get_team(session, team_number)
            if not team:
                team = await self._create_team(session, team_number)
            return team

    async def ingest_team_full(self, team_number: int) -> Team | None:
        async with get_session() as session:
            team = await self._get_team(session, team_number)
            if not team:
                try:
                    team = await self._create_team(session, team_number)
                except Exception as e:
                    logger.error("team creation failed", team_number=team_number, error=str(e))
            if team:
                try:
                    await self._ingest_team_history(session, team_number)
                except Exception as e:
                    logger.error("team history ingest failed", team_number=team_number, error=str(e))
            return team

    async def ingest_event(self, event_key: str) -> Event | None:
        async with get_session() as session:
            event = await self._get_event(session, event_key)
            if not event:
                event = await self._create_event(session, event_key)
            if event:
                await self._ingest_event_matches(session, event_key)
                await self._ingest_event_rankings(session, event_key)
            return event

    async def ingest_event_full(self, event_key: str) -> Event | None:
        async with get_session() as session:
            event = await self.ingest_event(event_key)
            if event:
                await self._ingest_event_teams(session, event_key)
            return event

    async def ingest_season_teams(self, season: int) -> list[int]:
        async with get_session() as session:
            teams = await self.statbotics_client.get_teams(season)
            team_numbers = []
            for t in teams:
                team_number = t.get("team")
                if team_number:
                    team_numbers.append(team_number)
                    await self._upsert_team_from_dict(session, team_number, t)
            logger.info("season teams ingested", season=season, count=len(team_numbers))
            return team_numbers

    async def ingest_team_epa(self, team_number: int, season: int) -> None:
        async with get_session() as session:
            epa_data = await self.statbotics_client.get_team_epa(team_number, season)
            if epa_data:
                await self._store_team_epa(session, epa_data)

    async def ingest_match_epa(self, match_key: str) -> None:
        async with get_session() as session:
            epa_data = await self.statbotics_client.get_match_epa(match_key)
            if epa_data:
                for epa in epa_data:
                    await self._store_match_epa(session, epa)

    async def ingest_match(self, match_key: str) -> Match | None:
        async with get_session() as session:
            match_data = await self.tba_client.get_match(match_key)
            if not match_data:
                return None
            return await self._store_match(session, match_data)

    async def _get_team(self, session: AsyncSession, team_number: int) -> Team | None:
        result = await session.execute(
            select(Team).where(Team.team_number == team_number)
        )
        return result.scalar_one_or_none()

    async def _create_team(self, session: AsyncSession, team_number: int) -> Team | None:
        tba_team = await self.tba_client.get_team(team_number)
        if not tba_team:
            logger.warning("team not found in TBA", team_number=team_number)
            return None
        team = Team(
            team_number=tba_team.team_number,
            name=tba_team.name,
            nickname=tba_team.nickname,
            location=f"{tba_team.city}, {tba_team.state_prov}, {tba_team.country}" if tba_team.city else None,
            country=tba_team.country,
            rookies_year=tba_team.rookies_year,
            website=tba_team.website,
        )
        session.add(team)
        await session.flush()
        logger.info("team created", team_number=team_number)
        return team

    async def _upsert_team_from_dict(self, session: AsyncSession, team_number: int, data: dict) -> Team | None:
        team = await self._get_team(session, team_number)
        if not team:
            team = Team(team_number=team_number, raw_data=data)
            session.add(team)
            await session.flush()
        else:
            team.raw_data = data
        return team

    async def _get_event(self, session: AsyncSession, event_key: str) -> Event | None:
        result = await session.execute(
            select(Event).where(Event.event_code == event_key)
        )
        return result.scalar_one_or_none()

    async def _create_event(self, session: AsyncSession, event_key: str) -> Event | None:
        tba_event = await self.tba_client.get_event(event_key)
        if not tba_event:
            logger.warning("event not found in TBA", event_key=event_key)
            return None
        event = Event(
            event_code=tba_event.key or event_key,
            name=tba_event.name,
            event_type=tba_event.event_type,
            city=tba_event.city,
            state_prov=tba_event.state_prov,
            country=tba_event.country,
            season=tba_event.season or 2025,
            district=tba_event.district.get("display_name") if tba_event.district else None,
            raw_data=tba_event.model_dump(),
        )
        session.add(event)
        await session.flush()
        logger.info("event created", event_key=event_key)
        return event

    async def _ingest_event_matches(self, session: AsyncSession, event_key: str) -> None:
        tba_matches = await self.tba_client.get_event_matches(event_key)
        for match_data in tba_matches:
            await self._store_match(session, match_data)

    async def _ingest_event_rankings(self, session: AsyncSession, event_key: str) -> None:
        rankings = await self.tba_client.get_event_rankings(event_key)
        event_id = await self._get_event_id(session, event_key)
        existing = await session.execute(
            select(EventRanking).where(EventRanking.event_id == event_id)
        )
        existing_map = {
            r.team_number: r for r in existing.scalars().all()
        }
        for rank_data in rankings:
            team_number = int(rank_data.team_key.replace("frc", ""))
            fields = dict(
                rank=rank_data.rank,
                rp=rank_data.rp,
                autoplay_points=rank_data.auto_points,
                teleop_points=rank_data.teleop_points,
                playoff_rp=rank_data.playoff_rp,
                sort_order_info=rank_data.sort_order_info or {},
                raw_data=rank_data.model_dump(),
            )
            ranking = existing_map.get(team_number)
            if ranking:
                for k, v in fields.items():
                    setattr(ranking, k, v)
            else:
                session.add(EventRanking(event_id=event_id, team_number=team_number, **fields))
        logger.info("rankings ingested", event_key=event_key, count=len(rankings))

    async def _ingest_event_teams(self, session: AsyncSession, event_key: str) -> None:
        teams = await self.tba_client.get_event_teams(event_key)
        for tba_team in teams:
            await self._upsert_team_from_dict(session, tba_team.team_number, tba_team.model_dump())

    async def _ingest_team_history(self, session: AsyncSession, team_number: int) -> None:
        team = await self._get_team(session, team_number)
        if not team:
            return
        season = 2025
        try:
            epa_data = await self.statbotics_client.get_team_epa(team_number, season)
            if epa_data:
                await self._store_team_epa(session, epa_data)
        except Exception as e:
            logger.error("team EPA ingest failed", team_number=team_number, error=str(e))

    async def _store_team_epa(self, session: AsyncSession, epa_data: Any) -> None:
        norm_epa = getattr(epa_data, "norm_epa", None)
        overall_epa = (norm_epa or {}).get("current") if norm_epa else None
        existing = await session.execute(
            select(EPAMetric).where(
                EPAMetric.team_number == epa_data.team,
                EPAMetric.season == epa_data.season,
                EPAMetric.match_key == "",
            )
        )
        existing_metric = existing.scalar_one_or_none()
        if existing_metric:
            existing_metric.overall_epa = overall_epa
            existing_metric.raw_data = epa_data.model_dump()
        else:
            metric = EPAMetric(
                team_number=epa_data.team,
                season=epa_data.season,
                match_key="",
                overall_epa=overall_epa,
                raw_data=epa_data.model_dump(),
            )
            session.add(metric)

    async def _store_match_epa(self, session: AsyncSession, epa_data: Any) -> None:
        metric = EPAMetric(
            team_number=epa_data.team,
            season=epa_data.season,
            match_key=epa_data.key,
            auto_epa=epa_data.auto_epa,
            teleop_epa=epa_data.teleop_epa,
            endgame_epa=epa_data.endgame_epa,
            overall_epa=epa_data.overall_epa,
            raw_data=epa_data.model_dump(),
        )
        session.add(metric)

    async def _store_match(
        self, session: AsyncSession, match_data: TBAMatch
    ) -> Match | None:
        parts = match_data.key.split("_")
        if len(parts) < 2:
            return None
        event_code = parts[0]
        event = await self._get_event(session, event_code)
        if not event:
            event = await self._create_event(session, event_code)
            if not event:
                return None

        red_score = match_data.alliances.get("red", {}).get("score")
        blue_score = match_data.alliances.get("blue", {}).get("score")
        match_status = "complete" if match_data.winning_alliance else "scheduled"

        existing = await session.execute(
            select(Match).where(
                Match.event_id == event.id,
                Match.match_number == match_data.match_number,
                Match.set_number == match_data.set_number,
                Match.competition_level == match_data.comp_level,
            )
        )
        existing_match = existing.scalar_one_or_none()

        if existing_match:
            match = existing_match
            match.red_score = red_score
            match.blue_score = blue_score
            match.winning_alliance = match_data.winning_alliance
            match.raw_alliances = match_data.alliances
            match.raw_scores = match_data.scores
            match.status = match_status
        else:
            match = Match(
                event_id=event.id,
                event=event,
                match_number=match_data.match_number,
                set_number=match_data.set_number,
                competition_level=match_data.comp_level,
                red_score=red_score,
                blue_score=blue_score,
                winning_alliance=match_data.winning_alliance,
                raw_alliances=match_data.alliances,
                raw_scores=match_data.scores,
                status=match_status,
            )
            session.add(match)

        await session.flush()
        alliance_team_keys = await self._store_match_alliances(session, match, match_data)
        await self._store_match_stats(session, match, alliance_team_keys)
        await session.flush()
        return match

    async def _store_match_alliances(
        self, session: AsyncSession, match: Match, match_data: TBAMatch
    ) -> dict[str, list[str]]:
        alliance_team_keys: dict[str, list[str]] = {}
        for color in ["red", "blue"]:
            alliance_data = match_data.alliances.get(color, {})
            team_keys = alliance_data.get("team_keys", [])
            alliance_team_keys[color] = team_keys
            team_numbers = [int(k.replace("frc", "")) for k in team_keys]
            score = alliance_data.get("score")
            existing = await session.execute(
                select(MatchAlliance).where(
                    MatchAlliance.match_id == match.id,
                    MatchAlliance.alliance_color == color,
                )
            )
            alliance = existing.scalar_one_or_none()
            if alliance:
                alliance.team_keys = team_keys
                alliance.score = score
            else:
                alliance = MatchAlliance(
                    match_id=match.id,
                    alliance_color=color,
                    team_keys=team_keys,
                    score=score,
                )
                session.add(alliance)
        return alliance_team_keys

    async def _store_match_stats(
        self, session: AsyncSession, match: Match, alliance_team_keys: dict[str, list[str]]
    ) -> None:
        all_team_keys = alliance_team_keys.get("red", []) + alliance_team_keys.get("blue", [])
        for team_key in all_team_keys:
            team_number = int(team_key.replace("frc", ""))
            existing = await session.execute(
                select(MatchStats).where(
                    MatchStats.match_id == match.id,
                    MatchStats.team_number == team_number,
                )
            )
            if not existing.scalar_one_or_none():
                stats = MatchStats(
                    match_id=match.id,
                    team_number=team_number,
                )
                session.add(stats)

    async def _store_match_stats_from_dict(
        self, session: AsyncSession, team_number: int, data: dict
    ) -> None:
        stats = MatchStats(
            team_number=team_number,
            auto_points=data.get("auto_points"),
            teleop_points=data.get("teleop_points"),
            rp_points=data.get("rp_points"),
            speakers_amplified=data.get("speakers_amplified"),
            amps=data.get("amps"),
            climbs=data.get("climbs"),
            raw_data=data,
        )
        session.add(stats)

    async def _get_event_id(self, session: AsyncSession, event_key: str) -> str | None:
        result = await session.execute(
            select(Event.id).where(Event.event_code == event_key)
        )
        row = result.scalar_one_or_none()
        return row

    async def ingest_competition_full(self, event_key: str) -> Event | None:
        async with get_session() as session:
            event = await self._create_event(session, event_key)
            if event:
                await self._ingest_event_matches(session, event_key)
                await self._ingest_event_rankings(session, event_key)
                await self._ingest_event_teams(session, event_key)
            return event

    async def backfill_season(self, season: int) -> dict:
        teams = await self.ingest_season_teams(season)
        event_count = 0
        match_count = 0
        for team_number in teams:
            try:
                team = await self.ingest_team_full(team_number)
                if team:
                    for event in team.raw_data.get("events", []):
                        event_count += 1
                        await self.ingest_event_full(event.get("key", ""))
            except Exception as e:
                logger.error("backfill error", team=team_number, error=str(e))
        logger.info("season backfill complete", season=season, teams=len(teams))
        return {"season": season, "teams": len(teams), "events": event_count, "matches": match_count}

    async def count_event_data(self, event_key: str) -> dict:
        from sqlalchemy import func

        async with get_session() as session:
            event = await self._get_event(session, event_key)
            if not event:
                return {}
            match_count = (
                await session.execute(
                    select(func.count()).select_from(Match).where(Match.event_id == event.id)
                )
            ).scalar() or 0
            ranking_count = (
                await session.execute(
                    select(func.count()).select_from(EventRanking).where(
                        EventRanking.event_id == event.id
                    )
                )
            ).scalar() or 0
            team_numbers = {
                tba_team.team_number
                for tba_team in await self.tba_client.get_event_teams(event_key)
            }
            return {
                "matches": match_count,
                "rankings": ranking_count,
                "teams": len(team_numbers),
            }

    async def health_check(self) -> dict:
        tba_ok = False
        statbotics_ok = False
        try:
            team = await self.tba_client.get_team(254)
            tba_ok = team is not None
        except Exception:
            pass
        try:
            team = await self.statbotics_client.get_team_epa(254, 2025)
            statbotics_ok = team is not None
        except Exception:
            pass
        return {
            "tba_api": "ok" if tba_ok else "error",
            "statbotics_api": "ok" if statbotics_ok else "error",
        }