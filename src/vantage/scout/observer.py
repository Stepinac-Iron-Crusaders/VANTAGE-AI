"""Match observer: concise scouting observations for played matches via Gemini."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from vantage.api.gemini_client import GeminiClient
from vantage.config.settings import get_settings
from vantage.core.logging import get_logger
from vantage.models.models import Match, MatchObservation
from vantage.scout.data import match_team_numbers

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class MatchReview:
    match_key: str
    observations: list[dict] = field(default_factory=list)

    def persisted_count(self) -> int:
        return len(self.observations)


SYSTEM_PROMPT = (
    "You are the Vantage FRC match observer. You are given one completed match "
    "with its alliance lineups and final score. Produce scouting observations "
    "about PLAYED behavior. Rules: no invented stats; if the data is thin, keep "
    "observations qualitative but tied to the result shown. The team_number in "
    "every observation MUST be an actual FRC team number from the red or blue "
    "lineup — never 1 or 2 or an index. Output STRICTLY a single JSON object: "
    "{\"observations\": [{\"team_number\": int, "
    "\"observation\": \"short sentence\", \"confidence\": 0.0}, ...]}. "
    "1-3 observations per team."
)


def _build_prompt(match: Match, red: list[int], blue: list[int]) -> str:
    winner = match.winning_alliance or "unknown"
    return (
        f"match_key: {match.key}\n"
        f"competition_level: {match.competition_level} set {match.set_number} "
        f"match {match.match_number}\n"
        f"winner: {winner}\n"
        f"score: red {match.red_score} - {match.blue_score} blue\n"
        f"red teams: {red}\n"
        f"blue teams: {blue}\n\n"
        "Return the observations JSON."
    )


def filter_observations(
    raw_observations: list, allowed_teams: set[int]
) -> list[dict]:
    """Validate and clean model observations against the match lineup."""
    observations: list[dict] = []
    for item in raw_observations or []:
        if not isinstance(item, dict):
            continue
        team_number = None
        try:
            team_number = int(item["team_number"])
        except (KeyError, TypeError, ValueError):
            pass
        if team_number is None or team_number not in allowed_teams:
            logger.info(
                "dropping observation for team not in lineup",
                team_number=team_number,
            )
            continue
        text = str(item.get("observation") or "").strip()
        if not text:
            continue
        observations.append(
            {
                "team_number": team_number,
                "observation": text,
                "confidence": float(item.get("confidence") or 0.0),
            }
        )
    return observations


class MatchObserver:
    def __init__(
        self,
        session: AsyncSession,
        client: GeminiClient | None = None,
    ):
        self.session = session
        self.client = client or GeminiClient()

    async def observe(
        self,
        match: Match,
        persist: bool = True,
    ) -> MatchReview:
        red, blue = await match_team_numbers(self.session, match)
        prompt = _build_prompt(match, red, blue)
        payload = None
        async with self.client as client:
            payload = await client.complete_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=4096,
            )

        raw_observations = payload.get("observations") or []
        review = MatchReview(
            match_key=match.key or "",
            observations=filter_observations(
                raw_observations, set(red) | set(blue)
            ),
        )
        if persist:
            await self._persist(review, match)
        return review

    async def _persist(self, review: MatchReview, match: Match) -> None:
        for obs in review.observations:
            team_number = obs.get("team_number")
            if not team_number:
                continue
            self.session.add(
                MatchObservation(
                    match_id=match.id,
                    team_number=team_number,
                    event_type=(
                        f"{match.competition_level}{match.match_number}"
                    ),
                    observation=obs["observation"],
                    confidence=obs["confidence"],
                    source_agent="gemini-scout",
                    raw_data={"match_key": match.key},
                )
            )
        if review.observations:
            await self.session.commit()
            logger.info(
                "observations persisted",
                match_key=match.key,
                count=len(review.observations),
            )