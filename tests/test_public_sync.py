from dataclasses import replace
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
import pytest

from tests.test_multi_user_database import database
from tests.test_public_source import feed, item
from app.models.public_announcements import PublicAnnouncement as P, PublicSourceState as S, PublicSyncRun as R
from app.services.public_source import PublicSourceError
from app.services.public_sync import sync_recent, SourceLease

NOW = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)


def test_sync_repeat_update_and_source_failure(database):
    db, _ = database
    source = lambda: feed(item(), item(url='https://osa.nkust.edu.tw/b'))
    assert sync_recent(db, source=source, now=NOW).added == 2
    assert sync_recent(db, source=source, now=NOW+timedelta(minutes=1)).unchanged == 2
    changed = lambda: feed(item(excerpt='新內容'), item(url='https://osa.nkust.edu.tw/b'))
    assert sync_recent(db, source=changed, now=NOW+timedelta(minutes=2)).updated == 1
    def fail():
        raise PublicSourceError('PUBLIC_SOURCE_UNAVAILABLE')
    assert sync_recent(db, source=fail, now=NOW+timedelta(minutes=3)).status == 'failed'
    with db.transaction() as s:
        rows = s.scalars(select(P).order_by(P.id)).all()
        assert len(rows) == 2 and rows[0].excerpt == '新內容'
        first_seen = rows[0].first_seen_at
        last_success = s.get(S,'nkust-latest').last_success_at
        assert (first_seen.replace(tzinfo=timezone.utc) if first_seen.tzinfo is None else first_seen) == NOW
        assert (last_success.replace(tzinfo=timezone.utc) if last_success.tzinfo is None else last_success) == NOW+timedelta(minutes=2)
        assert s.scalars(select(R).order_by(R.id)).all()[-1].error_code == 'PUBLIC_SOURCE_UNAVAILABLE'


def test_empty_and_partial_sources_are_not_marked_success(database):
    db, _ = database
    assert sync_recent(db, source=lambda: feed(), now=NOW).status == 'failed'
    result = sync_recent(db, source=lambda: feed(item(), item(url='https://evil.invalid/')), now=NOW)
    assert result.status == 'partial' and result.added == 1 and result.failed == 1
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').last_success_at is None


def test_lease_blocks_concurrency_expires_and_rejects_stale_writer(database):
    db, _ = database
    first=SourceLease(db,now=NOW)
    first.acquire()
    with pytest.raises(PublicSourceError,match='PUBLIC_SYNC_BUSY'):
        sync_recent(db,source=lambda:feed(item()),now=NOW)
    second=SourceLease(db,now=NOW+timedelta(minutes=11))
    second.acquire()
    first.release()
    with db.transaction() as s:
        with pytest.raises(PublicSourceError,match='PUBLIC_SYNC_LEASE_LOST'):
            first.verify(s)
        assert s.get(S,'nkust-latest').lease_owner == second.owner
    second.release()


def test_unexpected_errors_are_sanitized_and_lease_released(database):
    db,_=database
    def source(): raise RuntimeError('PRIVATE-MARKER')
    result=sync_recent(db,source=source,now=NOW)
    assert result.status=='failed'
    with db.transaction() as s:
        assert s.get(S,'nkust-latest').lease_owner is None
        assert 'PRIVATE-MARKER' not in s.scalar(select(R)).error_code
