import base64
import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from googleapiclient.errors import HttpError

from app.config import GMAIL_SCOPES, Settings
from app.services.gmail_service import GmailError, GmailService, GmailSetupRequired, authenticate


def service():
    api = MagicMock()
    return GmailService(Settings(gmail_query='subject:synthetic'), api), api.users().messages()


def settings(tmp_path):
    return Settings(credentials_path=tmp_path / 'credentials.json', token_path=tmp_path / 'token.json')


def credential_mock(**kwargs):
    return Mock(scopes=GMAIL_SCOPES, granted_scopes=None, valid=True,
                to_json=Mock(return_value=json.dumps({'scopes': list(GMAIL_SCOPES)})), **kwargs)


def test_pagination_configurable_query_and_in_run_duplicates():
    gmail, messages = service()
    messages.list().execute.side_effect = [
        {'messages': [{'id': 'a'}, {'id': 'b'}], 'nextPageToken': 'page2'},
        {'messages': [{'id': 'b'}, {'id': 'c'}]},
    ]
    messages.list.reset_mock()
    assert gmail.list_message_ids() == ['a', 'b', 'c']
    assert messages.list.call_args_list[0].kwargs == {'userId': 'me', 'q': 'subject:synthetic', 'maxResults': 100}
    assert messages.list.call_args_list[1].kwargs['pageToken'] == 'page2'
    assert messages.list().execute.call_args.kwargs == {'num_retries': 2}


def test_limit_and_empty_mailbox():
    gmail, messages = service()
    messages.list().execute.return_value = {'messages': [{'id': 'a'}, {'id': 'b'}]}
    assert gmail.list_message_ids(limit=1) == ['a']
    messages.list().execute.return_value = {}
    assert gmail.list_message_ids() == []
    with pytest.raises(ValueError):
        gmail.list_message_ids(0)


def test_get_and_attachment_decode():
    gmail, messages = service()
    messages.get().execute.return_value = {
        'id': 'a', 'internalDate': '1789776000000',
        'payload': {'mimeType': 'text/html', 'body': {'attachmentId': 'body'}},
    }
    messages.attachments().get().execute.return_value = {'data': base64.urlsafe_b64encode('公告'.encode()).decode()}
    assert gmail.read_message('a').html_body == '公告'
    messages.get.assert_called_with(userId='me', id='a', format='full')
    messages.attachments().get.assert_called_with(userId='me', messageId='a', id='body')


@pytest.mark.parametrize('operation', ['list', 'get', 'attachment'])
def test_api_failures_are_sanitized(operation):
    gmail, messages = service()
    error = HttpError(Mock(status=403, reason='Forbidden'), b'private response content')
    if operation == 'list':
        messages.list().execute.side_effect = error
        call = gmail.list_message_ids
    elif operation == 'get':
        messages.get().execute.side_effect = error
        call = lambda: gmail.get_message('a')
    else:
        messages.attachments().get().execute.side_effect = error
        call = lambda: gmail.get_body_attachment('a', 'b')
    with pytest.raises(GmailError, match='HTTP 403') as caught:
        call()
    assert 'private' not in str(caught.value)


def test_network_failure_and_repeated_page():
    gmail, messages = service()
    messages.list().execute.side_effect = TimeoutError
    with pytest.raises(GmailError, match='REQUEST_FAILED'):
        gmail.list_message_ids()
    messages.list().execute.side_effect = None
    messages.list().execute.return_value = {'nextPageToken': 'same'}
    with pytest.raises(GmailError, match='PAGINATION_ERROR'):
        gmail.list_message_ids()


def test_missing_credentials_does_not_launch_browser(tmp_path):
    with patch('app.services.gmail_service._TimedInstalledAppFlow') as flow:
        with pytest.raises(GmailSetupRequired, match='OAUTH_SETUP_REQUIRED'):
            authenticate(settings(tmp_path))
        flow.from_client_secrets_file.assert_not_called()


