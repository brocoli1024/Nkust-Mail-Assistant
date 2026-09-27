"""Opt-in PostgreSQL integration. Only a generated, disposable schema is removed.

Set NKUST_TEST_POSTGRES_URL to an independent test database (never production).
No fallback to the application's DATABASE_URL is allowed.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select, text
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.exc import IntegrityError

from app.database.multi_user import MultiUserDatabase, validate_database_url
from app.database.user_mail import UserSyncLease, SyncBusy
from app.models.multi_user import MultiUserBase, User, Email
from tests.test_multi_user_database import configuration
from tests import test_multi_user_database as contracts
from tests import test_sync_multi_user as sync_contracts


@pytest.fixture
def database():
    raw = os.environ.get('NKUST_TEST_POSTGRES_URL')
    if not raw:
        pytest.skip('NKUST_TEST_POSTGRES_URL absent: PostgreSQL NOT verified')
    url = validate_database_url(raw)
    if url.drivername != 'postgresql+psycopg':
        pytest.fail('Use postgresql+psycopg for the independent PostgreSQL test database')
    schema = 'nkust_test_' + uuid.uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    created = False
    db = None
    try:
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        isolated = url.update_query_dict({'options': f'-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=30000'})
        config = configuration(isolated)
        command.upgrade(config, 'head')
        db = MultiUserDatabase(isolated)
        with db.transaction() as session:
            assert session.scalar(text('select current_schema()')) == schema
            session.add_all([User(id=1, google_user_id='a', email='a@example.invalid'),
                             User(id=2, google_user_id='b', email='b@example.invalid')])
        yield db, config
    finally:
        if db is not None:
            db.close()
        if created:
            # schema is generated here, never accepted from settings/user input.
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def test_schema_and_repeat_upgrade(database):
    db, config = database
    command.upgrade(config, 'head')
    with db.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), MultiUserBase.metadata) == []


@pytest.mark.parametrize('contract', [
    contracts.test_announcement_cannot_reference_another_users_email,
    contracts.test_delete_owner_cascades_only_their_records,
    contracts.test_downgrade_and_reupgrade_on_disposable_database,
    sync_contracts.test_user_data_isolation_and_same_message_id_allowed,
    sync_contracts.test_repeat_sync_skips_download_and_releases_lease,
    sync_contracts.test_one_failure_continues_sanitizes_and_retry_recovers,
])
def test_database_contracts(database, contract):
    contract(database)


def test_message_uniqueness_and_generated_ids(database):
    db, _ = database
    with db.transaction() as session:
        a = Email(user_id=1, gmail_message_id='shared', status='processed')
        b = Email(user_id=2, gmail_message_id='shared', status='processed')
        session.add_all([a, b])
        session.flush()
        assert a.id != b.id
    with pytest.raises(IntegrityError):
        with db.transaction() as session:
            session.add(Email(user_id=1, gmail_message_id='shared', status='processed'))


def test_concurrent_lease_has_one_winner(database):
    db, _ = database
    gate = Barrier(2)
    leases = [UserSyncLease(db, 1), UserSyncLease(db, 1)]
    def acquire(lease):
        gate.wait(timeout=10)
        try:
            lease.acquire()
            return True
        except SyncBusy:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, leases))
    assert sorted(outcomes) == [False, True]
    for lease in leases:
        lease.release()
