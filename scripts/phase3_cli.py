"""CLI for Vantage FRC Phase 3: Gemini-powered Scouting Agent."""

import argparse
import asyncio
import sys

from sqlalchemy import select

from vantage.core.logging import configure_logging
from vantage.db.session import close_db, get_session, init_db
from vantage.models.models import Hypothesis, MatchObservation
from vantage.scout import VantageScout


async def cmd_init(args) -> None:
    configure_logging()
    await init_db()
    print("Database initialized successfully.")


def _fmt_confidence(v) -> str:
    if v is None:
        return "n/a"
    return f"{v:.0%}"


def _fmt_score(v) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1f}"


async def cmd_scout_team(args) -> None:
    configure_logging()
    async with get_session() as session:
        scout = VantageScout(session)
        dossier = await scout.scout_team(
            args.team_number,
            event_key=args.event_key,
            with_hypotheses=not args.no_hypotheses,
        )
        from vantage.scout.dossier import summarize_dossier

        print(summarize_dossier(dossier))
        print()


async def cmd_scout_event(args) -> None:
    configure_logging()
    async with get_session() as session:
        scout = VantageScout(session)
        dossiers = await scout.scout_event(
            args.event_key, limit=args.limit, with_hypotheses=not args.no_hypotheses
        )
        from vantage.scout.dossier import summarize_dossier

        for dossier in dossiers:
            print(summarize_dossier(dossier))
            print()


async def cmd_matchup(args) -> None:
    configure_logging()
    async with get_session() as session:
        red = [int(x) for x in args.red.split(",")]
        blue = [int(x) for x in args.blue.split(",")]
        scout = VantageScout(session)
        analysis = await scout.analyze_matchup(
            red, blue, event_key=args.event_key, season=args.season
        )
        print(
            f"RED {red} vs BLUE {blue}  "
            f"(event={analysis.event_key or 'none'}, strategy={analysis.strategy})"
        )
        print(
            f"predicted: {analysis.predicted_winner}"
            f"  {_fmt_score(analysis.predicted_red_score)} - "
            f"{_fmt_score(analysis.predicted_blue_score)}"
            f"  conf={_fmt_confidence(analysis.prediction_confidence)}"
        )
        if analysis.model_reasoning:
            print(f"\n{analysis.model_reasoning}")
        if analysis.upset_risk:
            print(f"upset risk: {analysis.upset_risk}")
        if analysis.scouting_notes:
            print("\nscouting notes:")
            for note in analysis.scouting_notes:
                print(f"  - {note}")


async def cmd_observe(args) -> None:
    configure_logging()
    async with get_session() as session:
        scout = VantageScout(session)
        reviews = await scout.observe_event(
            args.event_key, only_unobserved=True, limit=args.limit
        )
        total = sum(r.persisted_count() for r in reviews)
        print(f"Observed {len(reviews)} matches, {total} observations persisted")
        for review in reviews:
            print(
                f"  {review.match_key}: {review.persisted_count()} observations"
            )


async def cmd_hypotheses(args) -> None:
    configure_logging()
    async with get_session() as session:
        result = await session.execute(
            select(Hypothesis)
            .where(Hypothesis.team_number == args.team_number)
            .order_by(Hypothesis.confidence.desc())
        )
        items = list(result.scalars().all())
        if not items:
            print(f"No hypotheses for team {args.team_number}")
            return
        print(f"Hypotheses for team {args.team_number}:")
        for h in items:
            print(
                f"  [{h.category}] confidence={_fmt_confidence(h.confidence)} "
                f"status={h.status}"
            )
            print(f"    {h.hypothesis_text}")


async def cmd_observations(args) -> None:
    configure_logging()
    async with get_session() as session:
        result = await session.execute(
            select(MatchObservation)
            .order_by(MatchObservation.created_at.desc())
            .limit(args.limit)
        )
        items = list(result.scalars().all())
        if not items:
            print("No observations yet")
            return
        print(f"Latest {len(items)} observations:")
        for obs in items:
            print(
                f"  team {obs.team_number} [{obs.event_type}] "
                f"confidence={_fmt_confidence(obs.confidence)} "
                f"from={obs.source_agent}"
            )
            print(f"    {obs.observation}")


async def cmd_status(args) -> None:
    configure_logging()
    async with get_session() as session:
        from vantage.models.models import ResearchRecord

        rec = await session.execute(
            select(ResearchRecord).order_by(ResearchRecord.created_at.desc()).limit(5)
        )
        records = list(rec.scalars().all())
        print("Recent research records:")
        for r in records:
            print(
                f"  [{r.info_type}] team={r.team_number} "
                f"conf={_fmt_confidence(r.confidence)} source={r.source}"
            )
            print(f"    {r.title or ''}: {(r.content_summary or '')[:120]}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vantage FRC - Phase 3: Gemini Scouting Agent"
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.set_defaults(func=cmd_init)

    team_parser = subparsers.add_parser(
        "scout-team", help="Generate a scouting dossier for one team"
    )
    team_parser.add_argument("team_number", type=int)
    team_parser.add_argument("--event", dest="event_key", type=str, default=None)
    team_parser.add_argument("--no-hypotheses", action="store_true")
    team_parser.set_defaults(func=cmd_scout_team)

    event_parser = subparsers.add_parser(
        "scout-event", help="Generate dossiers for all teams at an event"
    )
    event_parser.add_argument("event_key", type=str)
    event_parser.add_argument("--limit", type=int, default=None)
    event_parser.add_argument("--no-hypotheses", action="store_true")
    event_parser.set_defaults(func=cmd_scout_event)

    matchup_parser = subparsers.add_parser(
        "matchup", help="Analyze a red vs blue alliance matchup"
    )
    matchup_parser.add_argument("red", type=str, help="Comma-separated team numbers")
    matchup_parser.add_argument("blue", type=str, help="Comma-separated team numbers")
    matchup_parser.add_argument("--event", dest="event_key", type=str, default=None)
    matchup_parser.add_argument("--season", type=int, default=2025)
    matchup_parser.set_defaults(func=cmd_matchup)

    observe_parser = subparsers.add_parser(
        "observe", help="Generate scouting observations for played matches"
    )
    observe_parser.add_argument("event_key", type=str)
    observe_parser.add_argument("--limit", type=int, default=None)
    observe_parser.set_defaults(func=cmd_observe)

    hypo_parser = subparsers.add_parser(
        "hypotheses", help="List stored hypotheses for a team"
    )
    hypo_parser.add_argument("team_number", type=int)
    hypo_parser.set_defaults(func=cmd_hypotheses)

    obs_parser = subparsers.add_parser(
        "observations", help="List recent stored scouting observations"
    )
    obs_parser.add_argument("--limit", type=int, default=20)
    obs_parser.set_defaults(func=cmd_observations)

    status_parser = subparsers.add_parser("status", help="Show recent research")
    status_parser.set_defaults(func=cmd_status)

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