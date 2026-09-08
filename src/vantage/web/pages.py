"""Server-rendered pages for the Vantage FRC dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.replay.predictors import TeamEPA, predict_epa
from vantage.scout.matchup import MatchupAdvisor
from vantage.web import data as db
from vantage.web.deps import get_db, render

router = APIRouter(include_in_schema=False)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db_session: SessionDep):
    stats = await db.dashboard_stats(db_session)
    events = await db.list_events(db_session)
    runs = await db.replay_runs(db_session)
    research = await db.research_records(db_session, limit=8)
    return render(
        request,
        "index.html",
        {"stats": stats, "events": events, "runs": runs, "research": research},
    )


@router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, db_session: SessionDep):
    events = await db.list_events(db_session)
    return render(request, "events.html", {"events": events})


@router.get("/events/{event_key}", response_class=HTMLResponse)
async def event_detail(
    request: Request,
    event_key: str,
    db_session: SessionDep,
):
    event = await db.get_event(db_session, event_key)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_key} not found")
    rankings = await db.event_rankings(db_session, event)
    matches = await db.event_matches(db_session, event)
    runs = await db.replay_runs(db_session, event_key)
    return render(
        request,
        "event.html",
        {
            "event": event,
            "rankings": rankings,
            "matches": matches,
            "runs": runs,
        },
    )


@router.get("/teams/{team_number}", response_class=HTMLResponse)
async def team_detail(
    request: Request,
    team_number: int,
    db_session: SessionDep,
    season: Annotated[int, Query()] = 2025,
):
    team = await db.get_team(db_session, team_number)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_number} not found")
    epa = await db.team_latest_epa(db_session, team_number, season)
    epa_series = await db.team_epa_series(db_session, team_number, season)
    events = await db.list_events(db_session)

    event = None
    record = None
    for ev in events:
        if ev["season"] == season:
            obj = await db.get_event(db_session, ev["event_code"])
            record = await db.team_event_record(db_session, team_number, obj)
            if record:
                event = obj
                break

    dossiers = await db.research_records(db_session, limit=50)
    team_dossiers = [r for r in dossiers if r.team_number == team_number]
    hypos = await db.hypotheses(db_session, limit=200)
    team_hypos = [h for h in hypos if h.team_number == team_number]
    obs = await db.observations(db_session, limit=200)
    team_obs = [o for o in obs if o.team_number == team_number]

    return render(
        request,
        "team.html",
        {
            "team": team,
            "season": season,
            "epa": epa,
            "epa_series": epa_series,
            "record": record,
            "event": event,
            "dossiers": team_dossiers,
            "hypotheses": team_hypos,
            "observations": team_obs,
        },
    )


@router.get("/replay", response_class=HTMLResponse)
async def replay_page(request: Request, db_session: SessionDep):
    runs = await db.replay_runs(db_session)
    return render(request, "replay.html", {"runs": runs})


@router.get("/replay/{run_id}", response_class=HTMLResponse)
async def replay_run_detail(
    request: Request, run_id: str, db_session: SessionDep
):
    runs = await db.replay_runs(db_session)
    run = next((r for r in runs if str(r["id"]) == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    predictions = await db.replay_predictions(db_session, run_id)
    return render(
        request,
        "run.html",
        {"run": run, "predictions": predictions},
    )


@router.get("/scouting", response_class=HTMLResponse)
async def scouting_page(
    request: Request,
    db_session: SessionDep,
    info_type: Annotated[str | None, Query()] = None,
):
    records = await db.research_records(db_session, info_type=info_type, limit=200)
    return render(
        request,
        "scouting.html",
        {"records": records, "selected_type": info_type},
    )


@router.get("/hypotheses", response_class=HTMLResponse)
async def hypotheses_page(
    request: Request,
    db_session: SessionDep,
    status: Annotated[str | None, Query()] = None,
):
    items = await db.hypotheses(db_session, status=status, limit=300)
    return render(request, "hypotheses.html", {"items": items, "status": status})


@router.get("/observations", response_class=HTMLResponse)
async def observations_page(
    request: Request, db_session: SessionDep
):
    items = await db.observations(db_session, limit=200)
    return render(request, "observations.html", {"items": items})


async def _matchup_form_data(
    session: AsyncSession, event_key: str | None = None
) -> dict:
    events = await db.list_events(session)
    rankings = []
    if events:
        key = event_key or events[0]["event_code"]
        event = await db.get_event(session, key)
        if event:
            rankings = await db.event_rankings(session, event)
    return {"events": events, "rankings": rankings, "selected_event": event_key}


@router.get("/matchup", response_class=HTMLResponse)
async def matchup_form(request: Request, db_session: SessionDep):
    ctx = await _matchup_form_data(db_session)
    return render(request, "matchup.html", ctx | {"result": None})


async def _compute_prediction(
    session: AsyncSession,
    red_teams: list[int],
    blue_teams: list[int],
    event: object | None,
    with_gemini: bool,
    season: int,
) -> dict:
    event_key = event.event_code if event else None
    epas = {}
    for team_number in red_teams + blue_teams:
        obj = await db.team_latest_epa(session, team_number, season)
        epas[team_number] = TeamEPA(
            team_number=team_number,
            overall_epa=obj.overall_epa if obj else None,
            auto_epa=obj.auto_epa if obj else None,
            teleop_epa=obj.teleop_epa if obj else None,
            endgame_epa=obj.endgame_epa if obj else None,
        )
    red = [epas[t] for t in red_teams]
    blue = [epas[t] for t in blue_teams]
    pred = predict_epa(red, blue)

    result = {
        "red_teams": red_teams,
        "blue_teams": blue_teams,
        "predicted_winner": pred.predicted_winner,
        "predicted_red_score": pred.predicted_red_score,
        "predicted_blue_score": pred.predicted_blue_score,
        "predicted_red_prob": pred.predicted_red_prob,
        "confidence": pred.confidence,
        "epas": {str(t): e for t, e in epas.items()},
        "reasoning": None,
        "upset_risk": None,
        "scouting_notes": [],
    }

    if with_gemini:
        advisor = MatchupAdvisor(session, season=season, event_key=event_key)
        analysis = await advisor.analyze(red_teams, blue_teams, event_key)
        result["predicted_winner"] = analysis.predicted_winner
        result["predicted_red_score"] = analysis.predicted_red_score
        result["predicted_blue_score"] = analysis.predicted_blue_score
        result["confidence"] = analysis.prediction_confidence
        result["reasoning"] = analysis.model_reasoning
        result["upset_risk"] = analysis.upset_risk
        result["scouting_notes"] = analysis.scouting_notes
    return result


@router.post("/matchup", response_class=HTMLResponse)
async def matchup_analyze(
    request: Request,
    event_key: Annotated[str, Form()],
    red_teams: Annotated[str, Form()],
    blue_teams: Annotated[str, Form()],
    db_session: SessionDep,
    with_gemini: Annotated[str, Form()] = "",
    season: Annotated[int, Form()] = 2025,
):
    def parse(s: str) -> list[int]:
        return [int(x) for x in s.replace(" ", "").split(",") if x.strip()]

    red = parse(red_teams)
    blue = parse(blue_teams)
    if len(red) == 0 or len(blue) == 0:
        detail = "Enter at least one team per alliance"
        raise HTTPException(status_code=400, detail=detail)

    event = await db.get_event(db_session, event_key) if event_key else None
    result = await _compute_prediction(
        db_session, red, blue, event, with_gemini == "on", season
    )
    ctx = await _matchup_form_data(db_session, event_key)
    ctx["result"] = result
    return render(request, "matchup.html", ctx)