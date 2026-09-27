from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets

from sqlalchemy import delete

from app.auth.errors import AuthError
from app.models.multi_user import OAuthAttempt

TTL_SECONDS = 600
COOKIE = 'nkust_oauth_browser'


def digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


class OAuthAttempts:
    def __init__(self, database, tokens):
        self.database = database
        self.tokens = tokens

    def create(self):
        state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        hashed = digest(state)
        now = datetime.now(timezone.utc)
        payload = self.tokens.encrypt(json.dumps({'nonce': nonce, 'verifier': verifier}), context='attempt:' + hashed)
        with self.database.transaction() as session:
            session.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at <= now))
            session.add(OAuthAttempt(state_hash=hashed, browser_hash=digest(browser),
                                     context_encrypted=payload, expires_at=now + timedelta(seconds=TTL_SECONDS)))
        return state, browser, nonce, verifier

    def consume(self, state, browser):
        if not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{43}', v) for v in (state, browser)):
            raise AuthError('OAUTH_STATE_INVALID')
        hashed = digest(state)
        # DELETE RETURNING is atomic across workers; commit before contacting Google.
        with self.database.transaction() as session:
            encrypted = session.scalar(delete(OAuthAttempt).where(
                OAuthAttempt.state_hash == hashed, OAuthAttempt.browser_hash == digest(browser),
                OAuthAttempt.expires_at > datetime.now(timezone.utc),
            ).returning(OAuthAttempt.context_encrypted))
        if encrypted is None:
            raise AuthError('OAUTH_STATE_INVALID')
        try:
            return json.loads(self.tokens.decrypt(encrypted, context='attempt:' + hashed))
        except AuthError:
            raise
        except Exception:
            raise AuthError('OAUTH_STATE_INVALID') from None
