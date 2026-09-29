from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone, date
from threading import Event

import pytest
from sqlalchemy import select, func, update

from app.core.session import CurrentUser
from app.database.multi_user import MultiUserDatabase
from app.database.user_mail import UserMailRepository, UserSyncLease, SyncBusy, SyncLeaseLost
from app.models.multi_user import Email, Announcement, SyncLease
from app.services.announcement_parser import parse_email
from app.services.gmail_service import GmailError
from app.services.user_gmail_service import GmailReauthorizationRequired
from app.services.user_sync_service import UserSyncService
from tests.test_api import mail
from tests.test_multi_user_database import database

A = CurrentUser(1, 'a@example.invalid', 'A')
B = CurrentUser(2, 'b@example.invalid', 'B')


class FakeMailbox:
    def __init__(self, messages):
        self.messages = messages
        self.reads = []
        self.closed = False

    def __enter__(self):
        self.closed = False
        return self

    def __exit__(self, *args):
        self.closed = True

    def list_message_ids(self, limit):
        return list(self.messages)[:limit]

    def read_message(self, message_id):
        self.reads.append(message_id)
        value = self.messages[message_id]
        if isinstance(value, Exception):
            raise value
        return value


def test_new_sync_classifies_source_category_variant(database):
    db, _ = database
    email = mail('variant')
    email = replace(email, html_body=email.html_body.replace('<td>獎學金</td>', '<td>獎學金申請</td>'))
    result = UserSyncService(db, lambda user: FakeMailbox({'variant': email})).sync_gmail_for_user(A)
    assert result['announcements_created'] == 3
    with db.transaction() as session:
        row = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 0))
        assert row.source_category == '獎學金申請'
        assert row.category == '獎學金'


def test_generic_source_uses_unique_title_category(database):
    db, _ = database
    UserSyncService(db, lambda user: FakeMailbox({'sample': mail('sample')})).sync_gmail_for_user(A)
    with db.transaction() as session:
        row = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 1))
        assert row.source_category == '其他'
        assert row.category == '徵才'


def test_repeat_sync_backfills_only_current_users_unclassified_announcements(database):
    db, _ = database
    boxes = {1: FakeMailbox({'a': mail('a')}), 2: FakeMailbox({'b': mail('b')})}
    service = UserSyncService(db, lambda user: boxes[user.id])
    service.sync_gmail_for_user(A)
    service.sync_gmail_for_user(B)
    with db.transaction() as session:
        own = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 0))
        other = session.scalar(select(Announcement).where(
            Announcement.user_id == B.id, Announcement.source_index == 0))
        own.source_category = other.source_category = '獎學金申請'
        own.category = other.category = None
        own.category_rule_version = other.category_rule_version = None
        kept = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 1))
        kept.category = '行政通知'

    boxes[1].messages = {}
    result = service.sync_gmail_for_user(A)
    assert result['emails_found'] == 0
    with db.transaction() as session:
        own = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 0))
        other = session.scalar(select(Announcement).where(
            Announcement.user_id == B.id, Announcement.source_index == 0))
        kept = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 1))
        assert own.category == '獎學金'
        assert other.category is None
        assert kept.category == '行政通知'


def test_unresolved_backfill_is_not_rechecked_on_every_sync(database, monkeypatch):
    db, _ = database
    box = FakeMailbox({'a': mail('a')})
    service = UserSyncService(db, lambda user: box)
    service.sync_gmail_for_user(A)
    with db.transaction() as session:
        row = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 0))
        row.source_category = '校園訊息'
        row.title = '校園最新消息'
        row.category = None
        row.category_rule_version = None

    box.messages = {}
    service.sync_gmail_for_user(A)
    with db.transaction() as session:
        row = session.scalar(select(Announcement).where(
            Announcement.user_id == A.id, Announcement.source_index == 0))
        assert row.category is None

    def rechecked(*_):
        raise AssertionError('unresolved announcement was rechecked')
    monkeypatch.setattr('app.database.user_mail.classify_category', rechecked)
    assert service.sync_gmail_for_user(A)['emails_found'] == 0


def test_user_data_isolation_and_same_message_id_allowed(database):
    db, _ = database
    boxes = {1: FakeMailbox({'shared':mail('shared')}), 2: FakeMailbox({'shared':mail('shared')})}
    service = UserSyncService(db, lambda user: boxes[user.id])
    first = service.sync_gmail_for_user(A)
    assert first['emails_processed'] == 1 and first['announcements_created'] == 3
    with db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Email).where(Email.user_id == 2)) == 0
        assert session.scalar(select(func.count()).select_from(Announcement).where(Announcement.user_id == 2)) == 0
    second = service.sync_gmail_for_user(B)
    assert second['database_counts'] == {'emails':1, 'announcements':3, 'failed_emails':0}
    with db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Email)) == 2
        for row in session.scalars(select(Announcement)):
            assert session.get(Email, row.email_id).user_id == row.user_id
        row = session.scalar(select(Announcement).where(Announcement.user_id == 1, Announcement.source_index == 0))
        assert row.deadline == date(2026,10,8)
        assert row.original_text and row.date_evidence


