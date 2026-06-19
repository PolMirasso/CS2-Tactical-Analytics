from __future__ import annotations

from app.config import get_settings
from collections.abc import Iterator
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine = None
_SessionLocal: sessionmaker | None = None


class Base(DeclarativeBase):
    pass


def _ensure() -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        url = get_settings().resolved_db_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _SessionLocal


def init_db() -> None:
    # Import models so they register on Base before create_all.
    from app.domain import models  # noqa: F401

    _ensure()
    Base.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    #FastAPI dependency: yields a session, commits on success
    session = _ensure()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    # Standalone transactional session for startup tasks / scripts
    session = _ensure()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
