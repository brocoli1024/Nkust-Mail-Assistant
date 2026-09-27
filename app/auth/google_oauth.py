"""Google authorization code flow; tokens never travel to the frontend."""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.auth.config import WEB_SCOPES
from app.auth.errors import AuthError, ReauthorizationRequired

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
# Bound tolerance for small local clock differences; all identity checks remain enabled.
ID_TOKEN_CLOCK_SKEW_SECONDS = 30
ALIASES = {'https://www.googleapis.com/auth/userinfo.email': 'email',
           'https://www.googleapis.com/auth/userinfo.profile': 'profile'}


def normalized_scopes(value):
    if isinstance(value, str):
        value = value.split()
    if not isinstance(value, (tuple, list)) or any(not isinstance(s, str) for s in value):
        raise AuthError('OAUTH_SCOPE_MISMATCH')
    scopes = {ALIASES.get(s, s) for s in value}
    if scopes != set(WEB_SCOPES):
        raise AuthError('OAUTH_SCOPE_MISMATCH')
    return sorted(scopes)


@dataclass(frozen=True)
class Tokens:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    id_token: str | None = field(repr=False)
    expires_at: datetime
    scopes: list[str]


class GoogleOAuth:
    def __init__(self, settings, *, transport=None, id_request=None):
        self.settings = settings
        self.transport = transport
        self.id_request = id_request

    def authorization_url(self, state, nonce, verifier):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode()
        return AUTH_URL + '?' + urlencode({
            'client_id': self.settings.client_id, 'redirect_uri': self.settings.redirect_uri,
            'response_type': 'code', 'scope': ' '.join(WEB_SCOPES),
            'state': state, 'nonce': nonce, 'code_challenge': challenge,
            'code_challenge_method': 'S256', 'access_type': 'offline',
            'prompt': 'consent', 'include_granted_scopes': 'false',
        })

    def _post(self, endpoint, data):
        try:
            with httpx.Client(transport=self.transport, timeout=self.settings.timeout,
                              follow_redirects=False) as client:
                response = client.post(endpoint, data=data)
            if response.status_code == 200:
                if endpoint == REVOKE_URL:
                    return {}
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError()
                return result
            if endpoint == TOKEN_URL and response.status_code == 400:
                if response.json().get('error') == 'invalid_grant':
                    raise ReauthorizationRequired('OAUTH_REAUTHORIZE')
            raise AuthError('OAUTH_PROVIDER_FAILED')
        except AuthError:
            raise
        except Exception:
            # Never include request/response bodies or chained exceptions.
            raise AuthError('OAUTH_PROVIDER_FAILED') from None

    def _tokens(self, data, *, fallback_scopes=None, require_identity=False):
        try:
            access = data['access_token']
            refresh = data.get('refresh_token')
            identity = data.get('id_token')
            expires = int(data['expires_in'])
            if (not isinstance(access, str) or not access or
                    data.get('token_type', '').lower() != 'bearer' or not 0 < expires <= 86400 or
                    (refresh is not None and (not isinstance(refresh, str) or not refresh)) or
                    (require_identity and (not isinstance(identity, str) or not identity))):
                raise ValueError()
            scopes = normalized_scopes(data.get('scope', fallback_scopes))
            return Tokens(access, refresh, identity,
                          datetime.now(timezone.utc) + timedelta(seconds=expires), scopes)
        except AuthError:
            raise
        except Exception:
            raise AuthError('OAUTH_TOKEN_INVALID') from None

    def exchange(self, code, verifier):
        data = self._post(TOKEN_URL, {
            'grant_type': 'authorization_code', 'code': code, 'code_verifier': verifier,
            'client_id': self.settings.client_id, 'client_secret': self.settings.client_secret,
            'redirect_uri': self.settings.redirect_uri,
        })
        return self._tokens(data, require_identity=True)

    def refresh(self, refresh_token, scopes):
        normalized_scopes(scopes)
        data = self._post(TOKEN_URL, {'grant_type': 'refresh_token', 'refresh_token': refresh_token,
                                    'client_id': self.settings.client_id,
                                    'client_secret': self.settings.client_secret})
        return self._tokens(data, fallback_scopes=scopes)

    def revoke(self, token):
        self._post(REVOKE_URL, {'token': token})

    def verify_identity(self, tokens, nonce):
        try:
            if self.id_request is not None:
                claims = id_token.verify_oauth2_token(
                    tokens.id_token, self.id_request, self.settings.client_id,
                    clock_skew_in_seconds=ID_TOKEN_CLOCK_SKEW_SECONDS)
            else:
                with requests.Session() as session:
                    request = Request(session=session)
                    def timed_request(*args, **kwargs):
                        kwargs['timeout'] = self.settings.timeout
                        return request(*args, **kwargs)
                    claims = id_token.verify_oauth2_token(
                        tokens.id_token, timed_request, self.settings.client_id,
                        clock_skew_in_seconds=ID_TOKEN_CLOCK_SKEW_SECONDS)
            # google-auth verifies signature, issuer, audience, expiry and issued-at.
            if (not isinstance(claims.get('nonce'), str) or
                    not secrets.compare_digest(claims['nonce'], nonce) or
                    claims.get('email_verified') is not True or
                    not isinstance(claims.get('sub'), str) or not 0 < len(claims['sub']) <= 255 or
                    not isinstance(claims.get('email'), str) or not 0 < len(claims['email']) <= 320 or
                    claims.get('azp', self.settings.client_id) != self.settings.client_id):
                raise ValueError()
            if 'at_hash' in claims:
                expected = base64.urlsafe_b64encode(hashlib.sha256(tokens.access_token.encode()).digest()[:16]).rstrip(b'=').decode()
                if not isinstance(claims['at_hash'], str) or not secrets.compare_digest(claims['at_hash'], expected):
                    raise ValueError()
            return {key: claims.get(key) for key in ('sub', 'email', 'name', 'picture')}
        except Exception:
            raise AuthError('OAUTH_IDENTITY_INVALID') from None
