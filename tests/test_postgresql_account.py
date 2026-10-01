"""Run account boundaries against the opt-in disposable PostgreSQL schema.

The imported fixture requires NKUST_TEST_POSTGRES_URL and never reads the
application DATABASE_URL. Google calls use synthetic credentials and responses.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import Settings
from app.database.user_mail import SyncBusy, UserSyncLease
from app.models.multi_user import User
from app.web import create_app
from tests.test_auth import FakeGoogle, oauth
from tests.test_postgresql import database
from tests import test_account_controls as contracts


@pytest.fixture
def postgres_web(database, oauth):
    db, _ = database
    # Account contracts start with no users, in this generated schema only.
    with db.transaction() as session:
        session.execute(delete(User))
    google = FakeGoogle(oauth)
    settings = Settings(database_url=db.engine.url)
    app = create_app(settings, oauth, google_factory=lambda _: google,
                     session_enabled=True,
                     session_secret='test-only-session-secret-32-characters')
    with TestClient(app, base_url='http://localhost', follow_redirects=False) as client:
        yield client, app, google, settings


@pytest.mark.parametrize('contract', [
    contracts.test_deletion_removes_only_current_users_data_and_all_their_sessions,
    contracts.test_active_sync_blocks_deletion_without_revoking_credentials,
    contracts.test_deletion_has_no_get_or_anonymous_side_effect,
    contracts.test_reconnect_cannot_replace_tokens_during_account_deletion,
    contracts.test_delayed_callback_cannot_issue_session_for_a_reused_user_id,
])
def test_account_database_contracts(postgres_web, contract):
    contract(postgres_web)


@pytest.mark.parametrize('operation', ['delete', 'sync'])
def test_stale_account_write(postgres_web, operation):
    contracts.test_stale_authenticated_request_cannot_target_a_reused_account_id(
        postgres_web, operation)


@pytest.mark.parametrize('view', ['list', 'detail', 'dashboard'])
def test_stale_account_read(postgres_web, view):
    contracts.test_stale_request_cannot_read_a_reused_accounts_announcements(
        postgres_web, view)


def test_local_deletion_when_google_fails(postgres_web, caplog):
    contracts.test_google_failure_does_not_prevent_local_data_deletion_or_expose_secrets(
        postgres_web, caplog)


def test_fence_and_acquire_lock_user_before_lease(database, monkeypatch):
    """Deletion must not hold the lease while a competing sync holds its User."""
    db, _ = database
    owner = UserSyncLease(db, 1, google_user_id='google-a')
    contender = UserSyncLease(db, 1, google_user_id='google-a')
    checking, user_locked = Event(), Event()
    original_check = contender._check_identity

    def check_identity(session, *, lock=False):
        checking.set()
        original_check(session, lock=lock)
        user_locked.set()

    monkeypatch.setattr(contender, '_check_identity', check_identity)

    def acquire():
        try:
            contender.acquire()
            return True
        except SyncBusy:
            return False

    owner.acquire()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with db.transaction() as session:
                owner.fence(session)
                future = pool.submit(acquire)
                assert checking.wait(5)
                # The contender must wait at User, before reaching SyncLease.
                acquired_before_commit = user_locked.wait(0.5)
            assert future.result(timeout=5) is False
        assert not acquired_before_commit
    finally:
        owner.release()
