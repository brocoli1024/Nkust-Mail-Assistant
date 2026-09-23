"""Bounded Gmail sync; completed emails are skipped before downloading their bodies."""
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

from app.services.announcement_parser import AnnouncementParseError, parse_email
from app.services.email_parser import EmailParseError
from app.services.gmail_service import GmailError

PARSER_VERSION = 'nkust-table-v1'


@dataclass
class SyncResult:
    matched: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    announcements_written: int = 0
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    database_counts: dict = field(default_factory=dict)


class SyncService:
    def __init__(self, gmail, database, *, parser=parse_email, parser_version=PARSER_VERSION):
        self.gmail = gmail
        self.database = database
        self.parser = parser
        self.parser_version = parser_version

    def sync(self, limit=5, *, force=False):
        return self.sync_ids(self.gmail.list_message_ids(limit), force=force)

    def sync_ids(self, message_ids, *, force=False):
        ids = list(dict.fromkeys(message_ids))
        report = SyncResult(matched=len(ids))
        for message_id in ids:
            email = None
            try:
                if not force and self.database.is_processed(message_id, self.parser_version):
                    report.skipped += 1
                    continue
                email = self.gmail.read_message(message_id)
                if email.gmail_message_id != message_id:
                    email = None
                    raise EmailParseError('EMAIL_ID_MISMATCH: retrieved email does not match requested ID')
                parsed = self.parser(email)
                saved = self.database.save_processed(email, parsed, self.parser_version, force=force)
                if saved:
                    report.processed += 1
                    report.announcements_written += len(parsed.announcements)
                    report.warnings.extend({'gmail_message_id': message_id, 'warning': w} for w in parsed.warnings)
                else:
                    report.skipped += 1
            except (GmailError, EmailParseError, AnnouncementParseError, SQLAlchemyError, ValueError) as exc:
                # SQLAlchemy exceptions can contain complete private SQL parameter values.
                error = 'DATABASE_WRITE_FAILED: transaction rolled back' if isinstance(exc, SQLAlchemyError) else str(exc)
                report.failed += 1
                entry = {'gmail_message_id': message_id, 'error': error}
                try:
                    self.database.record_failure(message_id, error, email)
                except SQLAlchemyError:
                    entry['persistence_error'] = 'Could not save failure state; rerun sync to retry'
                report.errors.append(entry)
        report.database_counts = self.database.counts()
        return report
