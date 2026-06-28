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
    _add_missing_columns()


# create_all never ALTERs existing tables; add columns introduced after a DB
# was first created so older dev databases keep working without a migration tool.
def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    wanted = {
        "download_jobs": {"matches_total": "INTEGER NOT NULL DEFAULT 0",
                          "demos_total": "INTEGER NOT NULL DEFAULT 0",
                          "max_matches": "INTEGER"},
        "rounds": {"winner": "VARCHAR", "win_reason": "VARCHAR"},
        "utility_events": {"radar_x": "FLOAT", "radar_y": "FLOAT"},
    }
    insp = inspect(_engine)
    for table, columns in wanted.items():
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        with _engine.begin() as conn:
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


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
