"""Per-user Gmail adapter; no Desktop flow or global token files.

Create one client per operation and close it; httplib2 clients are not shared
between users or worker threads. Reuses the legacy read/parse methods unchanged.
"""
from dataclasses import dataclass

import httplib2
from google.auth.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.exc import SQLAlchemyError

from app.auth.errors import AuthError, ReauthorizationRequired
from app.core.session import CurrentUser
from app.services.gmail_service import GmailService, GmailError
from app.services.email_parser import EmailParseError


class GmailReauthorizationRequired(GmailError):
    """The caller must prompt this user to reconnect Google, not crash the app."""


class GmailCredentialsUnavailable(GmailError):
    """Temporary token provider/database failure; retry later."""


def _access_token(tokens, user_id, *, google_user_id, rejected_token=None):
    try:
        return tokens.access_token(user_id, rejected_token=rejected_token, google_user_id=google_user_id)
    except ReauthorizationRequired:
        raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE') from None
    except AuthError as exc:
        if str(exc) in ('OAUTH_SCOPE_MISMATCH', 'OAUTH_CREDENTIAL_UNREADABLE', 'OAUTH_ACCOUNT_MISMATCH'):
            raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE') from None
        raise GmailCredentialsUnavailable('GMAIL_CREDENTIALS_UNAVAILABLE') from None
    except SQLAlchemyError:
        raise GmailCredentialsUnavailable('GMAIL_CREDENTIALS_UNAVAILABLE') from None
    except Exception:
        raise GmailCredentialsUnavailable('GMAIL_CREDENTIALS_UNAVAILABLE') from None


class _UserCredentials(Credentials):
    """SDK bearer adapter; TokenService exclusively owns refresh and persistence."""
    def __init__(self, tokens, user_id, google_user_id):
        super().__init__()
        self._tokens = tokens
        self._user_id = user_id
        self._google_user_id = google_user_id

    def before_request(self, request, method, url, headers):
        self.token = _access_token(self._tokens, self._user_id, google_user_id=self._google_user_id)
        self.apply(headers)

    def refresh(self, request):
        self.token = _access_token(self._tokens, self._user_id, google_user_id=self._google_user_id,
                                   rejected_token=self.token)


@dataclass(frozen=True)
class _ReadSettings:
    timeout_seconds: int
    gmail_query: str = 'from:mailoffice@nkust.edu.tw'


class UserGmailService(GmailService):
    @classmethod
    def connect(cls, settings, *, tokens, user_id, google_user_id):
        if type(user_id) is not int or user_id < 1 or not google_user_id:
            raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
        if settings.timeout_seconds <= 0:
            raise ValueError('Gmail timeout must be positive')
        credentials = _UserCredentials(tokens, user_id, google_user_id)
        # Fail before constructing the SDK resource if the account is unavailable.
        credentials.token = _access_token(tokens, user_id, google_user_id=google_user_id)
        http = None
        try:
            http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=settings.timeout_seconds),
                                  max_refresh_attempts=1)
            # Bundled discovery avoids a network request during construction.
            api = build('gmail', 'v1', http=http, cache_discovery=False, static_discovery=True)
            return cls(_ReadSettings(settings.timeout_seconds), api)
        except Exception:
            if http is not None:
                try:
                    http.close()
                except Exception:
                    pass
            raise GmailError('GMAIL_CONNECT_FAILED') from None

    @staticmethod
    def _execute(operation, request):
        try:
            return request().execute(num_retries=2)
        except GmailError:
            raise
        except HttpError as exc:
            if exc.resp.status == 401:
                raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE') from None
            raise GmailError(f'GMAIL_API_ERROR: {operation}, HTTP {exc.resp.status}') from None
        except Exception:
            raise GmailError(f'GMAIL_REQUEST_FAILED: {operation}') from None

    def close(self):
        self.api.close()

    def read_message(self, message_id):
        try:
            return super().read_message(message_id)
        except EmailParseError as exc:
            # The unchanged MIME parser wraps attachment loader errors. Preserve
            # actionable credential errors for the future per-user sync caller.
            if isinstance(exc.__cause__, (GmailReauthorizationRequired, GmailCredentialsUnavailable)):
                raise exc.__cause__ from None
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class UserGmailFactory:
    def __init__(self, settings, tokens):
        self.settings = settings
        self.tokens = tokens

    def __call__(self, user):
        # Callers pass the identity produced by current_user, never request JSON.
        if not isinstance(user, CurrentUser):
            raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
        return UserGmailService.connect(self.settings, tokens=self.tokens, user_id=user.id,
                                       google_user_id=user.google_user_id)
