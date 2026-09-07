from sqlalchemy import Index, ForeignKey
from sqlalchemy.orm import DeclarativeBase


def create_indexes() -> None:
    """Define additional indexes for fast live competition queries."""
    indexes = [
        Index("idx_live_match_status", "matches", "status"),
        Index("idx_live_match_event_time", "matches", "event_id", "actual_time"),
        Index("idx_live_ranking_event", "event_rankings", "event_id", "rank"),
        Index("idx_live_epa_team_season", "epa_metrics", "team_number", "season"),
        Index("idx_live_observation_team_time", "match_observations", "team_number", "timestamp"),
    ]
    return indexes