"""Prediction strategies for the historical match replay system."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

BASE_SCORE_OFFSET = 25.0
SCORE_TEMPERATURE = 25.0
FORM_WEIGHT = 0.3


@dataclass
class TeamForm:
    """Point-in-time form for a team, accumulated from prior matches only."""

    team_number: int
    matches_played: int = 0
    wins: int = 0
    total_alliance_score: float = 0.0
    total_opp_score: float = 0.0

    @property
    def avg_alliance_score(self) -> float | None:
        if self.matches_played == 0:
            return None
        return self.total_alliance_score / self.matches_played

    @property
    def win_rate(self) -> float | None:
        if self.matches_played == 0:
            return None
        return self.wins / self.matches_played


@dataclass
class TeamEPA:
    team_number: int
    overall_epa: float | None = None
    auto_epa: float | None = None
    teleop_epa: float | None = None
    endgame_epa: float | None = None


@dataclass
class Prediction:
    strategy: str
    predicted_winner: str | None
    predicted_red_score: float | None
    predicted_blue_score: float | None
    predicted_red_prob: float | None
    features: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float | None:
        if self.predicted_red_prob is None:
            return None
        return max(self.predicted_red_prob, 1.0 - self.predicted_red_prob)


def _logistic_prob(margin: float, temperature: float = SCORE_TEMPERATURE) -> float:
    z = margin / temperature
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    return math.exp(z) / (1.0 + math.exp(z))


def _epa_sum(teams: list[TeamEPA]) -> float | None:
    values = [t.overall_epa for t in teams if t.overall_epa is not None]
    if len(values) == 0:
        return None
    return sum(values)


def predict_epa(
    red: list[TeamEPA],
    blue: list[TeamEPA],
    *,
    base: float = BASE_SCORE_OFFSET,
) -> Prediction:
    red_sum = _epa_sum(red)
    blue_sum = _epa_sum(blue)
    if red_sum is None or blue_sum is None:
        return Prediction(
            "epa",
            None,
            None,
            None,
            None,
            {"reason": "missing_epa", "red_epa": red_sum, "blue_epa": blue_sum},
        )
    red_score = red_sum + base
    blue_score = blue_sum + base
    prob = _logistic_prob(red_score - blue_score)
    if red_score > blue_score:
        winner = "red"
    elif blue_score > red_score:
        winner = "blue"
    else:
        winner = None
    return Prediction(
        "epa",
        winner,
        red_score,
        blue_score,
        prob,
        {"red_epa_sum": red_sum, "blue_epa_sum": blue_sum, "base": base},
    )


def predict_epa_form(
    red_epa: list[TeamEPA],
    blue_epa: list[TeamEPA],
    red_form: dict[int, TeamForm],
    blue_form: dict[int, TeamForm],
    *,
    base: float = BASE_SCORE_OFFSET,
    form_weight: float = FORM_WEIGHT,
) -> Prediction:
    red_sum = _epa_sum(red_epa)
    blue_sum = _epa_sum(blue_epa)

    def _form_score(teams: list[TeamEPA], forms: dict[int, TeamForm]) -> float | None:
        avgs = [
            forms[t.team_number].avg_alliance_score
            for t in teams
            if forms.get(t.team_number)
        ]
        avgs = [a for a in avgs if a is not None]
        if not avgs:
            return None
        return sum(avgs) / len(avgs)

    red_form_score = _form_score(red_epa, red_form)
    blue_form_score = _form_score(blue_epa, blue_form)

    if red_sum is None or blue_sum is None:
        return Prediction(
            "epa_form",
            None,
            None,
            None,
            None,
            {"reason": "missing_epa"},
        )

    red_epa_score = red_sum + base
    blue_epa_score = blue_sum + base

    if red_form_score is not None and blue_form_score is not None:
        red_score = form_weight * red_form_score + (1.0 - form_weight) * red_epa_score
        blue_score = (
            form_weight * blue_form_score + (1.0 - form_weight) * blue_epa_score
        )
    else:
        red_score = red_epa_score
        blue_score = blue_epa_score

    prob = _logistic_prob(red_score - blue_score)
    if red_score > blue_score:
        winner = "red"
    elif blue_score > red_score:
        winner = "blue"
    else:
        winner = None
    return Prediction(
        "epa_form",
        winner,
        red_score,
        blue_score,
        prob,
        {
            "red_epa_sum": red_sum,
            "blue_epa_sum": blue_sum,
            "red_form": red_form_score,
            "blue_form": blue_form_score,
            "base": base,
            "form_weight": form_weight,
        },
    )


def predict_statbotics(
    match_key: str,
    pred_winner: str | None,
    pred_red_score: float | None,
    pred_blue_score: float | None,
    pred_red_prob: float | None,
) -> Prediction:
    return Prediction(
        "statbotics",
        pred_winner,
        pred_red_score,
        pred_blue_score,
        pred_red_prob,
        {"match_key": match_key},
    )


STRATEGIES = {
    "epa": predict_epa,
    "epa_form": predict_epa_form,
    "statbotics": predict_statbotics,
}