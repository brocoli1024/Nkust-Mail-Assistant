"""Revocable, absolute-expiry server sessions. Cookies contain only random IDs."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets

from dotenv import dotenv_values
from fastapi import HTTPException, Request
from sqlalchemy import delete, select

from app.config import ROOT
from app.auth.errors import AuthError
from app.models.multi_user import User, WebSession

SESSION_SECONDS = 8 * 60 * 60


def load_session_secret():
    return ({**dotenv_values(ROOT / '.env'), **os.environ}.get('SESSION_SECRET') or '')


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{43}', value) is not None


def session_hash(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    display_name: str | None
    google_user_id: str


class SessionService:
    def __init__(self, database, secret, *, secure, now=None):
        if not isinstance(secret, str) or len(secret.encode()) < 32:
            raise ValueError('SESSION_SECRET must contain at least 32 bytes')
        self.database = database
        self.secret = secret.encode()
        self.secure = secure
        self.cookie_name = '__Host-nkust_session' if secure else 'nkust_session'
        self.now = now or (lambda: datetime.now(timezone.utc))

    @property
    def cookie_options(self):
        return dict(httponly=True, secure=self.secure, samesite='lax', path='/')

    def create(self, user_id, previous=None, *, google_user_id=None):
        value = secrets.token_urlsafe(32)
        now = self.now()
        with self.database.transaction() as session:
            if google_user_id is not None:
                subject = session.scalar(select(User.google_user_id).where(User.id == user_id).with_for_update())
                if subject != google_user_id:
                    raise AuthError('OAUTH_ACCOUNT_CHANGED')
            session.execute(delete(WebSession).where(WebSession.expires_at <= now))
            if valid_id(previous):
                session.execute(delete(WebSession).where(WebSession.id_hash == session_hash(previous)))
            session.add(WebSession(id_hash=session_hash(value), user_id=user_id,
                                   created_at=now, expires_at=now + timedelta(seconds=SESSION_SECONDS)))
        return value

    def resolve(self, value):
        if not valid_id(value):
            return None
        with self.database.transaction() as session:
            row = session.execute(select(User.id, User.email, User.display_name, User.google_user_id).join(
                WebSession, WebSession.user_id == User.id).where(
                    WebSession.id_hash == session_hash(value), WebSession.expires_at > self.now())).first()
            return CurrentUser(*row) if row else None

    def revoke(self, value):
        if valid_id(value):
            with self.database.transaction() as session:
                session.execute(delete(WebSession).where(WebSession.id_hash == session_hash(value)))

    def csrf(self, value):
        if not valid_id(value):
            raise ValueError('Invalid session ID')
        return hmac.new(self.secret, ('csrf:' + value).encode(), hashlib.sha256).hexdigest()

    def valid_csrf(self, value, supplied):
        return (valid_id(value) and isinstance(supplied, str) and
                re.fullmatch(r'[a-f0-9]{64}', supplied) is not None and
                hmac.compare_digest(self.csrf(value), supplied))

    def set_cookie(self, response, value):
        response.set_cookie(self.cookie_name, value, max_age=SESSION_SECONDS, **self.cookie_options)

    def clear_cookie(self, response):
        response.delete_cookie(self.cookie_name, **self.cookie_options)


def current_user(request: Request):
    sessions = request.app.state.sessions
    user = sessions.resolve(request.cookies.get(sessions.cookie_name))
    if user is None:
        raise HTTPException(401, '請先登入。')
    return user


def current_page_user(request: Request):
    try:
        return current_user(request)
    except HTTPException as exc:
        raise HTTPException(303, '請先登入。', headers={'Location': '/login'}) from None
