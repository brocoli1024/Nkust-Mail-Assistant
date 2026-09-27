"""DB security and migration contracts; never connect to a real mailbox/database."""
from datetime import date, datetime, timezone
from io import StringIO
import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from app.config import ROOT, Settings
from app.database.multi_user import MultiUserDatabase, validate_database_url
from app.models import Base
from app.models.multi_user import MultiUserBase, User, OAuthAccount, Email, Announcement, Analysis, Scrape


def configuration(url, output=None):
    config = Config(str(ROOT / 'alembic.ini'), output_buffer=output)
    config.attributes['database_url'] = url
    return config


@pytest.fixture
def database(tmp_path):
    url = URL.create('sqlite', database=str(tmp_path / 'multi.db'))
    config = configuration(url)
    command.upgrade(config, 'head')
    db = MultiUserDatabase(url)
    with db.transaction() as session:
        session.add_all([User(id=1, google_user_id='google-a', email='a@example.invalid'),
                         User(id=2, google_user_id='google-b', email='b@example.invalid')])
    yield db, config
    db.close()


def announcement(user_id=1, email_id=1, **kwargs):
    return Announcement(user_id=user_id, email_id=email_id, source_index=0,
                        source_fingerprint='a' * 64, department='教務處',
                        source_category='課程', title='合成公告', original_text='合成本文', **kwargs)


def seed_email(db):
    with db.transaction() as session:
        session.add(Email(id=1, user_id=1, gmail_message_id='same-id', status='processed'))


def test_message_uniqueness_is_per_user(database):
    db, _ = database
    seed_email(db)
    with db.transaction() as session:
        session.add(Email(user_id=2, gmail_message_id='same-id', status='processed'))
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(Email(user_id=1, gmail_message_id='same-id', status='processed'))
    with db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Email)) == 2


@pytest.mark.parametrize('owner', [None, 999])
def test_email_requires_existing_owner(database, owner):
    db, _ = database
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(Email(user_id=owner, gmail_message_id='x', status='failed'))


def test_announcement_cannot_reference_another_users_email(database):
    db, _ = database
    seed_email(db)
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(announcement(user_id=2))
    with db.transaction() as session:
        session.add(announcement(id=1, deadline=date(2026, 10, 1)))
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.get(Announcement, 1).user_id = 2
    with db.transaction() as session:
        assert session.get(Announcement, 1).user_id == 1
        assert session.get(Announcement, 1).deadline == date(2026, 10, 1)
        assert session.scalar(select(Announcement).where(Announcement.user_id == 2)) is None


@pytest.mark.parametrize('kind', ['analysis', 'scrape'])
def test_retained_records_enforce_announcement_owner(database, kind):
    db, _ = database
    seed_email(db)
    with db.transaction() as session:
        session.add(announcement(id=1))
    record = (Analysis(user_id=2, announcement_id=1, input_hash='a'*64,
                       provider='test', model='test', version='v1', status='completed')
              if kind == 'analysis' else
              Scrape(user_id=2, announcement_id=1, status='completed',
                     attempted_at=datetime.now(timezone.utc)))
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(record)


def test_oauth_identity_cannot_belong_to_two_users(database):
    db, _ = database
    with db.transaction() as session:
        session.add(OAuthAccount(user_id=1, provider='google', provider_user_id='subject-a'))
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(OAuthAccount(user_id=2, provider='google', provider_user_id='subject-a'))


def test_delete_owner_cascades_only_their_records(database):
    db, _ = database
    seed_email(db)
    with db.transaction() as session:
        session.add(Email(id=2, user_id=2, gmail_message_id='same-id', status='processed'))
        session.flush()
        session.add_all([announcement(id=1), announcement(id=2, user_id=2, email_id=2)])
        session.flush()
        session.add(Scrape(user_id=1, announcement_id=1, status='completed',
                           attempted_at=datetime.now(timezone.utc)))
    with db.transaction() as session:
        session.execute(delete(User).where(User.id == 1))
    with db.transaction() as session:
        assert session.get(Email, 1) is None
        assert session.get(Announcement, 1) is None
        assert session.get(Scrape, 1) is None
        assert session.get(Announcement, 2).user_id == 2


def test_migration_matches_models_and_repeat_upgrade_preserves_data(database):
    db, config = database
    seed_email(db)
    command.upgrade(config, 'head')
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), MultiUserBase.metadata) == []
    with db.transaction() as session:
        assert session.get(Email, 1).gmail_message_id == 'same-id'
    assert 'users' not in Base.metadata.tables


def test_downgrade_and_reupgrade_on_disposable_database(database):
    db, config = database
    command.downgrade(config, 'base')
    assert set(inspect(db.engine).get_table_names()) == {'alembic_version'}
    command.upgrade(config, 'head')
    assert set(inspect(db.engine).get_table_names()) == set(MultiUserBase.metadata.tables) | {'alembic_version'}


def test_engine_does_not_create_schema(tmp_path):
    db = MultiUserDatabase(URL.create('sqlite', database=str(tmp_path / 'empty.db')))
    try:
        assert inspect(db.engine).get_table_names() == []
    finally:
        db.close()


@pytest.mark.parametrize('url', ['', 'sqlite:///data/nkust_mail.db',
                                 'sqlite:///data/../data/nkust_mail.db',
                                 'sqlite:///file:data/nkust_mail.db?uri=true'])
def test_legacy_path_and_missing_url_rejected(url):
    with pytest.raises(ValueError):
        validate_database_url(url)


def test_custom_legacy_path_rejected(tmp_path):
    path = tmp_path / 'private.db'
    with pytest.raises(ValueError):
        validate_database_url(URL.create('sqlite', database=str(path)), legacy_path=path)
    assert not path.exists()


def test_legacy_copy_migration_refused_without_changes(tmp_path):
    path = tmp_path / 'legacy-copy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE emails (id INTEGER PRIMARY KEY, gmail_message_id TEXT)')
        connection.execute("INSERT INTO emails VALUES (1, 'synthetic')")
    before = path.read_bytes()
    url = URL.create('sqlite', database=str(path))
    with pytest.raises(ValueError, match='Legacy schema'):
        command.upgrade(configuration(url), 'head')
    with pytest.raises(ValueError, match='Legacy schema'):
        MultiUserDatabase(url)
    assert path.read_bytes() == before


def test_postgresql_migration_sql_and_constraint_names():
    output = StringIO()
    config = configuration('postgresql+psycopg://test:unused@localhost/test', output)
    command.upgrade(config, 'head', sql=True)
    sql = output.getvalue()
    assert 'TIMESTAMP WITH TIME ZONE' in sql
    assert 'FOREIGN KEY(user_id, email_id)' in sql
    assert 'REFERENCES emails (user_id, id)' in sql
    assert 'PRAGMA' not in sql and 'julianday' not in sql
    # PostgreSQL rejects duplicate constraint names even if SQLite accepts them.
    names = [c.name for t in MultiUserBase.metadata.tables.values() for c in t.constraints if c.name]
    assert len(names) == len(set(names))


def test_database_url_is_separate_and_not_in_settings_repr(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:private-password@localhost/new')
    settings = Settings.load(tmp_path / 'absent.env')
    assert 'private-password' not in repr(settings)
    assert settings.database_path == ROOT / 'data/nkust_mail.db'
    assert validate_database_url(settings.database_url).drivername == 'postgresql+psycopg'
