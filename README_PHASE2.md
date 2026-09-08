# Vantage FRC — Phase 2: Historical Match Replay System

Phase 2 builds on the Phase 1 database/data pipeline to add an **offline match
replay harness** that measures how well different prediction strategies would
have performed on a historical event, using **only information available before
each match** (no look-ahead / no leakage).

## What it does

Given an event (e.g. `2025miket`), the replay engine:

1. Loads all matches for the event, ordered chronologically
   (`actual_time` / `predicted_time`, with playoff level tie-breaking
   `qm < ef < qf < sf < f`).
2. For each match, reads each team's EPA (and, for the `epa_form` strategy,
   each team's rolling point-in-time form built from prior matches only).
3. Builds a prediction of the winner and both alliance scores.
4. Records a `ReplayPrediction` row comparing predicted vs actual.
5. Aggregates metrics (win accuracy, score MAE/RMSE, Brier score, log loss,
   upset rate & detection, per-competition-level breakdown).

Three prediction strategies are supported (see `STRATEGIES`):

| strategy      | description                                                        |
|---------------|--------------------------------------------------------------------|
| `epa`         | Time-weighted sum of each team's overall EPA leads a win + score model using a sigmoid over the EPA gap (temperature `SCORE_TEMPERATURE`, baseline `BASE_SCORE_OFFSET`). |
| `epa_form`    | Blends the EPA-based score with each team's recent form (win rate + average alliance score, weight `FORM_WEIGHT`). |
| `statbotics`  | Uses Statbotics' own per-match prediction (`pred` block: winner, red/blue score, red win probability). |

## Database tables (new in Phase 2)

- `replay_runs` — one row per replay execution (event, strategy, timestamps, and
  a JSON `metrics` blob).
- `replay_predictions` — one row per match per run (match key, predicted/actual
  winner & scores, predicted red-win probability, correct flag, upset flag,
  score error, raw features).

Added to existing tables: `matches.key` (backfilled), and `epa_metrics` gained
`pred_winner`, `pred_red_score`, `pred_blue_score`, `pred_red_prob` columns
parsed from the Statbotics match prediction.

## CLI (`scripts/phase2_cli.py`)

```
python scripts/phase2_cli.py init                 # ensure replay tables exist
python scripts/phase2_cli.py ingest-epa 2025miket # backfill/match EPA for an event
python scripts/phase2_cli.py replay 2025miket     # run all strategies (--strategy epa to pick one)
python scripts/phase2_cli.py runs 2025miket       # list saved runs
python scripts/phase2_cli.py run <run_id>         # full summary + predictions detail
```

## Package layout (`src/vantage/replay/`)

- `engine.py` — `ReplayEngine`: chronological ordering, per-match prediction,
  persistence of runs & predictions.
- `predictors.py` — `TeamForm`, `TeamEPA`, `Prediction`, and the three
  `predict_*` functions + tuning constants.
- `features.py` — `FormTracker`: point-in-time form accumulation (prevents
  look-ahead).
- `metrics.py` — `ReplayRecord`, `compute_metrics` (incl. level breakdown).
- `report.py` — text formatters for the CLI.

## Validation

`python tests/test_phase2.py` and `python tests/test_phase1.py` both pass.

### Reference results — `2025miket` (95 matches)

| strategy    | predicted | win acc | score MAE | RMSE | Brier | log loss |
|-------------|-----------|---------|-----------|------|-------|----------|
| `epa`       | 95/95     | 91.6%   | 18.67     | 21.22| 0.12  | 0.40     |
| `epa_form`  | 95/95     | 91.6%   | 16.54     | 19.23| 0.13  | 0.44     |
| `statbotics`| 95/95     | 85.3%   | 17.29     | 19.88| 0.14  | 0.46     |

Per-level breakdowns (e.g. qm 80 / sf 13 / f 2) are printed by the CLI and
stored in each run's metrics.

> Phase 2 is committed and pushed to GitHub
> (`https://github.com/Stepinac-Iron-Crusaders/VANTAGE-AI`).
