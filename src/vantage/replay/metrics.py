"""Accuracy metrics for replay predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass

from vantage.replay.predictors import Prediction


@dataclass
class ReplayRecord:
    match_key: str
    competition_level: str
    match_number: int
    prediction: Prediction | None
    actual_winner: str | None
    actual_red_score: int | None
    actual_blue_score: int | None

    @property
    def correct(self) -> bool | None:
        if self.prediction is None or self.prediction.predicted_winner is None:
            return None
        if self.actual_winner is None:
            return None
        return self.prediction.predicted_winner == self.actual_winner

    @property
    def upset(self) -> bool | None:
        correct = self.correct
        if correct is None:
            return None
        return not correct

    @property
    def score_error(self) -> float | None:
        if (
            self.prediction is None
            or self.prediction.predicted_red_score is None
            or self.prediction.predicted_blue_score is None
            or self.actual_red_score is None
            or self.actual_blue_score is None
        ):
            return None
        return (
            abs(self.prediction.predicted_red_score - self.actual_red_score)
            + abs(self.prediction.predicted_blue_score - self.actual_blue_score)
        ) / 2.0


def _safe_log(x: float) -> float:
    return math.log(max(x, 1e-9))


def compute_metrics(
    records: list[ReplayRecord], include_level_breakdown: bool = True
) -> dict:
    total_matches = len(records)
    evaluated = [r for r in records if r.correct is not None]
    predicted_matches = len(evaluated)

    win_accuracy = None
    brier = None
    log_loss = None
    score_mae = None
    score_rmse = None
    upset_rate = None

    if predicted_matches:
        correct_count = sum(1 for r in evaluated if r.correct)
        win_accuracy = correct_count / predicted_matches

        probs = []
        for r in evaluated:
            if (
                r.prediction is not None
                and r.prediction.predicted_red_prob is not None
                and r.actual_winner in ("red", "blue")
            ):
                probs.append(r)
        if probs:
            brier = sum(
                (r.prediction.predicted_red_prob - int(r.actual_winner == "red")) ** 2
                for r in probs
            ) / len(probs)
            log_loss = -sum(
                int(r.actual_winner == "red")
                * _safe_log(r.prediction.predicted_red_prob)
                + int(r.actual_winner == "blue")
                * _safe_log(1.0 - r.prediction.predicted_red_prob)
                for r in probs
            ) / len(probs)

        errors = [r.score_error for r in evaluated if r.score_error is not None]
        if errors:
            score_mae = sum(errors) / len(errors)
            score_rmse = math.sqrt(sum(e**2 for e in errors) / len(errors))

        upsets = [r for r in evaluated if r.upset]
        upset_rate = len(upsets) / len(evaluated) if evaluated else None

    by_level: dict[str, dict] = {}
    if include_level_breakdown:
        for level in sorted({r.competition_level for r in records}):
            subset = [r for r in records if r.competition_level == level]
            sub_metrics = compute_metrics(subset, include_level_breakdown=False)
            by_level[level] = {
                "total": sub_metrics["total_matches"],
                "predicted": sub_metrics["predicted_matches"],
                "win_accuracy": sub_metrics["win_accuracy"],
                "upset_rate": sub_metrics["upset_rate"],
                "score_mae": sub_metrics["score_mae"],
            }

    detected = [r for r in records if r.prediction is not None]
    upset_detection_accuracy = None
    if detected:
        flagged = [
            r
            for r in detected
            if r.prediction.confidence is not None and r.prediction.confidence < 0.7
        ]
        if flagged:
            hits = [r for r in flagged if r.upset]
            upset_detection_accuracy = len(hits) / len(flagged)

    return {
        "total_matches": total_matches,
        "predicted_matches": predicted_matches,
        "win_accuracy": win_accuracy,
        "brier_score": brier,
        "log_loss": log_loss,
        "score_mae": score_mae,
        "score_rmse": score_rmse,
        "upset_rate": upset_rate,
        "upset_detection_accuracy": upset_detection_accuracy,
        "by_level": by_level,
    }