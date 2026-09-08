"""Async data queries for the Vantage web dashboard (pages + JSON API)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vantage.models.models import (
    EPAMetric,
    Event,
    EventRanking,
    Hypothesis,
    Match,
    MatchAlliance,
    MatchObservation,
    ReplayPrediction,
    ReplayRun,
    ResearchRecord,
    Team,
)


async def list_events(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Event).order_by(Event.season.desc(), Event.start_date.desc())
    )
    events = []
    for event in result.scalars().all():
        match_count = await session.scalar(
            select(func.count()).select_from(Match).where(Match.event_id == event.id)
        )
        events.append(
            {
                "event_code": event.event_code,
                "name": event.name,
                "season": event.season,
                "start_date": event.start_date,
                "match_count": match_count or 0,
            }
        )
    return events


async def get_event(session: AsyncSession, event_key: str) -> Event | None:
    result = await session.execute(select(Event).where(Event.event_code == event_key))
    return result.scalar_one_or_none()


async def event_rankings(
    session: AsyncSession, event: Event
) -> list[dict]:
    result = await session.execute(
        select(EventRanking)
        .options(selectinload(EventRanking.team))
        .where(EventRanking.event_id == event.id)
        .order_by(EventRanking.rank)
    )
    rankings = []
    for r in result.scalars().all():
        epa = await team_latest_epa(session, r.team_number, event.season)
        rankings.append(
            {
                "rank": r.rank,
                "team_number": r.team_number,
                "nickname": r.team.nickname if r.team else None,
                "rp": r.rp,
                "epa": epa,
            }
        )
    return rankings


async def team_latest_epa(
    session: AsyncSession, team_number: int, season: int
) -> EPAMetric | None:
    result = await session.execute(
        select(EPAMetric)
        .where(EPAMetric.team_number == team_number, EPAMetric.season == season)
        .order_by(EPAMetric.match_key.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def team_epa_series(
    session: AsyncSession, team_number: int, season: int
) -> list[dict]:
    result = await session.execute(
        select(EPAMetric)
        .where(EPAMetric.team_number == team_number, EPAMetric.season == season)
        .order_by(EPAMetric.match_key)
    )
    return [
        {
            "match_key": row.match_key,
            "overall_epa": row.overall_epa,
            "auto_epa": row.auto_epa,
            "teleop_epa": row.teleop_epa,
            "endgame_epa": row.endgame_epa,
        }
        for row in result.scalars().all()
    ]


async def team_event_record(
    session: AsyncSession, team_number: int, event: Event
) -> dict | None:
    result = await session.execute(select(Match).where(Match.event_id == event.id))
    wins = losses = ties = 0
    total_my = total_opp = 0.0
    played = 0
    for match in result.scalars().all():
        if match.winning_alliance is None or match.red_score is None:
            continue
        teams = await match_team_numbers(session, match)
        color = None
        if team_number in teams["red"]:
            color = "red"
        elif team_number in teams["blue"]:
            color = "blue"
        if color is None:
            continue
        my = match.red_score if color == "red" else match.blue_score
        opp = match.blue_score if color == "red" else match.red_score
        played += 1
        total_my += my
        total_opp += opp
        if match.winning_alliance == color:
            wins += 1
        elif match.winning_alliance == "tie":
            ties += 1
        else:
            losses += 1
    if played == 0:
        return None
    return {
        "played": played,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / played,
        "avg_score": total_my / played,
        "avg_opp_score": total_opp / played,
        "avg_margin": (total_my - total_opp) / played,
    }


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


async def event_matches(session: AsyncSession, event: Event) -> list[dict]:
    result = await session.execute(
        select(Match)
        .where(Match.event_id == event.id)
        .order_by(Match.actual_time, Match.competition_level, Match.match_number)
    )
    matches = []
    for match in result.scalars().all():
        teams = await match_team_numbers(session, match)
        matches.append(
            {
                "key": match.key,
                "competition_level": match.competition_level,
                "set_number": match.set_number,
                "match_number": match.match_number,
                "status": match.status,
                "red_teams": teams["red"],
                "blue_teams": teams["blue"],
                "red_score": match.red_score,
                "blue_score": match.blue_score,
                "winning_alliance": match.winning_alliance,
                "actual_time": match.actual_time,
            }
        )
    return matches


async def replay_runs(
    session: AsyncSession, event_key: str | None = None
) -> list[dict]:
    query = select(ReplayRun).order_by(ReplayRun.created_at.desc())
    if event_key:
        query = query.where(ReplayRun.event_key == event_key)
    result = await session.execute(query)
    return [
        {
            "id": row.id,
            "event_key": row.event_key,
            "strategy": row.strategy,
            "status": row.status,
            "total_matches": row.total_matches,
            "predicted_matches": row.predicted_matches,
            "win_accuracy": row.win_accuracy,
            "brier_score": row.brier_score,
            "log_loss": row.log_loss,
            "score_mae": row.score_mae,
            "score_rmse": row.score_rmse,
            "created_at": row.created_at,
        }
        for row in result.scalars().all()
    ]


async def replay_predictions(session: AsyncSession, run_id: str) -> list[dict]:
    result = await session.execute(
        select(ReplayPrediction)
        .where(ReplayPrediction.run_id == run_id)
        .order_by(ReplayPrediction.competition_level, ReplayPrediction.match_number)
    )
    return [r for r in result.scalars().all()]


async def research_records(
    session: AsyncSession, info_type: str | None = None, limit: int = 100
) -> list[ResearchRecord]:
    query = select(ResearchRecord).order_by(ResearchRecord.created_at.desc())
    if info_type:
        query = query.where(ResearchRecord.info_type == info_type)
    query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def hypotheses(
    session: AsyncSession, status: str | None = None, limit: int = 200
) -> list[Hypothesis]:
    query = select(Hypothesis).order_by(Hypothesis.created_at.desc())
    if status:
        query = query.where(Hypothesis.status == status)
    query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def observations(
    session: AsyncSession, limit: int = 100
) -> list[MatchObservation]:
    result = await session.execute(
        select(MatchObservation)
        .order_by(MatchObservation.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_team(session: AsyncSession, team_number: int) -> Team | None:
    result = await session.execute(select(Team).where(Team.team_number == team_number))
    return result.scalar_one_or_none()


async def dashboard_stats(session: AsyncSession) -> dict:
    team_count = await session.scalar(select(func.count()).select_from(Team))
    event_count = await session.scalar(select(func.count()).select_from(Event))
    match_count = await session.scalar(select(func.count()).select_from(Match))
    epa_count = await session.scalar(select(func.count()).select_from(EPAMetric))
    run_count = await session.scalar(select(func.count()).select_from(ReplayRun))
    hypo_count = await session.scalar(select(func.count()).select_from(Hypothesis))
    obs_count = await session.scalar(
        select(func.count()).select_from(MatchObservation)
    )
    return {
        "teams": team_count or 0,
        "events": event_count or 0,
        "matches": match_count or 0,
        "epa_rows": epa_count or 0,
        "replay_runs": run_count or 0,
        "hypotheses": hypo_count or 0,
        "observations": obs_count or 0,
    }