"""Encrypt, decrypt, refresh, revoke and persist account-bound credentials."""
from datetime import datetime, timedelta, timezone
import json

from cryptography.fernet import Fernet
from sqlalchemy import select, update

from app.auth.errors import AuthError, ReauthorizationRequired
from app.auth.google_oauth import normalized_scopes
from app.models.multi_user import User, OAuthAccount, SyncLease


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class TokenService:
    def __init__(self, database, key, google):
        self.database = database
        self.cipher = Fernet(key.encode('ascii'))
        self.google = google

    def encrypt(self, value, *, context):
        return self.cipher.encrypt(json.dumps({'context': context, 'value': value}).encode()).decode('ascii')

    def decrypt(self, value, *, context):
        try:
            data = json.loads(self.cipher.decrypt(value.encode('ascii')))
            if data['context'] != context or not isinstance(data['value'], str):
                raise ValueError()
            return data['value']
        except Exception:
            raise AuthError('OAUTH_CREDENTIAL_UNREADABLE') from None

    @staticmethod
    def context(user_id, kind):
        return f'google:{user_id}:{kind}'

    def save_identity(self, identity, tokens):
        normalized_scopes(tokens.scopes)
        with self.database.transaction() as session:
            user = session.scalar(select(User).where(User.google_user_id == identity['sub']).with_for_update())
            if user is None:
                user = User(google_user_id=identity['sub'], email=identity['email'])
                session.add(user)
                session.flush()
            elif session.scalar(select(SyncLease.user_id).where(
                    SyncLease.user_id == user.id, SyncLease.expires_at > datetime.now(timezone.utc))) is not None:
                # The user-row lock serializes this check with identity-bound
                # lease acquisition. Reconnect cannot replace a grant during
                # sync or between revocation and account removal.
                raise AuthError('OAUTH_ACCOUNT_BUSY')
            user.email = identity['email']
            user.display_name = identity.get('name') if isinstance(identity.get('name'), str) else None
            user.avatar_url = identity.get('picture') if isinstance(identity.get('picture'), str) else None
            account = session.scalar(select(OAuthAccount).where(
                OAuthAccount.user_id == user.id, OAuthAccount.provider == 'google').with_for_update())
            if account is None:
                account = OAuthAccount(user_id=user.id, provider='google', provider_user_id=identity['sub'])
                session.add(account)
            elif account.provider_user_id != identity['sub']:
                raise AuthError('OAUTH_ACCOUNT_MISMATCH')
            if tokens.refresh_token:
                account.refresh_token_encrypted = self.encrypt(tokens.refresh_token, context=self.context(user.id, 'refresh'))
            elif not account.refresh_token_encrypted:
                raise ReauthorizationRequired('OAUTH_REAUTHORIZE')
            else:
                # Do not preserve unusable credentials after a key change.
                self.decrypt(account.refresh_token_encrypted, context=self.context(user.id, 'refresh'))
            account.access_token_encrypted = self.encrypt(tokens.access_token, context=self.context(user.id, 'access'))
            account.expires_at = tokens.expires_at
            account.scopes = tokens.scopes
            session.flush()
            return user.id

    def _account(self, session, user_id, *, google_user_id=None):
        if type(user_id) is not int or user_id < 1:
            raise ReauthorizationRequired('OAUTH_REAUTHORIZE')
        statement = select(OAuthAccount).join(User, User.id == OAuthAccount.user_id).where(
            OAuthAccount.user_id == user_id, OAuthAccount.provider == 'google',
            OAuthAccount.provider_user_id == User.google_user_id)
        if google_user_id is not None:
            statement = statement.where(User.google_user_id == google_user_id)
        account = session.scalar(statement.with_for_update())
        if account is None or not account.refresh_token_encrypted:
            raise ReauthorizationRequired('OAUTH_REAUTHORIZE')
        normalized_scopes(account.scopes)
        return account

    def access_token(self, user_id, *, rejected_token=None, google_user_id=None):
        with self.database.transaction() as session:
            account = self._account(session, user_id, google_user_id=google_user_id)
            if (account.access_token_encrypted and account.expires_at and
                    utc(account.expires_at) > datetime.now(timezone.utc) + timedelta(seconds=60)):
                cached = self.decrypt(account.access_token_encrypted, context=self.context(user_id, 'access'))
                # A 401 forces refresh only if the rejected token is still current.
                # Another worker may already have refreshed this account.
                if rejected_token is None or cached != rejected_token:
                    return cached
            old_refresh = account.refresh_token_encrypted
            refresh = self.decrypt(old_refresh, context=self.context(user_id, 'refresh'))
            tokens = self.google.refresh(refresh, account.scopes)
            # CAS prevents a concurrent disconnect/reconnect from being overwritten.
            result = session.execute(update(OAuthAccount).where(
                OAuthAccount.id == account.id, OAuthAccount.user_id == user_id,
                OAuthAccount.refresh_token_encrypted == old_refresh,
                OAuthAccount.access_token_encrypted == account.access_token_encrypted,
            ).values(access_token_encrypted=self.encrypt(tokens.access_token, context=self.context(user_id, 'access')),
                     refresh_token_encrypted=self.encrypt(tokens.refresh_token or refresh, context=self.context(user_id, 'refresh')),
                     expires_at=tokens.expires_at, scopes=tokens.scopes))
            if result.rowcount != 1:
                raise ReauthorizationRequired('OAUTH_REAUTHORIZE')
            return tokens.access_token

    def revoke(self, user_id, *, google_user_id=None):
        with self.database.transaction() as session:
            account = self._account(session, user_id, google_user_id=google_user_id)
            old_refresh = account.refresh_token_encrypted
            self.google.revoke(self.decrypt(old_refresh, context=self.context(user_id, 'refresh')))
            session.execute(update(OAuthAccount).where(
                OAuthAccount.id == account.id, OAuthAccount.user_id == user_id,
                OAuthAccount.refresh_token_encrypted == old_refresh,
            ).values(access_token_encrypted=None, refresh_token_encrypted=None, expires_at=None))
