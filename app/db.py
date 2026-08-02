"""Database helpers."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(settings.database_url, future=True, pool_pre_ping=True)


def ping(engine: Engine | None = None) -> bool:
    engine = engine or get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
