from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from dotenv import dotenv_values

from app.config import ROOT

WEB_SCOPES = ('openid', 'email', 'profile', 'https://www.googleapis.com/auth/gmail.readonly')


@dataclass(frozen=True)
class OAuthSettings:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    redirect_uri: str
    base_url: str
    encryption_key: str = field(repr=False)
    timeout: int = 30

    @classmethod
    def load(cls, env_file=None):
        values = {**dotenv_values(env_file or ROOT / '.env'), **os.environ}
        return cls(*(values.get(key) or '' for key in (
            'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI',
            'APP_BASE_URL', 'TOKEN_ENCRYPTION_KEY')))

    def validate(self):
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ValueError('GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required')
        try:
            base = urlsplit(self.base_url)
            valid = (base.scheme in ('http', 'https') and base.hostname and
                     not base.username and not base.password and not base.query and
                     not base.fragment and base.path in ('', '/') and base.port != 0)
            if not valid or (base.scheme == 'http' and base.hostname not in ('localhost', '127.0.0.1', '::1')):
                raise ValueError()
            if self.redirect_uri != self.base_url.rstrip('/') + '/auth/google/callback':
                raise ValueError()
        except ValueError:
            raise ValueError('APP_BASE_URL / GOOGLE_REDIRECT_URI invalid; HTTPS required outside localhost') from None
        try:
            Fernet(self.encryption_key.encode('ascii'))
        except (ValueError, UnicodeError):
            raise ValueError('TOKEN_ENCRYPTION_KEY must be a valid Fernet key') from None
        if self.timeout <= 0:
            raise ValueError('OAuth timeout must be positive')
        return self

    @property
    def secure_cookie(self):
        return urlsplit(self.base_url).scheme == 'https'
