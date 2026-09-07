"""Historical match replay engine: replay an event in chronological order and
measure prediction accuracy using only information available before each match."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vantage.db.session import get_session
from vantage.models.models import (
    EPAMetric,
    Event,
    Match,
    MatchAlliance,
    ReplayPrediction,
    ReplayRun,
)
from vantage.replay.features import FormTracker
from vantage.replay.metrics import ReplayRecord, compute_metrics
from vantage.replay.predictors import (
    STRATEGIES,
    Prediction,
    TeamEPA,
    predict_epa_form,
    predict_statbotics,
)

logger = structlog.get_logger(__name__)

COMP_LEVEL_ORDER = {"qm": 0, "ef": 1, "qf": 2, "sf": 3, "f": 4}


class _NoPrediction:
    predicted_winner = None
    predicted_red_score = None
    predicted_blue_score = None
    predicted_red_prob = None


class ReplayEngine:
    def __init__(self, strategy: str = "epa"):
        if strategy not in STRATEGIES:
            choices = ", ".join(sorted(STRATEGIES))
            raise ValueError(f"Unknown strategy '{strategy}'. Choose from {choices}")
        self.strategy = strategy

    async def replay_event(
        self, event_key: str, persist: bool = True
    ) -> ReplayRun | None:
        async with get_session() as session:
            event = await self._load_event(session, event_key)
            if not event:
                logger.warning("event not found", event_key=event_key)
                return None

            matches = self._order_matches(await self._load_matches(session, event))
            tracker = FormTracker()
            records: list[ReplayRecord] = []
            stored: list[
                tuple[Match, list[int], list[int], str | None, Prediction | None]
            ] = []

            for match in matches:
                red, blue = await self._load_alliances(session, match)
                red_epas, blue_epas, statbotics_pred = await self._load_match_features(
                    session, match.key, red, blue
                )
                prediction = self._build_prediction(
                    match, red_epas, blue_epas, tracker, statbotics_pred
                )

                record = ReplayRecord(
                    match_key=match.key,
                    competition_level=match.competition_level,
                    match_number=match.match_number,
                    prediction=prediction,
                    actual_winner=match.winning_alliance,
                    actual_red_score=match.red_score,
                    actual_blue_score=match.blue_score,
                )
                records.append(record)
                stored.append((match, red, blue, match.winning_alliance, prediction))

                tracker.record(red, match.red_score, match.blue_score)
                tracker.record(blue, match.blue_score, match.red_score)

            metrics = compute_metrics(records)
            logger.info(
                "replay complete",
                event_key=event_key,
                strategy=self.strategy,
                total_matches=metrics["total_matches"],
                predicted_matches=metrics["predicted_matches"],
                win_accuracy=metrics["win_accuracy"],
                score_mae=metrics["score_mae"],
            )

            if not persist:
                return self._build_run(event_key, self.strategy, metrics)

            run = self._build_run(event_key, self.strategy, metrics)
            session.add(run)
            await session.flush()

            records_by_key = {r.match_key: r for r in records}
            for match, red, blue, actual_winner, prediction in stored:
                record = records_by_key[match.key]
                pred_val = prediction or _NoPrediction()
                session.add(
                    ReplayPrediction(
                        run_id=run.id,
                        match_key=match.key,
                        competition_level=match.competition_level,
                        match_number=match.match_number,
                        predicted_winner=pred_val.predicted_winner,
                        predicted_red_score=pred_val.predicted_red_score,
                        predicted_blue_score=pred_val.predicted_blue_score,
                        predicted_red_prob=pred_val.predicted_red_prob,
                        actual_winner=actual_winner,
                        actual_red_score=match.red_score,
                        actual_blue_score=match.blue_score,
                        correct=record.correct,
                        upset=record.upset,
                        score_error=record.score_error,
                        raw_data={
                            "red_teams": red,
                            "blue_teams": blue,
                            "strategy": self.strategy,
                            "features": prediction.features if prediction else {},
                        },
                    )
                )

            return run

    async def _load_event(
        self, session: AsyncSession, event_key: str
    ) -> Event | None:
        result = await session.execute(
            select(Event).where(Event.event_code == event_key)
        )
        return result.scalar_one_or_none()

    async def _load_matches(self, session: AsyncSession, event: Event) -> list[Match]:
        result = await session.execute(select(Match).where(Match.event_id == event.id))
        return list(result.scalars().all())

    @staticmethod
    def _order_matches(matches: list[Match]) -> list[Match]:
        def sort_key(match: Match) -> tuple:
            ts = match.actual_time or match.predicted_time
            timestamp = ts.timestamp() if ts else 0.0
            return (
                timestamp,
                COMP_LEVEL_ORDER.get(match.competition_level, 99),
                match.set_number,
                match.match_number,
            )

        return sorted(matches, key=sort_key)

    async def _load_alliances(
        self, session: AsyncSession, match: Match
    ) -> tuple[list[int], list[int]]:
        result = await session.execute(
            select(MatchAlliance).where(MatchAlliance.match_id == match.id)
        )
        red: list[int] = []
        blue: list[int] = []
        for alliance in result.scalars().all():
            team_numbers = [int(k.replace("frc", "")) for k in alliance.team_keys]
            if alliance.alliance_color == "red":
                red = team_numbers
            elif alliance.alliance_color == "blue":
                blue = team_numbers
        return red, blue

    async def _load_match_features(
        self,
        session: AsyncSession,
        match_key: str,
        red: list[int],
        blue: list[int],
    ) -> tuple[list[TeamEPA], list[TeamEPA], dict]:
        result = await session.execute(
            select(EPAMetric).where(EPAMetric.match_key == match_key)
        )
        by_team: dict[int, EPAMetric] = {}
        for epa in result.scalars().all():
            by_team[int(epa.team_number)] = epa

        statbotics_pred: dict = {}
        if by_team:
            raw = next(iter(by_team.values())).raw_data or {}
            statbotics_pred = {
                "winner": raw.get("pred_winner"),
                "red_score": raw.get("pred_red_score"),
                "blue_score": raw.get("pred_blue_score"),
                "red_prob": raw.get("pred_red_prob"),
            }

        def build(team_numbers: list[int]) -> list[TeamEPA]:
            epas: list[TeamEPA] = []
            for n in team_numbers:
                epa = by_team.get(n)
                epas.append(
                    TeamEPA(
                        team_number=n,
                        overall_epa=epa.overall_epa if epa else None,
                        auto_epa=epa.auto_epa if epa else None,
                        teleop_epa=epa.teleop_epa if epa else None,
                        endgame_epa=epa.endgame_epa if epa else None,
                    )
                )
            return epas

        return build(red), build(blue), statbotics_pred

    def _build_prediction(
        self,
        match: Match,
        red_epas: list[TeamEPA],
        blue_epas: list[TeamEPA],
        tracker: FormTracker,
        statbotics_pred: dict,
    ) -> Prediction | None:
        if self.strategy == "epa":
            return STRATEGIES["epa"](red_epas, blue_epas)
        if self.strategy == "epa_form":
            red_form = tracker.forms_for([t.team_number for t in red_epas])
            blue_form = tracker.forms_for([t.team_number for t in blue_epas])
            return predict_epa_form(red_epas, blue_epas, red_form, blue_form)
        if self.strategy == "statbotics":
            if not statbotics_pred.get("winner"):
                return None
            return predict_statbotics(
                match.key,
                statbotics_pred.get("winner"),
                statbotics_pred.get("red_score"),
                statbotics_pred.get("blue_score"),
                statbotics_pred.get("red_prob"),
            )
        return None

    @staticmethod
    def _build_run(event_key: str, strategy: str, metrics: dict) -> ReplayRun:
        return ReplayRun(
            event_key=event_key,
            strategy=strategy,
            total_matches=metrics["total_matches"],
            predicted_matches=metrics["predicted_matches"],
            win_accuracy=metrics["win_accuracy"],
            brier_score=metrics["brier_score"],
            log_loss=metrics["log_loss"],
            score_mae=metrics["score_mae"],
            score_rmse=metrics["score_rmse"],
            upset_rate=metrics["upset_rate"],
            upset_detection_accuracy=metrics["upset_detection_accuracy"],
            metrics=metrics,
        )