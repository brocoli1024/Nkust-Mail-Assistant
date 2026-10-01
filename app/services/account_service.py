"""Remove one authenticated account under the same lease used by Gmail sync."""
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app.auth.errors import AuthError
from app.core.session import CurrentUser
from app.database.user_mail import UserSyncLease
from app.models.multi_user import User


def delete_account(database, tokens, user):
    if (not isinstance(user, CurrentUser) or type(user.id) is not int or user.id < 1 or
            not isinstance(user.google_user_id, str) or not user.google_user_id):
        raise ValueError('Authenticated CurrentUser required')
    lease = UserSyncLease(database, user.id, google_user_id=user.google_user_id)
    lease.acquire()
    try:
        disconnected = True
        try:
            tokens.revoke(user.id, google_user_id=user.google_user_id)
        except AuthError:
            # Local removal must remain possible after expired/unreadable grants.
            # Never copy provider errors into a page or log.
            disconnected = False
        with database.transaction() as session:
            lease.fence(session)
            # Foreign-key cascades remove mail, announcements, credentials,
            # derived data, sessions and this user's lease in one transaction.
            session.execute(delete(User).where(User.id == user.id))
        return disconnected
    finally:
        try:
            lease.release()
        except SQLAlchemyError:
            pass
