"""CLI for Vantage FRC Phase 2: Historical Match Replay System."""

import argparse
import asyncio
import sys

from sqlalchemy import select

from vantage.core.logging import configure_logging
from vantage.db.session import close_db, get_session, init_db
from vantage.models.models import ReplayPrediction, ReplayRun
from vantage.pipeline.ingestion import FRCDataPipeline
from vantage.replay import STRATEGIES, ReplayEngine
from vantage.replay.report import format_replay_summary, format_run_list


async def cmd_init(args) -> None:
    configure_logging()
    await init_db()
    print("Database initialized successfully.")


async def cmd_ingest_event_epa(args) -> None:
    configure_logging()
    async with FRCDataPipeline() as pipeline:
        ingested = await pipeline.ingest_event_epa(args.event_key)
        print(f"Ingested EPA for {ingested} matches in {args.event_key}")


async def cmd_replay(args) -> None:
    configure_logging()
    strategies = [args.strategy] if args.strategy else sorted(STRATEGIES)
    for strategy in strategies:
        engine = ReplayEngine(strategy=strategy)
        run = await engine.replay_event(args.event_key, persist=True)
        if run is None:
            print(f"No replay run produced for {args.event_key} (strategy={strategy})")
            sys.exit(1)
        print(format_replay_summary(run))
        print()


async def cmd_runs(args) -> None:
    configure_logging()
    async with get_session() as session:
        result = await session.execute(
            select(ReplayRun)
            .where(ReplayRun.event_key == args.event_key)
            .order_by(ReplayRun.created_at.desc())
            .limit(args.limit)
        )
        runs = list(result.scalars().all())
        if not runs:
            print(f"No replay runs found for {args.event_key}")
            return
        print(format_run_list(runs))


async def cmd_run_detail(args) -> None:
    configure_logging()
    async with get_session() as session:
        result = await session.execute(
            select(ReplayRun).where(ReplayRun.id.like(f"{args.run_id}%"))
        )
        run = result.scalar_one_or_none()
        if not run:
            print(f"Run {args.run_id} not found")
            return
        print(format_replay_summary(run))

        preds = await session.execute(
            select(ReplayPrediction)
            .where(ReplayPrediction.run_id == run.id)
            .order_by(ReplayPrediction.competition_level, ReplayPrediction.match_number)
        )
        print("\npredictions:")
        header = f"{'key':<18} {'lv':<4} {'#':>3}  "
        header += f"{'pred':<4} {'pR>pB':<7} {'act':<4} {'aR>aB':<6} ok"
        print(header)
        for p in preds.scalars().all():
            pred_win = p.predicted_winner or "-"
            act_win = p.actual_winner or "-"
            ok = "Y" if p.correct else ("-" if p.correct is None else "N")
            pred_score = f"{_f(p.predicted_red_score)}>{_f(p.predicted_blue_score)}"
            act_score = f"{_f(p.actual_red_score)}>{_f(p.actual_blue_score)}"
            print(
                f"{p.match_key:<18} {p.competition_level:<4} {p.match_number:>3}  "
                f"{pred_win:<4} {pred_score:<7} "
                f"{act_win:<4} {act_score:<6} {ok}"
            )


def _f(v) -> str:
    if v is None:
        return "-"
    return str(int(v))


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vantage FRC - Phase 2: Historical Match Replay System"
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init", help="Initialize database (adds replay tables)"
    )
    init_parser.set_defaults(func=cmd_init)

    epa_parser = subparsers.add_parser(
        "ingest-epa", help="Ingest pre-match Statbotics EPA for all matches of an event"
    )
    epa_parser.add_argument("event_key", type=str)
    epa_parser.set_defaults(func=cmd_ingest_event_epa)

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay an event and measure prediction accuracy",
    )
    replay_parser.add_argument("event_key", type=str)
    replay_parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help=f"Prediction strategy. One of {sorted(STRATEGIES)} (default: all)",
    )
    replay_parser.set_defaults(func=cmd_replay)

    runs_parser = subparsers.add_parser("runs", help="List replay runs for an event")
    runs_parser.add_argument("event_key", type=str)
    runs_parser.add_argument("--limit", type=int, default=10)
    runs_parser.set_defaults(func=cmd_runs)

    detail_parser = subparsers.add_parser("run", help="Show details of a replay run")
    detail_parser.add_argument("run_id", type=str)
    detail_parser.set_defaults(func=cmd_run_detail)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        await args.func(args)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())