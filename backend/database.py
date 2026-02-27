"""Async SQLAlchemy engine, session factory, and base model."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from backend.config import settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None
_db_available = None  # None = untested, True/False = cached result


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def _check_db_available() -> bool:
    """Test if the database is reachable. Caches result."""
    global _db_available
    if _db_available is not None:
        return _db_available
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _db_available = True
    except Exception as exc:
        logger.warning("Database not reachable: %s", exc)
        _db_available = False
    return _db_available


async def get_db():  # type: ignore[misc]
    """FastAPI dependency that yields an async database session.

    In develop mode, yields None if database is unreachable.
    """
    if settings.is_develop:
        available = await _check_db_available()
        if not available:
            yield None
            return

    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
