"""JSON API endpoints for the Vantage web dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.replay.predictors import TeamEPA, predict_epa
from vantage.scout.matchup import MatchupAdvisor
from vantage.web import data as db
from vantage.web.deps import get_db

router = APIRouter(tags=["api"])

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def _team_epa_dict(obj) -> dict:
    return {
        "team_number": obj.team_number,
        "overall_epa": obj.overall_epa,
        "auto_epa": obj.auto_epa,
        "teleop_epa": obj.teleop_epa,
        "endgame_epa": obj.endgame_epa,
    }


def _research_to_dict(r) -> dict:
    return {
        "family": str(r.id),
        "team_number": r.team_number,
        "source": r.source,
        "title": r.title,
        "content_summary": r.content_summary,
        "info_type": r.info_type,
        "confidence": r.confidence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/events")
async def api_events(db_session: SessionDep):
    return await db.list_events(db_session)


@router.get("/api/events/{event_key}/rankings")
async def api_event_rankings(
    event_key: str, db_session: SessionDep
):
    event = await db.get_event(db_session, event_key)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return await db.event_rankings(db_session, event)


@router.get("/api/teams/{team_number}")
async def api_team(
    team_number: int,
    db_session: SessionDep,
    season: int = 2025,
):
    team = await db.get_team(db_session, team_number)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    epa = await db.team_latest_epa(db_session, team_number, season)
    series = await db.team_epa_series(db_session, team_number, season)
    return {
        "team_number": team.team_number,
        "name": team.name,
        "nickname": team.nickname,
        "location": team.location,
        "rookies_year": team.rookies_year,
        "epa": _team_epa_dict(epa) if epa else None,
        "epa_series": series,
    }


@router.get("/api/replay/runs")
async def api_replay_runs(
    db_session: SessionDep, event_key: str | None = None
):
    return await db.replay_runs(db_session, event_key)


@router.post("/api/matchup/predict")
async def api_matchup_predict(
    payload: Annotated[dict, Body(...)],
    db_session: SessionDep,
):
    red_teams = [int(x) for x in payload.get("red_teams", [])]
    blue_teams = [int(x) for x in payload.get("blue_teams", [])]
    season = int(payload.get("season", 2025))
    event_key = payload.get("event_key")
    if not red_teams or not blue_teams:
        raise HTTPException(status_code=400, detail="red_teams and blue_teams required")

    epas: dict[int, TeamEPA] = {}
    for team_number in red_teams + blue_teams:
        obj = await db.team_latest_epa(db_session, team_number, season)
        epas[team_number] = TeamEPA(
            team_number=team_number,
            overall_epa=obj.overall_epa if obj else None,
            auto_epa=obj.auto_epa if obj else None,
            teleop_epa=obj.teleop_epa if obj else None,
            endgame_epa=obj.endgame_epa if obj else None,
        )
    pred = predict_epa([epas[t] for t in red_teams], [epas[t] for t in blue_teams])

    response = {
        "predicted_winner": pred.predicted_winner,
        "predicted_red_score": pred.predicted_red_score,
        "predicted_blue_score": pred.predicted_blue_score,
        "predicted_red_prob": pred.predicted_red_prob,
        "confidence": pred.confidence,
        "epas": {str(t): _team_epa_dict(e) for t, e in epas.items()},
    }

    if payload.get("with_gemini"):
        advisor = MatchupAdvisor(db_session, season=season, event_key=event_key)
        analysis = await advisor.analyze(red_teams, blue_teams, event_key)
        response["reasoning"] = analysis.model_reasoning
        response["upset_risk"] = analysis.upset_risk
        response["scouting_notes"] = analysis.scouting_notes
    return response


@router.get("/api/research")
async def api_research(
    db_session: SessionDep,
    info_type: str | None = None,
    limit: int = 50,
):
    records = await db.research_records(db_session, info_type=info_type, limit=limit)
    return [_research_to_dict(r) for r in records]