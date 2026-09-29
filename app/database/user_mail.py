"""User-scoped persistence adapter for the unchanged SyncService contract."""
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import secrets

from sqlalchemy import delete, select, func, or_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.multi_user import SyncLease, Email, Announcement
from app.services.category_rules import RULE_VERSION, classify_category

LEASE_SECONDS = 300


class SyncBusy(RuntimeError):
    pass


class SyncLeaseLost(RuntimeError):
    pass


def safe_error(error):
    # Do not persist arbitrary exception messages/SQL parameters/mail fragments.
    prefix = str(error).split(':', 1)[0]
    allowed = {
        'GMAIL_REAUTHORIZE', 'GMAIL_CREDENTIALS_UNAVAILABLE', 'GMAIL_API_ERROR',
        'GMAIL_REQUEST_FAILED', 'GMAIL_RESPONSE_INVALID', 'EMAIL_ID_MISMATCH',
        'EMAIL_FORMAT_ERROR', 'EMAIL_DATE_ERROR', 'MIME_DECODE_ERROR',
        'MIME_BODY_MISSING', 'MIME_ATTACHMENT_ERROR', 'MIME_ATTACHMENT_REQUIRED',
        'ANNOUNCEMENT_EMPTY_FIELD', 'TABLE_DUPLICATE_HEADER', 'TABLE_SPAN_UNSUPPORTED',
        'TABLE_ROW_INVALID', 'TABLE_NOT_FOUND', 'TABLE_EMPTY', 'PLAIN_LAYOUT_UNKNOWN',
        'PLAIN_BLOCK_INVALID', 'DATABASE_WRITE_FAILED', 'EMPTY_PARSE_RESULT',
    }
    return prefix if prefix in allowed else 'PROCESSING_FAILED'


class UserSyncLease:
    def __init__(self, database, user_id, *, now=None):
        self.database = database
        self.user_id = user_id
        self.owner = secrets.token_hex(32)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def acquire(self):
        now = self.now()
        insert = sqlite_insert if self.database.engine.dialect.name == 'sqlite' else pg_insert
        statement = insert(SyncLease).values(user_id=self.user_id, owner=self.owner,
                                             expires_at=now + timedelta(seconds=LEASE_SECONDS))
        statement = statement.on_conflict_do_update(
            index_elements=[SyncLease.user_id],
            set_={'owner': self.owner, 'expires_at': now + timedelta(seconds=LEASE_SECONDS)},
            where=SyncLease.expires_at <= now,
        ).returning(SyncLease.user_id)
        with self.database.transaction() as session:
            acquired = session.scalar(statement)
        if acquired is None:
            raise SyncBusy('SYNC_BUSY')

    def fence(self, session):
        now = self.now()
        result = session.execute(update(SyncLease).where(
            SyncLease.user_id == self.user_id, SyncLease.owner == self.owner,
            SyncLease.expires_at > now,
        ).values(expires_at=now + timedelta(seconds=LEASE_SECONDS)))
        if result.rowcount != 1:
            raise SyncLeaseLost('SYNC_LEASE_LOST')

    def heartbeat(self):
        with self.database.transaction() as session:
            self.fence(session)

    def release(self):
        with self.database.transaction() as session:
            session.execute(delete(SyncLease).where(SyncLease.user_id == self.user_id, SyncLease.owner == self.owner))


class UserMailRepository:
    def __init__(self, database, user_id, lease):
        if type(user_id) is not int or user_id < 1 or lease.user_id != user_id:
            raise ValueError('User-scoped repository requires matching lease')
        self.database = database
        self.user_id = user_id
        self.lease = lease

    def _email(self, message_id):
        return select(Email).where(Email.user_id == self.user_id, Email.gmail_message_id == message_id)

    def is_processed(self, message_id, version):
        with self.database.transaction() as session:
            self.lease.fence(session)
            return session.scalar(self._email(message_id).where(
                Email.status == 'processed', Email.parser_version == version)) is not None

    @staticmethod
    def _copy_email(row, email):
        if email.received_at.tzinfo is None:
            raise ValueError('Received timestamp requires timezone')
        row.subject = email.subject
        row.sender = email.sender
        row.received_at = email.received_at.astimezone(timezone.utc)
        row.html_body = email.html_body
        row.text_body = email.text_body

    def save_processed(self, email, result, version, *, force=False):
        if not result.announcements:
            raise ValueError('EMPTY_PARSE_RESULT: no announcements')
        now = datetime.now(timezone.utc)
        with self.database.transaction() as session:
            self.lease.fence(session)
            row = session.scalar(self._email(email.gmail_message_id))
            if row and row.status == 'processed' and row.parser_version == version and not force:
                return False
            if row is None:
                row = Email(user_id=self.user_id, gmail_message_id=email.gmail_message_id, status='failed')
                session.add(row)
                session.flush()
            self._copy_email(row, email)
            session.execute(delete(Announcement).where(
                Announcement.user_id == self.user_id, Announcement.email_id == row.id))
            for item in result.announcements:
                session.add(Announcement(
                    user_id=self.user_id, email_id=row.id, source_index=item.source_index,
                    source_fingerprint=item.source_fingerprint, department=item.department,
                    source_category=item.source_category,
                    category=classify_category(item.source_category, item.title),
                    category_rule_version=RULE_VERSION,
                    title=item.title, original_text=item.original_text, original_html=item.original_html,
                    url=item.url, event_date=date.fromisoformat(item.event_date) if item.event_date else None,
                    deadline=date.fromisoformat(item.deadline) if item.deadline else None,
                    date_evidence=[asdict(e) for e in item.date_evidence],
                    date_inferred=any(e.year_inferred for e in item.date_evidence),
                    created_at=now, updated_at=now,
                ))
            row.status = 'processed'
            row.processed_at = now
            row.parser_version = version
            row.last_error = None
            row.warnings = result.warnings
            session.flush()
        return True

    def record_failure(self, message_id, error, email=None):
        with self.database.transaction() as session:
            self.lease.fence(session)
            row = session.scalar(self._email(message_id))
            if row is None:
                row = Email(user_id=self.user_id, gmail_message_id=message_id, status='failed')
                session.add(row)
            if row.status != 'processed' and email is not None:
                # A failed parse does not justify storing unvalidated timestamp data.
                if email.received_at.tzinfo is not None:
                    self._copy_email(row, email)
            row.last_error = safe_error(error)

    def backfill_categories(self):
        """Classify this user's existing pending announcements in bounded batches."""
        assigned = 0
        last_id = 0
        while True:
            with self.database.transaction() as session:
                self.lease.fence(session)
                rows = session.scalars(select(Announcement).where(
                    Announcement.user_id == self.user_id, Announcement.category.is_(None),
                    or_(Announcement.category_rule_version.is_(None),
                        Announcement.category_rule_version != RULE_VERSION),
                    Announcement.id > last_id).order_by(Announcement.id).limit(100)).all()
                if not rows:
                    return assigned
                for row in rows:
                    last_id = row.id
                    category = classify_category(row.source_category, row.title)
                    row.category_rule_version = RULE_VERSION
                    if category:
                        row.category = category
                        row.updated_at = datetime.now(timezone.utc)
                        assigned += 1

    def counts(self):
        with self.database.transaction() as session:
            return {
                'emails': session.scalar(select(func.count()).select_from(Email).where(Email.user_id == self.user_id)),
                'announcements': session.scalar(select(func.count()).select_from(Announcement).where(Announcement.user_id == self.user_id)),
                'failed_emails': session.scalar(select(func.count()).select_from(Email).where(
                    Email.user_id == self.user_id, Email.status == 'failed')),
            }
