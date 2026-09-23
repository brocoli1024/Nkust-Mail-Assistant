"""Read-only Gmail access. All network boundaries expose sanitized domain errors."""
import json
import os
import tempfile
from collections.abc import Callable

import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import GMAIL_SCOPES, Settings
from app.services.email_parser import DecodedEmail, decode_message


class GmailError(RuntimeError):
    pass


class GmailSetupRequired(GmailError):
    pass


def _check_scopes(scopes):
    if isinstance(scopes, str):
        scopes = scopes.split()
    if set(scopes or []) != set(GMAIL_SCOPES):
        raise GmailSetupRequired(
            'OAUTH_SCOPE_MISMATCH: only gmail.readonly is allowed. '
            'Use a separate readonly client/token; see README. Existing token was not changed.'
        )


class _TimedRequest(Request):
    def __init__(self, timeout):
        super().__init__()
        self.timeout = timeout

    def __call__(self, *args, **kwargs):
        kwargs['timeout'] = self.timeout
        return super().__call__(*args, **kwargs)


class _TimedInstalledAppFlow(InstalledAppFlow):
    request_timeout = 30

    def fetch_token(self, **kwargs):
        kwargs.setdefault('timeout', self.request_timeout)
        return super().fetch_token(**kwargs)


def _save_token(credentials, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as handle:
            temporary = handle.name
            handle.write(credentials.to_json())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def authenticate(settings: Settings) -> Credentials:
    """May open the local browser. Invoked only by the explicit Gmail CLI command."""
    try:
        credentials = None
        if settings.token_path.exists():
            stored = json.loads(settings.token_path.read_text(encoding='utf-8'))
            _check_scopes(stored.get('scopes'))
            credentials = Credentials.from_authorized_user_info(stored, scopes=GMAIL_SCOPES)
        changed = False
        if credentials is None or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(_TimedRequest(settings.timeout_seconds))
            else:
                if not settings.credentials_path.is_file():
                    raise GmailSetupRequired(
                        'OAUTH_SETUP_REQUIRED: create a Google Cloud Desktop OAuth client and '
                        f'place its JSON at {settings.credentials_path}. See README Google Cloud setup.'
                    )
                info = json.loads(settings.credentials_path.read_text(encoding='utf-8'))
                if 'installed' not in info:
                    raise GmailSetupRequired('OAUTH_CLIENT_TYPE: credentials must be a Desktop app client')
                flow = _TimedInstalledAppFlow.from_client_secrets_file(str(settings.credentials_path), GMAIL_SCOPES)
                flow.request_timeout = settings.timeout_seconds
                credentials = flow.run_local_server(
                    host='localhost', port=0, timeout_seconds=180,
                    access_type='offline', prompt='consent', include_granted_scopes='false',
                )
            changed = True
        _check_scopes(credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes)
        if changed:
            _save_token(credentials, settings.token_path)
        return credentials
    except GmailError:
        raise
    except Exception as exc:
        raise GmailError('OAUTH_FAILED: credentials could not be loaded, refreshed, authorized or saved; check local setup') from exc


class GmailService:
    def __init__(self, settings: Settings, api):
        self.settings = settings
        self.api = api

    @classmethod
    def connect(cls, settings: Settings):
        credentials = authenticate(settings)
        try:
            http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=settings.timeout_seconds))
            api = build('gmail', 'v1', http=http, cache_discovery=False)
            return cls(settings, api)
        except Exception as exc:
            raise GmailError('GMAIL_CONNECT_FAILED: could not initialize Gmail API') from exc

    @staticmethod
    def _execute(operation: str, request: Callable):
        try:
            return request().execute(num_retries=2)
        except HttpError as exc:
            raise GmailError(f'GMAIL_API_ERROR: {operation}, HTTP {exc.resp.status}') from exc
        except Exception as exc:
            raise GmailError(f'GMAIL_REQUEST_FAILED: {operation}') from exc

    def list_message_ids(self, limit: int = 100) -> list[str]:
        if limit < 1:
            raise ValueError('limit must be positive')
        ids = []
        seen_ids = set()
        seen_tokens = set()
        token = None
        while len(ids) < limit:
            arguments = dict(userId='me', q=self.settings.gmail_query, maxResults=min(100, limit - len(ids)))
            if token:
                arguments['pageToken'] = token
            response = self._execute('messages.list', lambda: self.api.users().messages().list(**arguments))
            try:
                for message in response.get('messages', []):
                    message_id = message['id']
                    if not isinstance(message_id, str) or not message_id:
                        raise ValueError('invalid message ID')
                    if message_id not in seen_ids:
                        ids.append(message_id)
                        seen_ids.add(message_id)
                    if len(ids) == limit:
                        break
                token = response.get('nextPageToken')
                if not token:
                    break
                if token in seen_tokens:
                    raise GmailError('GMAIL_PAGINATION_ERROR: repeated page token')
                seen_tokens.add(token)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise GmailError('GMAIL_RESPONSE_INVALID: messages.list') from exc
        return ids

    def get_message(self, message_id: str) -> dict:
        return self._execute('messages.get', lambda: self.api.users().messages().get(
            userId='me', id=message_id, format='full'))

    def get_body_attachment(self, message_id: str, attachment_id: str) -> str:
        response = self._execute('messages.attachments.get', lambda: self.api.users().messages().attachments().get(
            userId='me', messageId=message_id, id=attachment_id))
        if not isinstance(response, dict) or not isinstance(response.get('data'), str):
            raise GmailError('GMAIL_RESPONSE_INVALID: attachment body data missing')
        return response['data']

    def read_message(self, message_id: str) -> DecodedEmail:
        return decode_message(self.get_message(message_id),
                              lambda attachment_id: self.get_body_attachment(message_id, attachment_id))
