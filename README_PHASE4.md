# Vantage FRC — Phase 4: Web Dashboard

Phase 4 wraps Phases 1–3 in a **FastAPI dashboard**: browse events, rankings,
team dossiers, historical replay metrics, scouting research, hypotheses, and the
AI matchup advisor — all in the browser, plus a JSON API for automation.

## Run it

```
python scripts/phase4_cli.py init      # ensure all tables (matches Phase 1 init)
python scripts/phase4_cli.py serve     # uvicorn on http://127.0.0.1:8000
# or:
python -m uvicorn vantage.web.app:app --port 8000
```

`python scripts/phase4_cli.py init` can be used from anywhere; the server reads
`.env` for the Gemini key, which is only needed if you tick **Use Gemini AI** on
the matchup page (kept separate from the instant EPA-only prediction).

## Pages

| Route                | What it shows                                        |
| -------------------- | ---------------------------------------------------- |
| `/`                  | Dashboard: counts, latest matches, recent research   |
| `/events`            | Ingested events                                      |
| `/events/{key}`      | Match list + rankings table                          |
| `/teams/{num}`       | Team EPA splits (auto/teleop/endgame), record        |
| `/replay`            | Historical replay runs (Phase 2)                     |
| `/replay/{run_id}`   | Per-match predicted vs actual + accuracy metrics     |
| `/scouting`          | All research_records (dossiers + matchup analyses)   |
| `/hypotheses`        | Stored strategic hypotheses (Phase 3)                |
| `/observations`      | Match observations (Phase 3)                         |
| `/matchup`           | EPA-only prediction instantly; Gemini analysis via checkbox |

## JSON API

| Method | Route                          | Notes                              |
| ------ | ------------------------------ | ---------------------------------- |
| GET    | `/api/health`                  | service check                      |
| GET    | `/api/events`                  | list events                        |
| GET    | `/api/events/{key}/rankings`   | finalized rankings                 |
| GET    | `/api/teams/{num}?season=2025` | team summary + latest EPA          |
| GET    | `/api/replay/runs`             | previous replay runs               |
| POST   | `/api/matchup/predict`         | `{red_teams, blue_teams, season, event_key, with_gemini}` |
| GET    | `/api/research`                | scouting research records          |

Example prediction request (no Gemini, instant):

```json
{"red_teams": [27, 5150, 494], "blue_teams": [5460, 2137, 4998],
 "season": 2025, "event_key": "2025miket", "with_gemini": false}
```

Response: `predicted_winner`, `predicted_red_score`, `predicted_blue_score`,
`predicted_red_prob`, `confidence`, and per-team `epas` (overall/auto/teleop/
endgame).

## Layout (`src/vantage/web/`)

- `app.py` — FastAPI app factory + lifespan (init/close DB pool).
- `pages.py` — server-rendered HTML routes (Jinja2).
- `api.py` — JSON endpoints (reads the same `data.py` queries).
- `data.py` — async SQLAlchemy 2.0 queries used by both pages and API.
- `deps.py` — shared `get_db` dependency + template helpers (`pct`, `f1`).
- `templates/`, `static/styles.css` — dark dash theme.

The whole dashboard is read-only; ingestion and AI research still run through the
Phase 1–3 CLIs (`scripts/phase1_cli.py`, `scripts/phase3_cli.py`).

## Validation

`python tests/test_phase4.py` passes alongside `test_phase1.py`, `test_phase2.py`,
and `test_phase3.py`. Tests cover app import, all page routes, the matchup form +
API prediction, and the JSON API — offline (no Gemini calls).