"""Point-in-time feature accumulation for the replay engine."""

from __future__ import annotations

from vantage.replay.predictors import TeamForm


class FormTracker:
    """Tracks per-team form using only matches already played in the replay."""

    def __init__(self) -> None:
        self._forms: dict[int, TeamForm] = {}

    def get(self, team_number: int) -> TeamForm | None:
        return self._forms.get(team_number)

    def forms_for(self, team_numbers: list[int]) -> dict[int, TeamForm]:
        return {n: self._forms[n] for n in team_numbers if n in self._forms}

    def record(
        self,
        team_numbers: list[int],
        alliance_score: int | None,
        opponent_score: int | None,
    ) -> None:
        if alliance_score is None or opponent_score is None:
            return
        won = alliance_score > opponent_score
        for team_number in team_numbers:
            form = self._forms.setdefault(
                team_number, TeamForm(team_number=team_number)
            )
            form.matches_played += 1
            if won:
                form.wins += 1
            form.total_alliance_score += alliance_score
            form.total_opp_score += opponent_score