"""User-bound orchestration around the existing parser/sync loop."""
from sqlalchemy.exc import SQLAlchemyError

from app.core.session import CurrentUser
from app.database.user_mail import UserMailRepository, UserSyncLease, safe_error
from app.services.announcement_parser import parse_email
from app.services.sync_service import SyncService, PARSER_VERSION


class UserSyncService:
    def __init__(self, database, gmail_factory, *, parser=parse_email, parser_version=PARSER_VERSION):
        self.database = database
        self.gmail_factory = gmail_factory
        self.parser = parser
        self.parser_version = parser_version

    def sync_gmail_for_user(self, user, limit=5):
        if (not isinstance(user, CurrentUser) or type(user.id) is not int or user.id < 1 or
                not isinstance(user.google_user_id, str) or not user.google_user_id):
            raise ValueError('Authenticated CurrentUser required')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Sync limit must be between 1 and 100')
        lease = UserSyncLease(self.database, user.id, google_user_id=user.google_user_id)
        lease.acquire()
        try:
            repository = UserMailRepository(self.database, user.id, lease)
            with self.gmail_factory(user) as gmail:
                result = SyncService(gmail, repository, parser=self.parser,
                                     parser_version=self.parser_version).sync(limit)
            repository.backfill_categories()
            errors = [{'gmail_message_id': e['gmail_message_id'], 'error': safe_error(e['error']),
                       'failure_recorded': 'persistence_error' not in e} for e in result.errors]
            return {
                'emails_found': result.matched,
                'emails_processed': result.processed,
                'emails_skipped': result.skipped,
                'emails_failed': result.failed,
                'announcements_created': result.announcements_written,
                'reauthorization_required': any(e['error'] == 'GMAIL_REAUTHORIZE' for e in errors),
                'errors': errors,
                'database_counts': result.database_counts,
            }
        finally:
            try:
                lease.release()
            except SQLAlchemyError:
                # Do not overwrite a completed result/original exception. A crashed
                # worker or unavailable DB recovers when this bounded lease expires.
                pass
