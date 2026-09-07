"""CLI entry point for Vantage FRC Phase 1: Database and Data Pipeline."""

import argparse
import asyncio
import sys

from vantage.config.settings import get_settings
from vantage.core.logging import configure_logging
from vantage.db.session import init_db, close_db
from vantage.pipeline.ingestion import FRCDataPipeline


async def cmd_init(args) -> None:
    configure_logging()
    await init_db()
    print("Database initialized successfully.")


async def cmd_ingest_team(args) -> None:
    configure_logging()
    async with FRCDataPipeline() as pipeline:
        team = await pipeline.ingest_team_full(args.team_number)
        if team:
            print(f"Team {args.team_number}: {team.name or 'Unknown'}")
        else:
            print(f"Team {args.team_number}: not found")


async def cmd_ingest_event(args) -> None:
    configure_logging()
    async with FRCDataPipeline() as pipeline:
        event = await pipeline.ingest_event_full(args.event_key)
        if event:
            print(f"Event {args.event_key}: {event.name}")
            counts = await pipeline.count_event_data(args.event_key)
            print(
                "  matches: {}, rankings: {}, teams: {}".format(
                    counts.get("matches", 0),
                    counts.get("rankings", 0),
                    counts.get("teams", 0),
                )
            )
        else:
            print(f"Event {args.event_key}: not found")


async def cmd_backfill(args) -> None:
    configure_logging()
    async with FRCDataPipeline() as pipeline:
        result = await pipeline.backfill_season(args.season)
        print(f"Backfill complete: {result}")


async def cmd_health(args) -> None:
    configure_logging()
    async with FRCDataPipeline() as pipeline:
        health = await pipeline.health_check()
        print(f"Health check: {health}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vantage FRC - Phase 1: Database and Data Pipeline"
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.set_defaults(func=cmd_init)

    team_parser = subparsers.add_parser("ingest-team", help="Ingest team data")
    team_parser.add_argument("team_number", type=int)
    team_parser.set_defaults(func=cmd_ingest_team)

    event_parser = subparsers.add_parser("ingest-event", help="Ingest event data")
    event_parser.add_argument("event_key", type=str)
    event_parser.set_defaults(func=cmd_ingest_event)

    backfill_parser = subparsers.add_parser("backfill", help="Backfill season data")
    backfill_parser.add_argument("season", type=int)
    backfill_parser.set_defaults(func=cmd_backfill)

    health_parser = subparsers.add_parser("health", help="Health check")
    health_parser.set_defaults(func=cmd_health)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    await args.func(args)


if __name__ == "__main__":
    asyncio.run(main())