def test_repeat_sync_skips_download_and_releases_lease(database):
    db, _ = database
    box = FakeMailbox({'same':mail('same')})
    service = UserSyncService(db, lambda user: box)
    service.sync_gmail_for_user(A)
    result = service.sync_gmail_for_user(A)
    assert result['emails_skipped'] == 1 and result['announcements_created'] == 0
    assert box.reads == ['same'] and box.closed
    with db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(SyncLease)) == 0


def test_one_failure_continues_sanitizes_and_retry_recovers(database):
    db, _ = database
    box = FakeMailbox({'bad':GmailError('private body token marker'), 'good':mail('good')})
    service = UserSyncService(db, lambda user: box)
    result = service.sync_gmail_for_user(A)
    assert (result['emails_found'],result['emails_processed'],result['emails_failed']) == (2,1,1)
    assert 'private' not in str(result)
    with db.transaction() as session:
        row = session.scalar(select(Email).where(Email.user_id == 1,Email.gmail_message_id == 'bad'))
        assert row.last_error == 'PROCESSING_FAILED' and row.status == 'failed'
    box.messages['bad'] = mail('bad')
    result = service.sync_gmail_for_user(A)
    assert result['emails_processed'] == 1 and result['emails_skipped'] == 1
    assert result['database_counts']['emails'] == 2
    with db.transaction() as session:
        assert session.scalar(select(Email).where(Email.gmail_message_id == 'bad')).last_error is None


def test_auth_failure_during_read_is_reported_with_partial_result(database):
    db, _ = database
    box = FakeMailbox({'good':mail('good'), 'expired':GmailReauthorizationRequired('GMAIL_REAUTHORIZE')})
    result = UserSyncService(db, lambda user:box).sync_gmail_for_user(A)
    assert result['reauthorization_required'] is True
    assert result['emails_processed'] == 1 and result['emails_failed'] == 1


def test_failed_reparse_rolls_back_previous_snapshot(database):
    db, _ = database
    box = FakeMailbox({'same':mail('same')})
    UserSyncService(db, lambda user:box, parser_version='v1').sync_gmail_for_user(A)
    def broken(email):
        result = parse_email(email)
        result.announcements[1].source_index = 0
        result.announcements[0].title = 'must-not-persist'
        return result
    result = UserSyncService(db, lambda user:box, parser=broken,parser_version='v2').sync_gmail_for_user(A)
    assert result['emails_failed'] == 1
    with db.transaction() as session:
        email = session.scalar(select(Email))
        assert email.parser_version == 'v1' and email.status == 'processed'
        assert email.last_error == 'DATABASE_WRITE_FAILED'
        assert len(session.scalars(select(Announcement)).all()) == 3
        assert not session.scalar(select(Announcement).where(Announcement.title == 'must-not-persist'))


def test_wrong_message_identity_not_persisted(database):
    db, _ = database
    result = UserSyncService(db,lambda user:FakeMailbox({'requested':mail('different')})).sync_gmail_for_user(A)
    assert result['emails_failed'] == 1
    with db.transaction() as session:
        row = session.scalar(select(Email))
        assert row.gmail_message_id == 'requested' and row.html_body is None
        assert row.last_error == 'EMAIL_ID_MISMATCH'


def test_worker_failure_releases_lease(database):
    db, _ = database
    def unavailable(user):
        raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
    with pytest.raises(GmailReauthorizationRequired):
        UserSyncService(db, unavailable).sync_gmail_for_user(A)
    lease = UserSyncLease(db, 1)
    lease.acquire()
    lease.release()


def test_cross_worker_same_user_blocked_while_other_user_can_sync(database):
    db, _ = database
    entered, release = Event(), Event()
    class SlowBox(FakeMailbox):
        def list_message_ids(self, limit):
            entered.set()
            assert release.wait(5)
            return super().list_message_ids(limit)
    clone = MultiUserDatabase(db.engine.url)
    try:
        service = UserSyncService(db, lambda user: SlowBox({'a':mail('a')}))
        other = UserSyncService(clone, lambda user: FakeMailbox({'b':mail('b')}))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.sync_gmail_for_user, A)
            try:
                assert entered.wait(3)
                with pytest.raises(SyncBusy):
                    other.sync_gmail_for_user(A)
                assert other.sync_gmail_for_user(B)['emails_processed'] == 1
            finally:
                release.set()
            assert future.result(timeout=5)['emails_processed'] == 1
    finally:
        clone.close()


def test_expired_worker_cannot_write_or_release_new_owner(database):
    db, _ = database
    old = UserSyncLease(db,1)
    old.acquire()
    with db.transaction() as session:
        session.execute(update(SyncLease).where(SyncLease.user_id==1).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
    new = UserSyncLease(db,1)
    new.acquire()
    repo = UserMailRepository(db,1,old)
    with pytest.raises(SyncLeaseLost):
        repo.save_processed(mail('a'),parse_email(mail('a')),'v1')
    old.release()
    new.heartbeat()
    with db.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Email)) == 0
    new.release()


@pytest.mark.parametrize('limit',[0,101,True,'5'])
def test_service_limit_validation(database,limit):
    db, _ = database
    with pytest.raises(ValueError):
        UserSyncService(db,lambda user:pytest.fail('must not connect')).sync_gmail_for_user(A,limit)
