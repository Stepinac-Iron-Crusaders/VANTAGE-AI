"""Hypothesis extraction: turn team dossiers into testable strategic hypotheses."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from vantage.api.gemini_client import GeminiClient
from vantage.config.settings import get_settings
from vantage.core.logging import get_logger
from vantage.models.models import Hypothesis
from vantage.scout.dossier import TeamDossier

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class HypothesisSet:
    team_number: int
    hypotheses: list[dict] = field(default_factory=list)

    def persisted_count(self) -> int:
        return len(self.hypotheses)


SYSTEM_PROMPT = (
    "You are the Vantage FRC strategy analyst. Given a team dossier, propose 1-3 "
    "concise, testable strategic hypotheses about how this team contributes within "
    "an alliance. Each must be a concrete claim we could confirm with match data. "
    "Output STRICTLY a single JSON object: {\"hypotheses\": [{"
    "\"category\": \"drive|auto|teleop|endgame|defense|alliance\", "
    "\"hypothesis\": \"one sentence\", "
    "\"confidence\": 0.0}, ...]}"
)


def _build_prompt(dossier: TeamDossier) -> str:
    from vantage.scout.dossier import summarize_dossier

    summary = summarize_dossier(dossier)
    return (
        f"Team {dossier.team_number} dossier:\n{summary}\n\n"
        "Return the hypotheses JSON."
    )


class HypothesisBuilder:
    def __init__(
        self,
        session: AsyncSession,
        client: GeminiClient | None = None,
    ):
        self.session = session
        self.client = client or GeminiClient()

    async def build(
        self,
        dossier: TeamDossier,
        persist: bool = True,
    ) -> HypothesisSet:
        prompt = _build_prompt(dossier)
        async with self.client as client:
            payload = await client.complete_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=4096,
            )

        items = []
        for item in payload.get("hypotheses") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("hypothesis") or "").strip()
            if not text:
                continue
            items.append(
                {
                    "category": str(item.get("category") or "drive"),
                    "hypothesis": text,
                    "confidence": float(item.get("confidence") or 0.3),
                }
            )

        result = HypothesisSet(
            team_number=dossier.team_number, hypotheses=items
        )
        if persist:
            await self._persist(result)
        return result

    async def _persist(self, result: HypothesisSet) -> None:
        for item in result.hypotheses:
            self.session.add(
                Hypothesis(
                    team_number=result.team_number,
                    category=item["category"],
                    hypothesis_text=item["hypothesis"],
                    confidence=item["confidence"],
                    status="unconfirmed",
                    evidence_count=0,
                    evidence_matches=[],
                )
            )
        if result.hypotheses:
            await self.session.commit()
            logger.info(
                "hypotheses persisted",
                team_number=result.team_number,
                count=len(result.hypotheses),
            )