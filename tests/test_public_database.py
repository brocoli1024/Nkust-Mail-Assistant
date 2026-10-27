from datetime import datetime, timezone
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from alembic import command
import pytest

from tests.test_multi_user_database import database
from app.models.multi_user import User
from app.models.public_announcements import PublicAnnouncement, PublicSourceState


def public_row(url='https://osa.nkust.edu.tw/a'):
    return PublicAnnouncement(source_key='nkust-latest', canonical_url=url,
                              title='同名合成公告', excerpt='', content_hash='a'*64)


def test_public_rows_have_no_user_dependency(database):
    db, _ = database
    with db.transaction() as s:
        s.add(public_row())
    with db.transaction() as s:
        s.execute(delete(User))
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(PublicAnnouncement)) == 1


def test_public_identity_is_source_and_url_not_title(database):
    db, _ = database
    with db.transaction() as s:
        s.add_all([public_row(), public_row('https://osa.nkust.edu.tw/b')])
    with pytest.raises(IntegrityError):
        with db.transaction() as s:
            s.add(public_row())
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(PublicAnnouncement)) == 2


def test_migration_preserves_private_users_and_has_complete_metadata(database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.models.multi_user import MultiUserBase
    db, config = database
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(User)) == 2
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), MultiUserBase.metadata) == []
    command.downgrade(config, '0005')
    command.upgrade(config, 'head')
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(User)) == 2


def test_invalid_student_state_is_rejected(database):
    db, _ = database
    with pytest.raises(IntegrityError):
        with db.transaction() as s:
            row=public_row()
            row.student_relevance='anything'
            s.add(row)
