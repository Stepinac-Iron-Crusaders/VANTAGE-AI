"""Validation tests for Phase 2: Historical Match Replay System."""

import asyncio
import sys


async def validate_imports():
    errors = []

    try:
        from vantage.replay.engine import ReplayEngine  # noqa: F401
        from vantage.replay.features import FormTracker, TeamForm  # noqa: F401
        from vantage.replay.metrics import ReplayRecord, compute_metrics  # noqa: F401
        from vantage.replay.predictors import (  # noqa: F401
            STRATEGIES,
            predict_epa,
            predict_epa_form,
        )
        from vantage.replay.report import format_replay_summary  # noqa: F401
        print("[OK] replay package")
    except Exception as e:
        errors.append(f"replay package: {e!r}")

    try:
        from vantage.models.models import ReplayPrediction, ReplayRun  # noqa: F401
        print("[OK] replay models")
    except Exception as e:
        errors.append(f"replay models: {e!r}")

    try:
        from vantage.api.statbotics_client import StatboticsMatchEPA
        fields = StatboticsMatchEPA.model_fields
        assert "pred_winner" in fields, "pred_winner missing"
        assert "pred_red_score" in fields, "pred_red_score missing"
        assert "pred_blue_score" in fields, "pred_blue_score missing"
        assert "pred_red_prob" in fields, "pred_red_prob missing"
        print("[OK] statbotics pred fields")
    except Exception as e:
        errors.append(f"statbotics pred fields: {e!r}")

    if errors:
        print("\n[FAIL]:")
        for err in errors:
            print(f"  - {err}")
        return False
    print("\n[PASS] All imports successful")
    return True


def _team_epa(team, epa, auto=None, teleop=None, end=None):
    from vantage.replay.predictors import TeamEPA
    return TeamEPA(
        team_number=team,
        overall_epa=epa,
        auto_epa=auto or epa * 0.2,
        teleop_epa=teleop if teleop is not None else epa * 0.5,
        endgame_epa=end or epa * 0.3,
    )


async def validate_predictors():
    from vantage.replay.predictors import TeamForm, predict_epa, predict_epa_form

    red = [_team_epa(1, 30.0), _team_epa(2, 28.0), _team_epa(3, 25.0)]
    blue = [_team_epa(4, 20.0), _team_epa(5, 18.0), _team_epa(6, 15.0)]

    pred = predict_epa(red, blue)
    assert pred.predicted_winner == "red", pred
    assert pred.predicted_red_score > pred.predicted_blue_score
    assert pred.predicted_red_prob > 0.5
    assert pred.confidence

    pred2 = predict_epa(blue, red)
    assert pred2.predicted_winner == "blue"

    def tf(num: int, wins: int, as_: int, os: int) -> TeamForm:
        return TeamForm(
            num,
            matches_played=10,
            wins=wins,
            total_alliance_score=as_,
            total_opp_score=os,
        )

    red_form = {1: tf(1, 9, 900, 700)}
    blue_form = {4: tf(4, 2, 400, 900), 5: tf(5, 3, 500, 800), 6: tf(6, 1, 300, 900)}
    mixed = predict_epa_form(red, blue, red_form, blue_form)
    assert mixed.predicted_winner == "red"
    assert mixed.predicted_red_score > mixed.predicted_blue_score
    assert "red_form" in mixed.features

    print("[OK] predictors (epa, epa_form)")
    return True


async def validate_metrics():
    from vantage.replay.metrics import ReplayRecord, compute_metrics
    from vantage.replay.predictors import Prediction

    records = []

    def add(
        match_key, level, num, pred_winner, pred_red, pred_blue, prob,
        act_winner, act_red, act_blue,
    ):
        rec = ReplayRecord(
            match_key=match_key,
            competition_level=level,
            match_number=num,
            prediction=Prediction(
                strategy="epa",
                predicted_winner=pred_winner,
                predicted_red_score=pred_red,
                predicted_blue_score=pred_blue,
                predicted_red_prob=prob,
            ),
            actual_winner=act_winner,
            actual_red_score=act_red,
            actual_blue_score=act_blue,
        )
        records.append(rec)

    add("e1_qm1", "qm", 1, "red", 100, 80, 0.8, "red", 95, 90)
    add("e1_qm2", "qm", 2, "red", 100, 80, 0.8, "blue", 70, 110)
    add("e1_qm3", "qm", 3, "red", 100, 80, 0.8, "red", 105, 85)
    add("e1_qm4", "qm", 4, "red", 100, 80, 0.8, "blue", 60, 120)

    metrics = compute_metrics(records)

    assert metrics["total_matches"] == 4
    assert metrics["predicted_matches"] == 4
    assert metrics["win_accuracy"] == 0.5
    assert metrics["score_mae"] == 20.625
    assert metrics["upset_rate"] == 0.5
    assert "qm" in metrics["by_level"]
    assert metrics["log_loss"] is not None
    assert metrics["brier_score"] is not None
    print("[OK] metrics (accuracy, MAE, brier, log loss, by-level)")
    return True


async def validate_form_tracker():
    from vantage.replay.features import FormTracker

    tracker = FormTracker()
    tracker.record([1, 2, 3], 100, 80)
    tracker.record([1, 2, 3], 90, 95)
    tracker.record([4, 5, 6], 120, 60)

    t1 = tracker.get(1)
    assert t1.matches_played == 2
    assert t1.wins == 1
    assert t1.avg_alliance_score == 95.0
    assert not tracker.get(99)
    print("[OK] form tracker (point-in-time features)")
    return True


async def validate_tables():
    from vantage.models.models import Base

    tables = sorted(Base.metadata.tables.keys())
    for expected in ["replay_runs", "replay_predictions"]:
        assert expected in tables, f"{expected} missing"
    print("[OK] replay tables registered")
    return True


async def main():
    print("=" * 50)
    print("Vantage FRC Phase 2 Validation")
    print("=" * 50)

    checks = [
        await validate_imports(),
        await validate_predictors(),
        await validate_metrics(),
        await validate_form_tracker(),
        await validate_tables(),
    ]

    print("\n" + "=" * 50)
    if all(checks):
        print("Phase 2 validation: PASSED")
        sys.exit(0)
    else:
        print("Phase 2 validation: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())