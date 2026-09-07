# Vantage FRC - Phase 1: Database and Data Pipeline

## Overview

Phase 1 establishes the foundation for the Vantage FRC AI Tactical Intelligence system.
It includes:

- **Database schema** for FRC data (teams, events, matches, alliances, rankings, EPA metrics)
- **FRC Data Pipeline** for ingesting data from The Blue Alliance (TBA) and Statbotics APIs
- **Structured data storage** optimized for fast live competition queries

## Project Structure

```text
src/vantage/
  config/
    settings.py          - Configuration management (env vars, Pydantic)
  db/
    session.py           - Async database session management
    indexes.py           - Additional indexes for live queries
  models/
    base.py              - SQLAlchemy Base and TimestampMixin
    models.py            - All FRC data models (Team, Event, Match, etc.)
  api/
    tba_client.py        - The Blue Alliance API client (async)
    statbotics_client.py - Statbotics API client (async)
  pipeline/
    ingestion.py         - Data ingestion pipeline
  core/
    logging.py           - Structured logging with structlog
```

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `teams` | Team information (number, name, location, etc.) |
| `events` | Competition events |
| `matches` | Match data with scores, alliances, status |
| `match_alliances` | Alliance composition and scores per match |
| `event_rankings` | Event-specific rankings (RP, OPR, etc.) |
| `team_rankings` | Season-level team rankings |
| `match_stats` | Per-team match performance statistics |
| `epa_metrics` | EPA (Expected Points Added) metrics per match |
| `team_history` | Historical performance summaries |
| `alliance_selections` | Playoff alliance selections |
| `hypotheses` | Strategic hypotheses about teams |
| `research_records` | Internet research findings |
| `match_observations` | Scouting observations from video |

## Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your database URL and TBA API key

# Initialize database
python scripts/phase1_cli.py init

# Ingest a team
python scripts/phase1_cli.py ingest-team 254

# Ingest an event
python scripts/phase1_cli.py ingest-event 2025miket

# Backfill a season
python scripts/phase1_cli.py backfill 2025

# Health check
python scripts/phase1_cli.py health
```

## Usage Example

```python
import asyncio
from vantage import FRCDataPipeline, init_db

async def main():
    await init_db()
    async with FRCDataPipeline() as pipeline:
        # Ingest team data
        team = await pipeline.ingest_team_full(254)
        # Ingest event with matches and rankings
        event = await pipeline.ingest_event_full("2025miket")
        # Health check
        health = await pipeline.health_check()

asyncio.run(main())
```

## API Clients

### TBAClient
Async client for The Blue Alliance API v3.
- `get_team(team_number)` - Get team info
- `get_team_events(team_number, season)` - Get team events
- `get_event_matches(event_key)` - Get event matches
- `get_event_rankings(event_key)` - Get event rankings
- `get_match(match_key)` - Get match details
- `get_top_teams(season, count)` - Get top teams by OPR

### StatboticsClient
Async client for Statbotics API v3.
- `get_team_epa(team_number, season)` - Get team EPA metrics
- `get_match_epa(match_key)` - Get match EPA data
- `get_team_matches(team_number, season)` - Get team match history
- `get_teams(season)` - Get all teams in a season

## Key Features

- **Async all the way**: Uses `httpx.AsyncClient` and `asyncpg` for high concurrency
- **Structured data**: Pydantic models validate API responses before DB insertion
- **Upsert semantics**: Prevents duplicate data on re-ingestion
- **Graceful degradation**: API failures logged, don't crash pipeline
- **Rate limiting**: Semaphores control API request rates
- **Structured logging**: All operations logged with structlog for observability

## Next Phase

Phase 2: Historical Match Replay System
- Replay past competitions using ingested data
- Build backtesting framework for predictions
- Measure detection and prediction accuracy