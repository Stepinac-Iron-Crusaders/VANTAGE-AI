"""Team dossier generation via the Gemini scouting agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from vantage.api.gemini_client import GeminiClient
from vantage.config.settings import get_settings
from vantage.core.logging import get_logger
from vantage.models.models import ResearchRecord
from vantage.scout.data import build_team_context, get_event

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class TeamDossier:
    team_number: int
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    profile: dict = field(default_factory=dict)
    tier: str = "unknown"
    confidence: float = 0.0
    raw_data: dict = field(default_factory=dict)

    def to_research_dict(self) -> dict:
        data = {
            "team_number": self.team_number,
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "profile": self.profile,
            "tier": self.tier,
            "confidence": self.confidence,
        }
        return {"confidence": self.confidence, "data": data}

    @classmethod
    def from_payload(
        cls, team_number: int, payload: dict | None
    ) -> TeamDossier:
        payload = payload or {}
        return cls(
            team_number=team_number,
            summary=payload.get("summary") or "",
            strengths=[str(s) for s in payload.get("strengths") or []],
            weaknesses=[str(w) for w in payload.get("weaknesses") or []],
            profile={
                k: v
                for k, v in payload.get("profile", {}).items()
            },
            tier=str(payload.get("tier") or "unknown"),
            confidence=float(payload.get("confidence") or 0.0),
            raw_data=payload,
        )


SYSTEM_PROMPT = """You are the Vantage FRC scouting analyst. You convert raw
scouting data about a FIRST Robotics team into a concise, honest dossier.

Rules:
- Only assert what the data supports. Use the phrase 'data unavailable' rather
  than guessing.
- Output STRICTLY a single JSON object with this exact shape:
  {
    "summary": "2-3 sentence team summary",
    "strengths": ["...", "..."],
    "weaknesses": ["...", "..."],
    "profile": {
      "auto": "short note or 'data unavailable'",
      "teleop": "short note or 'data unavailable'",
      "endgame": "short note or 'data unavailable'",
      "reliability": "short note or 'data unavailable'"
    },
    "tier": "elite|strong|mid|weak",
    "confidence": 0.0
  }
- confidence 0..1 reflecting how much data was available.
"""


def build_team_context_prompt(team_number: int, context: dict) -> str:
    compact = json.dumps(context, default=str)
    return (
        f"Scout FRC team {team_number} using this data (JSON):\n{compact}\n\n"
        "Return the JSON dossier."
    )


class ScoutingAgent:
    """One agent that produces structured scouting intelligence via Gemini."""

    def __init__(
        self,
        session: AsyncSession,
        client: GeminiClient | None = None,
    ):
        self.session = session
        self.client = client or GeminiClient()

    async def team_dossier(
        self,
        team_number: int,
        event_key: str | None = None,
        persist: bool = True,
    ) -> TeamDossier:
        event = await get_event(self.session, event_key) if event_key else None
        context = await build_team_context(
            self.session, team_number, event=event
        )
        prompt = build_team_context_prompt(team_number, context)

        async with self.client as client:
            payload = await client.complete_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=settings.gemini_temperature,
                max_tokens=4096,
            )

        dossier = TeamDossier.from_payload(team_number, payload)
        dossier.raw_data["context"] = context

        if persist:
            await self._persist_dossier(dossier)
        return dossier

    async def _persist_dossier(self, dossier: TeamDossier) -> None:
        record = ResearchRecord(
            team_number=dossier.team_number,
            source="gemini-scout",
            source_url="",
            title=f"Team {dossier.team_number} scouting dossier (tier {dossier.tier})",
            content_summary=dossier.summary,
            info_type="scouting_dossier",
            confidence=dossier.confidence,
            verification_status="unverified",
            raw_data=dossier.raw_data,
        )
        self.session.add(record)
        await self.session.commit()
        logger.info(
            "dossier persisted",
            team_number=dossier.team_number,
            tier=dossier.tier,
        )


def summarize_dossier(dossier: TeamDossier) -> str:
    """Human-readable rendering of a dossier for CLI output."""
    lines = [
        "Team {}  tier={}  confidence={:.2f}".format(  # noqa: UP032 (kept <88 cols)
            dossier.team_number, dossier.tier, dossier.confidence
        ),
        dossier.summary or "(no summary)",
    ]
    if dossier.profile:
        for k in ("auto", "teleop", "endgame", "reliability"):
            v = dossier.profile.get(k)
            if v:
                lines.append(f"  {k}: {v}")
    if dossier.strengths:
        lines.append("  strengths:")
        lines.extend(f"    - {s}" for s in dossier.strengths)
    if dossier.weaknesses:
        lines.append("  weaknesses:")
        lines.extend(f"    - {w}" for w in dossier.weaknesses)
    return "\n".join(lines)