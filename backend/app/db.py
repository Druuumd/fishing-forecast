from sqlalchemy import Engine, create_engine

from app.settings import Settings


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        _normalize_database_url(settings.database_url),
        pool_pre_ping=True,
        future=True,
    )
