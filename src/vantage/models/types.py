"""Cross-database type adapters for SQLite and PostgreSQL compatibility."""
from sqlalchemy import String, JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID


def JsonType():
    """Return JSONB on PostgreSQL, JSON on SQLite."""
    from vantage.config.settings import get_settings
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return JSON()
    return JSONB()


def UuidType():
    """Return UUID on PostgreSQL, String(36) on SQLite."""
    from vantage.config.settings import get_settings
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        return String(36)
    return PG_UUID(as_uuid=True)
