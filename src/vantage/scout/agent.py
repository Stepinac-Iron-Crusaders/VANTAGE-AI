"""Scouting agent: end-to-end pipeline for generating team intelligence via Gemini.

Wires together data assembly, dossier generation, matchup analysis, match
observation, and hypothesis extraction.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.api.gemini_client import GeminiClient
from vantage.core.logging import get_logger
from vantage.models.models import (
    Event,
    EventRanking,
    Match,
    MatchObservation,
    ResearchRecord,
)
from vantage.scout.dossier import ScoutingAgent, TeamDossier
from vantage.scout.hypotheses import HypothesisBuilder
from vantage.scout.matchup import MatchupAdvisor
from vantage.scout.observer import MatchObserver

logger = get_logger(__name__)


class VantageScout:
    """Facade combining all Phase 3 scouting capabilities."""

    def __init__(
        self,
        session: AsyncSession,
        client: GeminiClient | None = None,
    ):
        self.session = session
        self.client = client

    def _agent(self) -> ScoutingAgent:
        return ScoutingAgent(self.session, self.client)

    def _matchup(self, season: int, event_key: str | None) -> MatchupAdvisor:
        return MatchupAdvisor(
            self.session, self.client, season=season, event_key=event_key
        )

    def _observer(self) -> MatchObserver:
        return MatchObserver(self.session, self.client)

    def _hypotheses(self) -> HypothesisBuilder:
        return HypothesisBuilder(self.session, self.client)

    async def scout_team(
        self,
        team_number: int,
        event_key: str | None = None,
        with_hypotheses: bool = True,
    ) -> TeamDossier:
        """Full pipeline: dossier + hypotheses + persisted research record."""
        dossier = await self._agent().team_dossier(team_number, event_key=event_key)
        if with_hypotheses:
            await self._hypotheses().build(dossier)
        return dossier

    async def scout_event(
        self,
        event_key: str,
        team_numbers: list[int] | None = None,
        with_hypotheses: bool = False,
        limit: int | None = None,
    ) -> list[TeamDossier]:
        result = await self.session.execute(
            select(Event).where(Event.event_code == event_key)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Event {event_key} not found")

        if not team_numbers:
            rankings = await self.session.execute(
                select(EventRanking)
                .where(EventRanking.event_id == event.id)
                .order_by(EventRanking.rank)
            )
            team_numbers = [r.team_number for r in rankings.scalars().all()]
        if limit:
            team_numbers = team_numbers[:limit]

        dossiers = []
        for team_number in team_numbers:
            dossiers.append(
                await self.scout_team(team_number, event_key, with_hypotheses)
            )
        return dossiers

    async def analyze_matchup(
        self,
        red_teams: list[int],
        blue_teams: list[int],
        event_key: str | None = None,
        season: int = 2025,
    ):
        return await self._matchup(season, event_key).analyze(
            red_teams, blue_teams, event_key
        )

    async def observe_event(
        self,
        event_key: str,
        only_unobserved: bool = True,
        limit: int | None = None,
    ):
        result = await self.session.execute(
            select(Event).where(Event.event_code == event_key)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Event {event_key} not found")

        matches_result = await self.session.execute(
            select(Match).where(Match.event_id == event.id)
        )
        matches = list(matches_result.scalars().all())

        observer = self._observer()
        reviews = []
        observed_keys = set()
        if only_unobserved:
            obs_result = await self.session.execute(
                select(MatchObservation)
                .join(Match, Match.id == MatchObservation.match_id)
                .where(Match.event_id == event.id)
            )
            observed_keys = {
                (obs.raw_data or {}).get("match_key")
                for obs in obs_result.scalars().all()
            }

        for match in matches:
            if match.status != "complete" or match.winning_alliance is None:
                continue
            if only_unobserved and match.key in observed_keys:
                continue
            reviews.append(await observer.observe(match))
            if limit and len(reviews) >= limit:
                break
        return reviews

    async def nearby_teams(
        self, team_number: int, event_key: str, k: int = 3
    ) -> list[int]:
        """Teams most similar in event rank (for alliance planning)."""
        result = await self.session.execute(
            select(Event).where(Event.event_code == event_key)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Event {event_key} not found")
        ranks = await self.session.execute(
            select(EventRanking)
            .where(EventRanking.event_id == event.id)
            .order_by(EventRanking.rank)
        )
        ordered = [r.team_number for r in ranks.scalars().all()]
        if team_number not in ordered:
            return []
        idx = ordered.index(team_number)
        out = []
        for delta in range(1, k + 1):
            if idx - delta >= 0:
                out.append(ordered[idx - delta])
            if idx + delta < len(ordered):
                out.append(ordered[idx + delta])
        return out[:k]

    async def stored_research(
        self, team_number: int | None = None, limit: int = 10
    ) -> list[ResearchRecord]:
        query = select(ResearchRecord).order_by(ResearchRecord.created_at.desc())
        if team_number is not None:
            query = query.where(ResearchRecord.team_number == team_number)
        query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())