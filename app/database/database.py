"""SQLite persistence with one atomic transaction per email."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.models import Base
from app.models.email import Email
from app.models.announcement import Announcement
from app.models.analysis import Analysis
from app.models.scrape import Scrape

CATEGORIES = {'課程', '選課', '獎學金', '競賽', '講座', '活動', '證照', 'TOEIC', '實習', '徵才', '交換學生', '行政通知', '其他'}


class Database:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(URL.create('sqlite', database=str(path)), connect_args={'timeout': 10})

        @event.listens_for(self.engine, 'connect')
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()

        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        with Session(self.engine) as session, session.begin():
            # Reserve the SQLite writer before rechecking state; concurrent syncs cannot race.
            session.execute(text('BEGIN IMMEDIATE'))
            yield session

    def is_processed(self, message_id, version):
        with Session(self.engine) as session:
            return session.scalar(select(Email.id).where(
                Email.gmail_message_id == message_id, Email.status == 'processed',
                Email.parser_version == version)) is not None

    @staticmethod
    def _copy_email(row, email):
        row.subject = email.subject
        row.sender = email.sender
        row.received_at = email.received_at.isoformat()
        row.html_body = email.html_body
        row.text_body = email.text_body

    def save_processed(self, email, result, version, *, force=False):
        if not result.announcements:
            raise ValueError('EMPTY_PARSE_RESULT: refusing to mark an empty parse successful')
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as session:
            row = session.scalar(select(Email).where(Email.gmail_message_id == email.gmail_message_id))
            if row and row.status == 'processed' and row.parser_version == version and not force:
                return False
            if row is None:
                row = Email(gmail_message_id=email.gmail_message_id, status='failed')
                session.add(row)
                session.flush()
            self._copy_email(row, email)
            session.execute(delete(Announcement).where(Announcement.email_id == row.id))
            for item in result.announcements:
                session.add(Announcement(
                    email_id=row.id, source_index=item.source_index,
                    source_fingerprint=item.source_fingerprint, department=item.department,
                    source_category=item.source_category,
                    category=item.source_category if item.source_category in CATEGORIES else None,
                    title=item.title, original_text=item.original_text, original_html=item.original_html,
                    url=item.url, event_date=item.event_date, deadline=item.deadline,
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
        with self.transaction() as session:
            row = session.scalar(select(Email).where(Email.gmail_message_id == message_id))
            if row is None:
                row = Email(gmail_message_id=message_id, status='failed')
                session.add(row)
            # A failed reparse must preserve the previous successful snapshot and version.
            if row.status != 'processed' and email is not None:
                self._copy_email(row, email)
            row.last_error = error

    def counts(self):
        with Session(self.engine) as session:
            return {
                'emails': session.scalar(select(func.count()).select_from(Email)),
                'announcements': session.scalar(select(func.count()).select_from(Announcement)),
                'failed_emails': session.scalar(select(func.count()).select_from(Email).where(Email.status == 'failed')),
            }

    def close(self):
        self.engine.dispose()
