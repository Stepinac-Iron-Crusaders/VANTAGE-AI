"""Data assembly helpers for the scouting agent: gather team & event context
from the database into plain dicts that can be serialized into prompts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.models.models import (
    EPAMetric,
    Event,
    EventRanking,
    Match,
    MatchAlliance,
    Team,
)


def _fmt(v: float | int | None, ndigits: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.{ndigits}f}"


async def get_event(session: AsyncSession, event_key: str) -> Event | None:
    result = await session.execute(
        select(Event).where(Event.event_code == event_key)
    )
    return result.scalar_one_or_none()


async def team_basic(session: AsyncSession, team_number: int) -> dict:
    result = await session.execute(
        select(Team).where(Team.team_number == team_number)
    )
    team = result.scalar_one_or_none()
    if not team:
        return {"team_number": team_number, "name": "unknown", "nickname": "unknown"}
    return {
        "team_number": team_number,
        "name": team.name or "unknown",
        "nickname": team.nickname or "unknown",
    }


async def team_epa_profile(
    session: AsyncSession, team_number: int, season: int
) -> dict:
    """Average per-match EPA for a team in a season (from the latest ingested data)."""
    result = await session.execute(
        select(EPAMetric)
        .where(EPAMetric.team_number == team_number, EPAMetric.season == season)
        .order_by(EPAMetric.match_key)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"rows": 0}

    def _avg(field: str) -> float | None:
        values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        if not values:
            return None
        return sum(values) / len(values)

    latest = rows[-1]
    return {
        "rows": len(rows),
        "matches": len(rows),
        "avg_auto_epa": _avg("auto_epa"),
        "avg_teleop_epa": _avg("teleop_epa"),
        "avg_endgame_epa": _avg("endgame_epa"),
        "avg_overall_epa": _avg("overall_epa"),
        "latest_overall_epa": latest.overall_epa,
    }


async def team_event_record(
    session: AsyncSession,
    team_number: int,
    event: Event,
    matches: list[Match] | None = None,
) -> dict:
    """Team's record within a single event: W/L/T, avg margins, alliance EPA context."""
    if matches is None:
        result = await session.execute(
            select(Match).where(Match.event_id == event.id)
        )
        matches = list(result.scalars().all())

    wins = losses = ties = 0
    total_score = total_opp = 0.0
    played = 0
    for match in matches:
        if match.winning_alliance is None or match.red_score is None:
            continue
        teams = await match_team_numbers(session, match)
        if team_number not in teams["red"] and team_number not in teams["blue"]:
            continue
        color = "red" if team_number in teams["red"] else "blue"
        my_score = match.red_score if color == "red" else match.blue_score
        opp_score = match.blue_score if color == "red" else match.red_score
        played += 1
        total_score += my_score
        total_opp += opp_score
        if match.winning_alliance == color:
            wins += 1
        elif match.winning_alliance == "tie":
            ties += 1
        else:
            losses += 1

    record = {"played": played, "wins": wins, "losses": losses, "ties": ties}
    if played:
        record.update(
            {
                "avg_score": total_score / played,
                "avg_opp_score": total_opp / played,
                "avg_margin": (total_score - total_opp) / played,
                "win_rate": wins / played,
            }
        )
    return record


async def match_team_numbers(
    session: AsyncSession, match: Match
) -> dict[str, list[int]]:
    result = await session.execute(
        select(MatchAlliance).where(MatchAlliance.match_id == match.id)
    )
    red: list[int] = []
    blue: list[int] = []
    for alliance in result.scalars().all():
        target = red if alliance.alliance_color == "red" else blue
        for key in alliance.team_keys or []:
            if key.startswith("frc"):
                target.append(int(key[3:]))
    return {"red": red, "blue": blue}


async def event_rankings_map(
    session: AsyncSession, event: Event
) -> dict[int, dict]:
    """Map team_number -> {rank, rp, ...} for an event."""
    result = await session.execute(
        select(EventRanking).where(EventRanking.event_id == event.id)
    )
    out = {}
    for r in result.scalars().all():
        out[r.team_number] = {
            "rank": r.rank,
            "rp": r.rp,
            "auto_points": r.autoplay_points,
            "teleop_points": r.teleop_points,
            "playoff_rp": r.playoff_rp,
        }
    return out


async def build_team_context(
    session: AsyncSession,
    team_number: int,
    event: Event | None = None,
    matches: list[Match] | None = None,
) -> dict:
    """Assemble a dict describing a team for the agent, from local DB data."""
    ctx: dict = await team_basic(session, team_number)
    ctx["season"] = event.season if event else None

    epa = await team_epa_profile(session, team_number, event.season if event else 2025)
    if epa.get("rows"):
        ctx["epa"] = {
            "overall": epa["avg_overall_epa"],
            "auto": epa["avg_auto_epa"],
            "teleop": epa["avg_teleop_epa"],
            "endgame": epa["avg_endgame_epa"],
        }

    if event is not None:
        rankings = await event_rankings_map(session, event)
        if team_number in rankings:
            ctx["event_rank"] = rankings[team_number]["rank"]
            ctx["event_rp"] = rankings[team_number]["rp"]
        ctx["event_record"] = await team_event_record(
            session, team_number, event, matches=matches
        )
    return ctx


async def build_event_teams_context(
    session: AsyncSession,
    event: Event,
    team_numbers: list[int] | None = None,
) -> dict[int, dict]:
    """Assemble lightweight team context for every team at an event."""
    result = await session.execute(select(Match).where(Match.event_id == event.id))
    matches = list(result.scalars().all())
    rankings = await event_rankings_map(session, event)

    team_list = team_numbers or sorted(rankings.keys())
    contexts = {}
    for team_number in team_list:
        ctx: dict = await team_basic(session, team_number)
        ctx["season"] = event.season
        epa = await team_epa_profile(session, team_number, event.season)
        if epa.get("rows"):
            ctx["epa"] = {
                "overall": _fmt(epa["avg_overall_epa"]),
                "auto": _fmt(epa["avg_auto_epa"]),
                "teleop": _fmt(epa["avg_teleop_epa"]),
                "endgame": _fmt(epa["avg_endgame_epa"]),
            }
        if team_number in rankings:
            ctx["event_rank"] = rankings[team_number]["rank"]
        ctx["event_record"] = await team_event_record(
            session, team_number, event, matches=matches
        )
        contexts[team_number] = ctx
    return contexts