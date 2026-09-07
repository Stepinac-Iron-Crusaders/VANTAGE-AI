"""Human-readable summary of a replay run."""

from __future__ import annotations

from vantage.models.models import ReplayRun


def fmt_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def format_replay_summary(run: ReplayRun) -> str:
    metrics = run.metrics or {}
    by_level = metrics.get("by_level", {})
    pct_str = fmt_percent(
        run.predicted_matches / run.total_matches if run.total_matches else None
    )
    lines = [
        "=" * 60,
        f"Replay Run {str(run.id)[:8]}  {run.event_key}  strategy={run.strategy}",
        "=" * 60,
        f"  matches: {run.total_matches}  predicted: {run.predicted_matches} "
        f"({pct_str})",
        f"  win accuracy: {fmt_percent(run.win_accuracy)}",
        f"  score MAE:    {fmt_num(run.score_mae)}    RMSE: {fmt_num(run.score_rmse)}",
        f"  brier:        {fmt_num(run.brier_score)}  "
        f"log loss: {fmt_num(run.log_loss)}",
        f"  upset rate:   {fmt_percent(run.upset_rate)}",
        f"  upset detect: {fmt_percent(run.upset_detection_accuracy)}",
    ]
    if by_level:
        lines.append("-" * 60)
        lines.append("  breakdown by level:")
        for level, m in sorted(by_level.items()):
            acc = fmt_percent(m.get("win_accuracy"))
            mae = fmt_num(m.get("score_mae"))
            lines.append(
                f"    {level:<4} matches={m.get('total', 0):>3}  "
                f"pred={m.get('predicted', 0):>3}  acc={acc}  mae={mae}"
            )
    lines.append("=" * 60)
    return "\n".join(lines)


def format_run_list(runs: list[ReplayRun]) -> str:
    lines = ["id        event     strategy   total  pred  acc"]
    for run in runs:
        lines.append(
            f"{str(run.id)[:8]}  {run.event_key:<9} {run.strategy:<10} "
            f"{run.total_matches:>5} {run.predicted_matches:>4} "
            f"{fmt_percent(run.win_accuracy)}"
        )
    return "\n".join(lines)