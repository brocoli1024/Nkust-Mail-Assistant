"""URL-based connections only; schema changes belong to Alembic."""
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import ROOT


def validate_database_url(value, *, legacy_path=None):
    if not value or (isinstance(value, str) and not value.strip()):
        raise ValueError('DATABASE_URL is required; use a separate multi-user database')
    url = make_url(value)
    if url.get_backend_name() not in ('sqlite', 'postgresql'):
        raise ValueError('DATABASE_URL must use SQLite or PostgreSQL')
    if url.get_backend_name() == 'postgresql' and url.drivername == 'postgresql':
        url = url.set(drivername='postgresql+psycopg')
    if url.get_backend_name() == 'sqlite':
        # URI aliases can bypass the resolved-path protection below.
        if url.query or (url.database or '').startswith('file:'):
            raise ValueError('SQLite URI/query options are not supported')
        if url.database and url.database != ':memory:':
            path = Path(url.database).expanduser()
            path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            protected = { (ROOT / 'data/nkust_mail.db').resolve() }
            if legacy_path is not None:
                legacy = Path(legacy_path).expanduser()
                protected.add((ROOT / legacy).resolve() if not legacy.is_absolute() else legacy.resolve())
            if path in protected:
                raise ValueError('DATABASE_URL must not point to the legacy database')
            url = url.set(database=str(path))
    return url


def reject_legacy_schema(connection):
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    for table in ('emails', 'announcements'):
        if table in tables and 'user_id' not in {c['name'] for c in inspector.get_columns(table)}:
            raise ValueError('Legacy schema detected; migrate into a NEW database, never in place')


def create_multi_user_engine(database_url, *, legacy_path=None):
    url = validate_database_url(database_url, legacy_path=legacy_path)
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
    if url.get_backend_name() == 'sqlite':
        @event.listens_for(engine, 'connect')
        def configure(connection, _):
            # Explicit BEGIN also makes SQLite DDL transactional on older Python.
            connection.isolation_level = None
            connection.execute('PRAGMA foreign_keys=ON')
        @event.listens_for(engine, 'begin')
        def begin(connection):
            connection.exec_driver_sql('BEGIN')
    return engine


class MultiUserDatabase:
    def __init__(self, database_url, *, legacy_path=None):
        self.engine = create_multi_user_engine(database_url, legacy_path=legacy_path)
        try:
            with self.engine.connect() as connection:
                reject_legacy_schema(connection)
        except Exception:
            self.engine.dispose()
            raise

    @contextmanager
    def transaction(self):
        with Session(self.engine) as session, session.begin():
            yield session

    def close(self):
        self.engine.dispose()
