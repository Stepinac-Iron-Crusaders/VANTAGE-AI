from datetime import datetime
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    func,
    Column,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy import types
import uuid

from vantage.models.base import Base
from vantage.models.types import JsonType, UuidType


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    team_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rookies_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data = Column(JsonType(), default=dict)

    team_rankings = relationship("TeamRanking", back_populates="team", lazy="selectin")
    event_rankings = relationship("EventRanking", back_populates="team", lazy="selectin")
    match_stats = relationship("MatchStats", back_populates="team", lazy="selectin")
    history = relationship("TeamHistory", back_populates="team", lazy="selectin")
    hypotheses = relationship("Hypothesis", back_populates="team", lazy="selectin")

    __table_args__ = (
        Index("idx_team_number", "team_number", unique=True),
    )


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state_prov: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data = Column(JsonType(), default=dict)

    matches = relationship("Match", back_populates="event", lazy="selectin")
    event_rankings = relationship("EventRanking", back_populates="event", lazy="selectin")

    __table_args__ = (
        Index("idx_event_code", "event_code"),
        Index("idx_event_season", "season"),
        Index("idx_event_start_date", "start_date"),
    )


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(UuidType(), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    match_number: Mapped[int] = mapped_column(Integer, nullable=False)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    competition_level: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    predicted_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    raw_alliances = Column(JsonType(), nullable=True)
    raw_scores = Column(JsonType(), nullable=True)
    red_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blue_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winning_alliance: Mapped[str | None] = mapped_column(String(10), nullable=True)

    event = relationship("Event", back_populates="matches")
    alliances = relationship("MatchAlliance", back_populates="match", lazy="selectin")
    stats = relationship("MatchStats", back_populates="match", lazy="selectin")

    __table_args__ = (
        Index("idx_match_event", "event_id", "competition_level", "match_number", "set_number", unique=True),
        Index("idx_match_event_id", "event_id"),
        Index("idx_match_status", "status"),
        Index("idx_match_actual_time", "actual_time"),
    )


class MatchAlliance(Base, TimestampMixin):
    __tablename__ = "match_alliances"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(UuidType(), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    alliance_color: Mapped[str] = mapped_column(String(10), nullable=False)
    team_keys = Column(JsonType(), nullable=False)
    surrogate_team_keys = Column(JsonType(), default=list)
    dq_team_keys = Column(JsonType(), default=list)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match = relationship("Match", back_populates="alliances")

    __table_args__ = (
        Index("idx_match_alliance_match", "match_id"),
        Index("idx_match_alliance_color", "alliance_color"),
    )


class EventRanking(Base, TimestampMixin):
    __tablename__ = "event_rankings"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(UuidType(), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    rp: Mapped[float | None] = mapped_column(Float, nullable=True)
    autoplay_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    teleop_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    playoff_rp: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order_info = Column(JsonType(), default=dict)
    raw_data = Column(JsonType(), default=dict)

    event = relationship("Event", back_populates="event_rankings")
    team = relationship("Team", back_populates="event_rankings")

    __table_args__ = (
        Index("idx_ranking_event_team", "event_id", "team_number", unique=True),
        Index("idx_ranking_event_rank", "event_id", "rank"),
    )


class TeamRanking(Base, TimestampMixin):
    __tablename__ = "team_rankings"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rp: Mapped[float | None] = mapped_column(Float, nullable=True)
    opr: Mapped[float | None] = mapped_column(Float, nullable=True)
    dpr: Mapped[float | None] = mapped_column(Float, nullable=True)
    ccwm: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_data = Column(JsonType(), default=dict)

    team = relationship("Team", back_populates="team_rankings")

    __table_args__ = (
        Index("idx_team_ranking_season", "team_number", "season", unique=True),
    )


class MatchStats(Base, TimestampMixin):
    __tablename__ = "match_stats"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(UuidType(), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )

    auto_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    teleop_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    rp_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    penalty_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    foul_points: Mapped[float | None] = mapped_column(Float, nullable=True)

    speakers_amplified: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speakers_underserved: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    climbs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    park_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_speakers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_amp_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_trap_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_surrogate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dq: Mapped[bool] = mapped_column(Boolean, default=False)
    starting_position: Mapped[str | None] = mapped_column(String(20), nullable=True)

    raw_data = Column(JsonType(), default=dict)

    match = relationship("Match", back_populates="stats")
    team = relationship("Team", back_populates="match_stats")

    __table_args__ = (
        Index("idx_match_stats_match", "match_id"),
        Index("idx_match_stats_team", "team_number"),
        Index("idx_match_stats_match_team", "match_id", "team_number", unique=True),
    )


class TeamHistory(Base, TimestampMixin):
    __tablename__ = "team_history"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    event_code: Mapped[str] = mapped_column(String(50), nullable=False)
    match_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loss_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tie_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playoff_appearance: Mapped[bool] = mapped_column(Boolean, default=False)
    playoff_wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playoff_losses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_opp_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_data = Column(JsonType(), default=dict)

    team = relationship("Team", back_populates="history")

    __table_args__ = (
        Index("idx_history_team_season", "team_number", "season"),
        Index("idx_history_team_event", "team_number", "event_code"),
    )


class EPAMetric(Base, TimestampMixin):
    __tablename__ = "epa_metrics"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    match_key: Mapped[str] = mapped_column(String(100), nullable=False)
    auto_epa: Mapped[float | None] = mapped_column(Float, nullable=True)
    teleop_epa: Mapped[float | None] = mapped_column(Float, nullable=True)
    endgame_epa: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_epa: Mapped[float | None] = mapped_column(Float, nullable=True)
    cliff_epa: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_data = Column(JsonType(), default=dict)

    team = relationship("Team")

    __table_args__ = (
        Index("idx_epa_team_season", "team_number", "season"),
        Index("idx_epa_match_key", "match_key"),
    )


class AllianceSelection(Base, TimestampMixin):
    __tablename__ = "alliance_selections"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(UuidType(), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    selection: Mapped[str] = mapped_column(String(20), nullable=False)
    backup_team: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_station: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data = Column(JsonType(), default=dict)

    event = relationship("Event")
    team = relationship("Team")

    __table_args__ = (
        Index("idx_alliance_event_team", "event_id", "team_number", unique=True),
    )


class Hypothesis(Base, TimestampMixin):
    __tablename__ = "hypotheses"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    hypothesis_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unconfirmed")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_matches = Column(JsonType(), default=list)
    raw_data = Column(JsonType(), default=dict)

    team = relationship("Team", back_populates="hypotheses")

    __table_args__ = (
        Index("idx_hypothesis_team", "team_number"),
        Index("idx_hypothesis_category", "category"),
        Index("idx_hypothesis_status", "status"),
    )


class ResearchRecord(Base, TimestampMixin):
    __tablename__ = "research_records"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_number: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    raw_data = Column(JsonType(), default=dict)

    team = relationship("Team")

    __table_args__ = (
        Index("idx_research_team", "team_number"),
        Index("idx_research_source", "source"),
        Index("idx_research_info_type", "info_type"),
        Index("idx_research_verification", "verification_status"),
    )


class MatchObservation(Base, TimestampMixin):
    __tablename__ = "match_observations"

    id = Column(UuidType(), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(UuidType(), ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    team_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.team_number"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    video_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data = Column(JsonType(), default=dict)

    match = relationship("Match")
    team = relationship("Team")

    __table_args__ = (
        Index("idx_observation_match", "match_id"),
        Index("idx_observation_team", "team_number"),
        Index("idx_observation_event_type", "event_type"),
        Index("idx_observation_confidence", "confidence"),
    )