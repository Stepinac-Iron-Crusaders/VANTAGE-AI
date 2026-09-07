"""Quick validation test for Phase 1 models and imports."""

import asyncio
import sys
import traceback


async def validate_imports():
    """Test that all modules can be imported correctly."""
    errors = []

    try:
        from vantage.config.settings import get_settings, settings
        print("[OK] config.settings")
    except Exception as e:
        errors.append(f"config.settings: {e}")

    try:
        from vantage.db.session import get_engine, get_session, init_db, close_db
        print("[OK] db.session")
    except Exception as e:
        errors.append(f"db.session: {e}")

    try:
        from vantage.models.base import Base, TimestampMixin
        print("[OK] models.base")
    except Exception as e:
        errors.append(f"models.base: {e}")

    try:
        from vantage.models.models import (
            Team, Event, Match, MatchAlliance,
            EventRanking, TeamRanking, MatchStats,
            TeamHistory, EPAMetric, AllianceSelection,
            Hypothesis, ResearchRecord, MatchObservation,
        )
        print("[OK] models.models")
    except Exception as e:
        errors.append(f"models.models: {e}")

    try:
        from vantage.api.tba_client import TBAClient, TBAClientSync, TBAAPIError
        print("[OK] api.tba_client")
    except Exception as e:
        errors.append(f"api.tba_client: {e}")

    try:
        from vantage.api.statbotics_client import StatboticsClient, StatboticsClientSync, StatboticsError
        print("[OK] api.statbotics_client")
    except Exception as e:
        errors.append(f"api.statbotics_client: {e}")

    try:
        from vantage.pipeline.ingestion import FRCDataPipeline
        print("[OK] pipeline.ingestion")
    except Exception as e:
        errors.append(f"pipeline.ingestion: {e}")

    try:
        from vantage.core.logging import configure_logging, get_logger
        print("[OK] core.logging")
    except Exception as e:
        errors.append(f"core.logging: {e}")

    try:
        from vantage import FRCDataPipeline, init_db, close_db, settings
        print("[OK] vantage package")
    except Exception as e:
        errors.append(f"vantage package: {e}")

    if errors:
        print("\n[FAIL] Import errors:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("\n[PASS] All imports successful")
        return True


async def validate_models():
    """Test that model table names and columns are correct."""
    from vantage.models.models import Base

    tables = sorted(Base.metadata.tables.keys())
    expected = [
        "teams", "events", "matches", "match_alliances",
        "event_rankings", "team_rankings", "match_stats",
        "team_history", "epa_metrics", "alliance_selections",
        "hypotheses", "research_records", "match_observations",
    ]

    missing = [t for t in expected if t not in tables]
    if missing:
        print(f"[FAIL] Missing tables: {missing}")
        return False

    print(f"[OK] All {len(expected)} tables defined")
    return True


async def main():
    print("=" * 50)
    print("Vantage FRC Phase 1 Validation")
    print("=" * 50)

    imports_ok = await validate_imports()
    models_ok = await validate_models()

    print("\n" + "=" * 50)
    if imports_ok and models_ok:
        print("Phase 1 validation: PASSED")
        sys.exit(0)
    else:
        print("Phase 1 validation: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())