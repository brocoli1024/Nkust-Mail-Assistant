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

    def discovery(self, user, *, timeout_seconds):
        if not isinstance(user, CurrentUser):raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
        if type(timeout_seconds) is not int or not 1<=timeout_seconds<=10:raise ValueError('OFFICE_DISCOVERY_TIMEOUT')
        return DiscoveryGmailService.connect(_ReadSettings(timeout_seconds),tokens=self.tokens,user_id=user.id,google_user_id=user.google_user_id)

    def __call__(self, user):
        # Callers pass the identity produced by current_user, never request JSON.
        if not isinstance(user, CurrentUser):
            raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
        return UserGmailService.connect(self.settings, tokens=self.tokens, user_id=user.id,
                                       google_user_id=user.google_user_id)


class DiscoveryGmailService(UserGmailService):
    """Independent no-retry SDK client for the bounded discovery operation."""
    @staticmethod
    def _execute(operation, request):
        try:
            return request().execute(num_retries=0)
        except GmailError:
            raise
        except HttpError as exc:
            if exc.resp.status == 401:
                raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE') from None
            if exc.resp.status==400 and operation=='discovery.page':raise GmailError('GMAIL_DISCOVERY_PAGE_TOKEN') from None
            raise GmailError('GMAIL_DISCOVERY_UNAVAILABLE') from None
        except Exception:
            raise GmailError('GMAIL_DISCOVERY_UNAVAILABLE') from None

    def list_discovery_page(self, start, end, *, page_token=None):
        from app.services.office_mail_discovery_source import discovery_query
        import re
        if page_token is not None and (not isinstance(page_token,str) or not 1<=len(page_token)<=4096):
            raise GmailError('GMAIL_RESPONSE_INVALID')
        args=dict(userId='me',q=discovery_query(start,end),maxResults=10,includeSpamTrash=False)
        if page_token:args['pageToken']=page_token
        result=self._execute('discovery.page' if page_token else 'messages.list',lambda:self.api.users().messages().list(**args))
        try:
            rows=result.get('messages',[]);token=result.get('nextPageToken')
            if not isinstance(rows,list) or len(rows)>10:raise ValueError()
            ids=tuple(row['id'] for row in rows)
            if any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,255}',i) for i in ids) or len(set(ids))!=len(ids):raise ValueError()
            if token is not None and (not isinstance(token,str) or not 1<=len(token)<=4096 or token==page_token):raise ValueError()
            return ids,token
        except (ValueError,TypeError,KeyError,AttributeError):raise GmailError('GMAIL_RESPONSE_INVALID') from None

    def read_message(self,message_id):
        from app.services.email_parser import decode_message
        raw=self.get_message(message_id)
        if not isinstance(raw,dict) or raw.get('id')!=message_id:raise GmailError('EMAIL_ID_MISMATCH')
        headers=raw.get('payload',{}).get('headers',[])
        if sum(h.get('name','').lower()=='from' for h in headers)!=1:raise EmailParseError('EMAIL_FORMAT_ERROR')
        return decode_message(raw,lambda aid:self.get_body_attachment(message_id,aid))
