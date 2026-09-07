"""Vantage FRC - AI Tactical Intelligence and Copilot System for FIRST Robotics Competition"""

from vantage.config.settings import get_settings, settings
from vantage.db.session import get_engine, get_session, init_db, close_db
from vantage.pipeline.ingestion import FRCDataPipeline

__version__ = "0.1.0"
__all__ = [
    "get_settings",
    "settings",
    "get_engine",
    "get_session",
    "init_db",
    "close_db",
    "FRCDataPipeline",
]