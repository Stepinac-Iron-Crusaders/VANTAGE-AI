"""Alliance matchup advisor: combine Phase 2 EPA predictions with Gemini reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.api.gemini_client import GeminiClient
from vantage.config.settings import get_settings
from vantage.core.logging import get_logger
from vantage.models.models import EPAMetric, ResearchRecord
from vantage.replay.predictors import TeamEPA, predict_epa

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class MatchupAnalysis:
    red_teams: list[int]
    blue_teams: list[int]
    event_key: str | None = None
    predicted_winner: str | None = None
    predicted_red_score: float | None = None
    predicted_blue_score: float | None = None
    prediction_confidence: float | None = None
    strategy: str = "epa"
    model_reasoning: str = ""
    upset_risk: str = ""
    scouting_notes: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


async def _load_team_epa(
    session: AsyncSession,
    team_numbers: list[int],
    season: int,
    match_key: str | None = None,
) -> dict[int, TeamEPA]:
    """Load each team's latest EPA for the season, preferring the latest match."""
    out: dict[int, TeamEPA] = {}
    result = await session.execute(
        select(EPAMetric).where(
            EPAMetric.team_number.in_(team_numbers),
            EPAMetric.season == season,
        )
    )
    latest: dict[int, EPAMetric] = {}
    for row in result.scalars().all():
        cur = latest.get(row.team_number)
        if cur is None or (row.match_key or "") > (cur.match_key or ""):
            latest[row.team_number] = row
    for team_number in team_numbers:
        row = latest.get(team_number)
        out[team_number] = TeamEPA(
            team_number=team_number,
            overall_epa=row.overall_epa if row else None,
            auto_epa=row.auto_epa if row else None,
            teleop_epa=row.teleop_epa if row else None,
            endgame_epa=row.endgame_epa if row else None,
        )
    return out


def _epa_list(
    epas: dict[int, TeamEPA], team_numbers: list[int]
) -> list[TeamEPA]:
    return [epas[t] for t in team_numbers if t in epas]


class MatchupAdvisor:
    def __init__(
        self,
        session: AsyncSession,
        client: GeminiClient | None = None,
        season: int = 2025,
        event_key: str | None = None,
    ):
        self.session = session
        self.client = client or GeminiClient()
        self.season = season
        self._event_key = event_key

    async def analyze(
        self,
        red_teams: list[int],
        blue_teams: list[int],
        event_key: str | None = None,
        persist: bool = True,
    ) -> MatchupAnalysis:
        epas = await _load_team_epa(
            self.session, red_teams + blue_teams, self.season, event_key
        )
        red_epa = _epa_list(epas, red_teams)
        blue_epa = _epa_list(epas, blue_teams)

        pred = predict_epa(red_epa, blue_epa)

        analysis = MatchupAnalysis(
            red_teams=red_teams,
            blue_teams=blue_teams,
            event_key=event_key,
            predicted_winner=pred.predicted_winner,
            predicted_red_score=pred.predicted_red_score,
            predicted_blue_score=pred.predicted_blue_score,
            prediction_confidence=pred.confidence,
            strategy=pred.strategy,
        )

        prompt = self._build_prompt(red_teams, blue_teams, pred, epas)
        async with self.client as client:
            payload = await client.complete_json(
                system_prompt=self._system_prompt(),
                user_prompt=prompt,
                temperature=settings.gemini_temperature,
                max_tokens=4096,
            )

        analysis.model_reasoning = str(payload.get("reasoning") or "")
        analysis.upset_risk = str(payload.get("upset_risk") or "")
        analysis.scouting_notes = [
            str(n) for n in payload.get("scouting_notes") or []
        ]
        analysis.raw_data["epa"] = {
            str(t): {
                "overall_epa": e.overall_epa,
                "auto_epa": e.auto_epa,
                "teleop_epa": e.teleop_epa,
                "endgame_epa": e.endgame_epa,
            }
            for t, e in epas.items()
        }
        analysis.raw_data["prediction"] = (
            {
                "winner": pred.predicted_winner,
                "red_score": pred.predicted_red_score,
                "blue_score": pred.predicted_blue_score,
                "confidence": pred.confidence,
            }
        )

        if persist:
            await self._persist(analysis)
        return analysis

    def _system_prompt(self) -> str:
        return (
            "You are the Vantage FRC alliance matchup analyst. Given two alliances "
            "of 3 teams, a model scoreline, and each team's EPA, explain the likely "
            "outcome, the upset risk, and what to watch on the field. Be concrete "
            "and honest; never invent data. Output STRICTLY a single JSON object "
            "with keys: reasoning (string), upset_risk (string), scouting_notes "
            "(array of strings)."
        )

    def _build_prompt(
        self,
        red_teams: list[int],
        blue_teams: list[int],
        pred,
        epas: dict[int, TeamEPA],
    ) -> str:
        def line(t: int) -> str:
            e = epas.get(t)
            if e and e.overall_epa is not None:
                return (
                    f"  - #{t}: overall EPA {e.overall_epa:.2f}, "
                    f"auto {e.auto_epa or 0:.2f}, "
                    f"teleop {e.teleop_epa or 0:.2f}, "
                    f"endgame {e.endgame_epa or 0:.2f}"
                )
            return f"  - #{t}: no EPA data"

        red_block = "\n".join(line(t) for t in red_teams)
        blue_block = "\n".join(line(t) for t in blue_teams)
        event_label = self.event_key or "unknown event"
        return (
            f"Event: {event_label}\n"
            f"RED alliance teams:\n{red_block}\n"
            f"BLUE alliance teams:\n{blue_block}\n"
            f"EPA model predicts: red {self._num(pred.predicted_red_score)} vs "
            f"blue {self._num(pred.predicted_blue_score)}, "
            f"winner={pred.predicted_winner}, confidence={self._num(pred.confidence)}\n"
            "Analyze the matchup and return JSON."
        )

    @property
    def event_key(self) -> str | None:
        return getattr(self, "_event_key", None)

    @staticmethod
    def _num(v: float | None) -> str:
        return f"{v:.1f}" if v is not None else "n/a"

    async def _persist(self, analysis: MatchupAnalysis) -> None:
        record = ResearchRecord(
            team_number=None,
            source="gemini-scout",
            source_url=f"matchup:{'+'.join(map(str, analysis.red_teams))}"
            f"_vs_{'+'.join(map(str, analysis.blue_teams))}",
            title="Alliance matchup analysis",
            content_summary=analysis.model_reasoning,
            info_type="matchup_analysis",
            confidence=(
                analysis.prediction_confidence
                if analysis.prediction_confidence is not None
                else 0.0
            ),
            verification_status="unverified",
            raw_data=analysis.raw_data,
        )
        self.session.add(record)
        await self.session.commit()
        logger.info(
            "matchup analysis persisted",
            red=analysis.red_teams,
            blue=analysis.blue_teams,
        )