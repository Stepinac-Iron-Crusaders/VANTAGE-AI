# Vantage FRC — Phase 3: Gemini Scouting Agent

Phase 3 turns Vantage FRC into an **AI scouting copilot**. A single agent powered
by Google Gemini reads the local match/EPA database and produces structured,
persistable scouting intelligence:

- **Team dossiers** — auto/teleop/endgame profile, strengths, weaknesses, tier.
- **Alliance matchup advice** — Phase 2 EPA predictions + Gemini reasoning,
  upset risk, and on-field scouting notes.
- **Match observer** — per-team observations from completed matches.
- **Strategic hypotheses** — testable claims about how a team contributes, saved
  for future confirmation against real data.

## Setup

The agent needs a Gemini API key. It is read from `.env` (already configured, and
gitignored):

```dotenv
GEMINI_API_KEY=AIza...            # your Google Gemini API key
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_MODEL=gemini-3.6-flash     # current model; set to your available model
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_TOKENS=8192
```

Default request limits (free tier) apply; the client retries transient 429/5xx
errors with backoff.

## CLI (`scripts/phase3_cli.py`)

```
python scripts/phase3_cli.py init                         # ensure Phase 3 tables
python scripts/phase3_cli.py scout-team 27 --event 2025miket
python scripts/phase3_cli.py scout-event 2025miket --limit 3
python scripts/phase3_cli.py matchup 27,5150,494 5460,2137,4998 --event 2025miket
python scripts/phase3_cli.py observe 2025miket --limit 2   # only unobserved matches
python scripts/phase3_cli.py observations --limit 10       # latest observations
python scripts/phase3_cli.py hypotheses 27                 # stored hypotheses
python scripts/phase3_cli.py status                        # recent research records
```

## Package layout (`src/vantage/scout/`)

- `agent.py` — `VantageScout` facade: `scout_team`, `scout_event`,
  `analyze_matchup`, `observe_event`, `stored_research`, `nearby_teams`.
- `dossier.py` — `TeamDossier`, `ScoutingAgent` (dossier generation + persistence).
- `matchup.py` — `MatchupAdvisor` (EPA prediction + Gemini analysis).
- `observer.py` — `MatchObserver` + `filter_observations` (validates that every
  observation's team_number is actually in the match lineup).
- `hypotheses.py` — `HypothesisBuilder` (dossier → strategic hypotheses).
- `data.py` — assembles team/event context from the DB into prompt-ready dicts.
- `src/vantage/api/gemini_client.py` — async Gemini client with JSON-mode
  prompting, lenient JSON extraction, and rate-limit backoff.

## What gets persisted

- `research_records` — every dossier and matchup analysis (source, confidence,
  raw data).
- `hypotheses` — testable claims (category, confidence, evidence counters).
- `match_observations` — per-team observations from played matches
  (team_number is a FK; non-lineup teams are dropped).

## Validation

`python tests/test_phase3.py` (plus `test_phase1.py` / `test_phase2.py`) passes.
Tests cover JSON extraction, retry-hint parsing, dossier parsing, hypothesis
parsing, and the observation lineup filter — all offline (no API calls).