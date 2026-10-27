"""Maintainer-only synchronization into independent public tables."""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from sqlalchemy import select, update, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.public_announcements import PublicAnnouncement as P, PublicSourceState as S, PublicSyncRun as R
from app.services.category_rules import classify_category, RULE_VERSION as CATEGORY_VERSION
from app.services.public_source import SOURCE_KEY, PublicSourceError, fetch_feed, parse_feed, normalize_public_url


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    status: str = 'success'


class SourceLease:
    def __init__(self, database, *, now=None):
        self.database, self.owner = database, secrets.token_hex(24)
        self.clock = (lambda: now) if now is not None else utcnow

    def acquire(self):
        now = self.clock()
        with self.database.transaction() as session:
            insert = pg_insert if session.bind.dialect.name == 'postgresql' else sqlite_insert
            session.execute(insert(S).values(source_key=SOURCE_KEY, next_history_page=1,
                history_status='not_started').on_conflict_do_nothing(index_elements=['source_key']))
            result = session.execute(update(S).where(S.source_key == SOURCE_KEY,
                or_(S.lease_owner.is_(None), S.lease_expires_at <= now)).values(
                lease_owner=self.owner, lease_expires_at=now + timedelta(minutes=10)))
            if result.rowcount != 1:
                raise PublicSourceError('PUBLIC_SYNC_BUSY')

    def verify(self, session):
        state = session.scalar(select(S).where(S.source_key == SOURCE_KEY).with_for_update())
        if (not state or state.lease_owner != self.owner or not state.lease_expires_at
                or aware(state.lease_expires_at) <= self.clock()):
            raise PublicSourceError('PUBLIC_SYNC_LEASE_LOST')
        return state

    def release(self):
        with self.database.transaction() as session:
            session.execute(update(S).where(S.source_key == SOURCE_KEY, S.lease_owner == self.owner)
                .values(lease_owner=None, lease_expires_at=None))


def store_entries(session, entries, now, result):
    """Call only while holding and verifying a SourceLease in this transaction."""
    dates = []
    for entry in entries:
        url = normalize_public_url(entry.url)
        row = session.scalar(select(P).where(P.source_key == SOURCE_KEY, P.canonical_url == url))
        # A listing without an excerpt/date must not erase richer RSS data.
        excerpt = entry.excerpt or (row.excerpt if row else '')
        published = aware(entry.published_at) or (aware(row.published_at) if row else None)
        external = entry.external_id or (row.external_id if row else None)
        values = dict(title=entry.title, excerpt=excerpt, published_at=published, external_id=external)
        fingerprint = hashlib.sha256(json.dumps(dict(values, published_at=published.isoformat() if published else None),
            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if row is None:
            row = P(source_key=SOURCE_KEY, canonical_url=url, first_seen_at=now)
            session.add(row)
            result.added += 1
        elif row.content_hash == fingerprint:
            result.unchanged += 1
        else:
            result.updated += 1
        if row.content_hash != fingerprint:
            for key, value in values.items():
                setattr(row, key, value)
            row.content_hash = fingerprint
            row.category = classify_category('', entry.title)
            row.category_rule_version = CATEGORY_VERSION
            row.updated_at = now
        row.last_seen_at = now
        if published:
            dates.append(published)
        session.flush()  # same-response duplicate URLs see the newly inserted row
    return min(dates) if dates else None


def begin_run(database, lease, mode):
    with database.transaction() as session:
        lease.verify(session)
        row = R(source_key=SOURCE_KEY, mode=mode, status='running', started_at=lease.clock())
        session.add(row)
        session.flush()
        return row.id


def finish_run(database, run_id, result, error_code=None, *, now=None):
    with database.transaction() as session:
        row = session.get(R, run_id)
        for key, value in asdict(result).items():
            setattr(row, key, value)
        row.finished_at = now or utcnow()
        row.error_code = error_code


def sync_recent(database, *, source=None, now=None) -> SyncResult:
    lease = SourceLease(database, now=now)
    lease.acquire()
    run_id = None
    result, error = SyncResult(), None
    try:
        run_id = begin_run(database, lease, 'recent')
        entries = parse_feed((source or fetch_feed)())
        with database.transaction() as session:
            state = lease.verify(session)
            oldest = store_entries(session, entries, lease.clock(), result)
            result.failed = entries.failed
            if entries.failed:
                result.status, error = 'partial', 'PUBLIC_SOURCE_PARTIAL'
            else:
                state.last_success_at = lease.clock()
            if oldest and (not state.oldest_seen_at or oldest < aware(state.oldest_seen_at)):
                state.oldest_seen_at = oldest
    except Exception as exc:
        result = SyncResult(failed=1, status='failed')
        error = str(exc) if isinstance(exc, PublicSourceError) else 'PUBLIC_SYNC_FAILED'
    finally:
        try:
            if run_id is not None:
                finish_run(database, run_id, result, error, now=lease.clock())
        finally:
            lease.release()
    return result