def test_oauth_requests_only_readonly_and_saves_token(tmp_path):
    config = settings(tmp_path)
    config.credentials_path.write_text('{"installed": {}}', encoding='utf-8')
    with patch('app.services.gmail_service._TimedInstalledAppFlow') as flow:
        flow.from_client_secrets_file().run_local_server.return_value = credential_mock()
        authenticate(config)
        flow.from_client_secrets_file.assert_called_with(str(config.credentials_path), GMAIL_SCOPES)
        args = flow.from_client_secrets_file().run_local_server.call_args.kwargs
        assert args['port'] == 0
        assert args['include_granted_scopes'] == 'false'
    assert json.loads(config.token_path.read_text())['scopes'] == list(GMAIL_SCOPES)


def test_cached_broad_token_rejected_without_overwriting(tmp_path):
    config = settings(tmp_path)
    original = '{"scopes": ["https://www.googleapis.com/auth/gmail.modify"]}'
    config.token_path.write_text(original, encoding='utf-8')
    with pytest.raises(GmailSetupRequired, match='SCOPE_MISMATCH'):
        authenticate(config)
    assert config.token_path.read_text() == original


def test_valid_token_reused_without_oauth(tmp_path):
    config = settings(tmp_path)
    config.token_path.write_text(json.dumps({'scopes': list(GMAIL_SCOPES)}))
    credentials = credential_mock()
    with patch('app.services.gmail_service.Credentials') as factory, patch('app.services.gmail_service._TimedInstalledAppFlow') as flow:
        factory.from_authorized_user_info.return_value = credentials
        assert authenticate(config) is credentials
        flow.from_client_secrets_file.assert_not_called()


def test_expired_token_refresh(tmp_path):
    config = settings(tmp_path)
    config.token_path.write_text(json.dumps({'scopes': list(GMAIL_SCOPES)}))
    credentials = credential_mock(expired=True, refresh_token='synthetic')
    credentials.valid = False
    with patch('app.services.gmail_service.Credentials') as factory:
        factory.from_authorized_user_info.return_value = credentials
        authenticate(config)
        assert credentials.refresh.call_args.args[0].timeout == config.timeout_seconds


def test_refresh_failure_keeps_existing_token(tmp_path):
    config = settings(tmp_path)
    original = json.dumps({'scopes': list(GMAIL_SCOPES)})
    config.token_path.write_text(original)
    credentials = credential_mock(expired=True, refresh_token='synthetic')
    credentials.valid = False
    credentials.refresh.side_effect = RuntimeError('secret')
    with patch('app.services.gmail_service.Credentials') as factory:
        factory.from_authorized_user_info.return_value = credentials
        with pytest.raises(GmailError, match='OAUTH_FAILED'):
            authenticate(config)
    assert config.token_path.read_text() == original


def test_real_oauth_url_has_only_readonly_scope():
    from urllib.parse import parse_qs, urlsplit
    from app.services.gmail_service import _TimedInstalledAppFlow
    flow = _TimedInstalledAppFlow.from_client_config({'installed': {
        'client_id': 'synthetic-client', 'client_secret': 'synthetic-secret',
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'redirect_uris': ['http://localhost'],
    }}, GMAIL_SCOPES)
    flow.redirect_uri = 'http://localhost:12345/'
    url, _ = flow.authorization_url(include_granted_scopes='false', prompt='consent')
    query = parse_qs(urlsplit(url).query)
    assert query['scope'] == list(GMAIL_SCOPES)
    assert query['include_granted_scopes'] == ['false']
    flow.request_timeout = 17
    with patch('google_auth_oauthlib.flow.InstalledAppFlow.fetch_token') as fetch:
        flow.fetch_token(code='synthetic-code')
        fetch.assert_called_once_with(code='synthetic-code', timeout=17)


def test_extra_granted_scope_is_not_saved(tmp_path):
    config = settings(tmp_path)
    config.credentials_path.write_text('{"installed": {}}')
    credentials = credential_mock()
    credentials.granted_scopes = [*GMAIL_SCOPES, 'https://www.googleapis.com/auth/gmail.modify']
    with patch('app.services.gmail_service._TimedInstalledAppFlow') as flow:
        flow.from_client_secrets_file().run_local_server.return_value = credentials
        with pytest.raises(GmailSetupRequired, match='SCOPE_MISMATCH'):
            authenticate(config)
    assert not config.token_path.exists()
