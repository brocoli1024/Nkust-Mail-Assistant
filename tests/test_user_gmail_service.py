"""Exercise real Gmail SDK requests with offline HTTP and encrypted user records."""
import base64
from datetime import datetime, timedelta, timezone
import json
import traceback
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httplib2
import pytest
from sqlalchemy import select

from app.auth.errors import ReauthorizationRequired, AuthError
from app.config import Settings
from app.core.session import CurrentUser
from app.models.multi_user import OAuthAccount, User
from app.services.gmail_service import GmailError
from app.services.user_gmail_service import (
    UserGmailFactory, UserGmailService, GmailReauthorizationRequired, GmailCredentialsUnavailable,
)
from tests.test_auth import web, oauth, tokens


class FakeHttp:
    def __init__(self, responder=None):
        self.requests = []
        self.closed = False
        self.responder = responder or (lambda uri, auth: (200, {'messages': [{'id': auth.split()[-1]}]}))

    def request(self, uri, method='GET', body=None, headers=None, **kwargs):
        self.requests.append((uri, method, dict(headers or {})))
        assert method == 'GET'
        status, payload = self.responder(uri, headers.get('authorization'))
        return httplib2.Response({'status': str(status), 'content-type': 'application/json'}), json.dumps(payload).encode()

    def close(self):
        self.closed = True


def seed(app, google, *, expired=False):
    expiry = datetime.now(timezone.utc) + timedelta(seconds=-1 if expired else 3600)
    first = app.state.tokens.save_identity(google.claims, tokens(access_token='user-a-token', refresh_token='user-a-refresh', expires_at=expiry))
    second = app.state.tokens.save_identity({'sub':'google-b', 'email':'b@example.invalid'},
                                           tokens(access_token='user-b-token', refresh_token='user-b-refresh'))
    return CurrentUser(first, 'a@example.invalid', 'A', 'google-a'), CurrentUser(second, 'b@example.invalid', 'B', 'google-b')


def test_existing_gmail_client_cannot_use_a_reused_accounts_token(web):
    _, app, google = web
    first = app.state.tokens.save_identity(google.claims, tokens(access_token='user-a-token'))
    actor = CurrentUser(first, 'a@example.invalid', 'A', 'google-a')
    transport = FakeHttp()
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport):
        with app.state.gmail_for_user(actor) as client:
            with app.state.database.transaction() as session:
                session.delete(session.get(User, first))
            second = app.state.tokens.save_identity({'sub': 'google-b', 'email': 'b@example.invalid'},
                                                    tokens(access_token='user-b-token'))
            assert second == first  # SQLite's numeric ID may be reused after deletion.
            with pytest.raises(GmailReauthorizationRequired):
                client.list_message_ids()
    assert transport.requests == []


def test_two_users_have_separate_clients_bearer_tokens_and_fixed_query(web, tmp_path):
    _, app, google = web
    a, b = seed(app, google)
    config = Settings(gmail_query='in:anywhere', credentials_path=tmp_path/'missing.json', token_path=tmp_path/'token.json')
    transports = [FakeHttp(), FakeHttp()]
    with patch('app.services.user_gmail_service.httplib2.Http', side_effect=transports), \
         patch('app.services.gmail_service.authenticate', side_effect=AssertionError('Desktop flow called')):
        factory = UserGmailFactory(config, app.state.tokens)
        with factory(a) as client_a, factory(b) as client_b:
            assert client_a.api is not client_b.api
            assert client_a.list_message_ids() == ['user-a-token']
            assert client_b.list_message_ids() == ['user-b-token']
    assert all(t.closed for t in transports)
    assert not config.token_path.exists()
    for transport in transports:
        uri, method, _ = transport.requests[0]
        assert '/users/me/messages' in uri
        assert parse_qs(urlsplit(uri).query)['q'] == ['from:mailoffice@nkust.edu.tw']
        assert len(transport.requests) == 1  # no network discovery on construction


def test_expired_access_refreshes_only_owner_and_persists_encrypted(web):
    _, app, google = web
    a, b = seed(app, google, expired=True)
    google.token = tokens(access_token='a-updated', refresh_token='a-refresh-updated')
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=FakeHttp()):
        with app.state.gmail_for_user(a) as client:
            assert client.list_message_ids() == ['a-updated']
    assert google.refreshes == 1
    with app.state.database.transaction() as session:
        rows = {r.user_id:r for r in session.scalars(select(OAuthAccount))}
        assert app.state.tokens.decrypt(rows[a.id].refresh_token_encrypted, context=f'google:{a.id}:refresh') == 'a-refresh-updated'
        assert app.state.tokens.decrypt(rows[b.id].access_token_encrypted, context=f'google:{b.id}:access') == 'user-b-token'
        assert 'a-refresh-updated' not in rows[a.id].refresh_token_encrypted


def test_401_forces_refresh_once_even_when_not_expired(web):
    _, app, google = web
    a, _ = seed(app, google)
    google.token = tokens(access_token='new-access')
    transport = FakeHttp(lambda uri, auth: (401, {'error':'private-body'}) if auth == 'Bearer user-a-token' else (200, {'messages':[{'id':'ok'}]}))
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport):
        with app.state.gmail_for_user(a) as client:
            assert client.list_message_ids() == ['ok']
    assert google.refreshes == 1 and len(transport.requests) == 2
    assert transport.requests[1][2]['authorization'] == 'Bearer new-access'


def test_repeated_401_stops_after_one_refresh_and_sanitizes_traceback(web):
    _, app, google = web
    a, _ = seed(app, google)
    transport = FakeHttp(lambda uri, auth: (401, {'error': {'message':'private-body-marker'}}))
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport):
        with app.state.gmail_for_user(a) as client:
            with pytest.raises(GmailReauthorizationRequired) as caught:
                client.list_message_ids()
    assert google.refreshes == 1 and len(transport.requests) == 2
    assert 'private-body-marker' not in ''.join(traceback.format_exception(caught.value))


@pytest.mark.parametrize('error,expected', [(ReauthorizationRequired('OAUTH_REAUTHORIZE'), GmailReauthorizationRequired),
                                          (AuthError('OAUTH_PROVIDER_FAILED'), GmailCredentialsUnavailable)])
def test_refresh_failure_leaves_other_user_usable(web, error, expected):
    _, app, google = web
    a, b = seed(app, google, expired=True)
    google.error = error
    with pytest.raises(expected):
        app.state.gmail_for_user(a)
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=FakeHttp()):
        with app.state.gmail_for_user(b) as client:
            assert client.list_message_ids() == ['user-b-token']


def test_no_token_fallback_for_unknown_user_or_untrusted_identity(web):
    _, app, _ = web
    with patch('app.services.gmail_service.authenticate', side_effect=AssertionError('legacy fallback')):
        for user in ({'id':1}, 1, None, CurrentUser(999,'missing@example.invalid',None,'missing'), CurrentUser(True,'bad',None,'bad')):
            with pytest.raises(GmailReauthorizationRequired):
                app.state.gmail_for_user(user)


def test_credential_revoked_after_client_creation_is_checked_before_next_request(web):
    _, app, google = web
    a, _ = seed(app, google)
    transport = FakeHttp()
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport):
        with app.state.gmail_for_user(a) as client:
            app.state.tokens.revoke(a.id)
            with pytest.raises(GmailReauthorizationRequired):
                client.list_message_ids()
    assert transport.requests == []


@pytest.mark.parametrize('corruption', ['scope','identity','ciphertext'])
def test_invalid_account_refused_before_gmail_request(web, corruption):
    _, app, google = web
    a, b = seed(app, google)
    with app.state.database.transaction() as session:
        row = session.scalar(select(OAuthAccount).where(OAuthAccount.user_id == a.id))
        if corruption == 'scope':
            row.scopes = [*row.scopes,'https://www.googleapis.com/auth/gmail.modify']
        elif corruption == 'identity':
            row.provider_user_id = 'mismatched-subject'
        else:
            row.access_token_encrypted = session.scalar(select(OAuthAccount).where(OAuthAccount.user_id == b.id)).access_token_encrypted
    with pytest.raises(GmailReauthorizationRequired):
        app.state.gmail_for_user(a)


def test_refresh_does_not_repeat_if_another_worker_already_replaced_token(web):
    _, app, google = web
    a, _ = seed(app, google)
    assert app.state.tokens.access_token(a.id,rejected_token='an-older-token') == 'user-a-token'
    assert google.refreshes == 0


def test_reused_pagination_and_mime_attachment_parser(web):
    _, app, google = web
    a, _ = seed(app, google)
    def respond(uri, auth):
        url = urlsplit(uri)
        if '/attachments/' in url.path:
            return 200, {'data':base64.urlsafe_b64encode('合成公告'.encode()).decode()}
        if url.path.endswith('/messages/message-a'):
            return 200, {'id':'message-a','internalDate':'1789776000000',
                          'payload':{'mimeType':'text/html','body':{'attachmentId':'body'}}}
        if parse_qs(url.query).get('pageToken'):
            return 200, {'messages':[{'id':'message-a'},{'id':'message-b'}]}
        return 200, {'messages':[{'id':'message-a'}], 'nextPageToken':'page2'}
    transport = FakeHttp(respond)
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport):
        with app.state.gmail_for_user(a) as client:
            assert client.list_message_ids() == ['message-a','message-b']
            assert client.read_message('message-a').html_body == '合成公告'
    assert len(transport.requests) == 4


def test_attachment_auth_failure_propagates_without_rewriting_parser(web):
    _, app, google = web
    a, _ = seed(app, google)
    def respond(uri, auth):
        if '/attachments/' in uri:
            return 401, {'error': {'message':'private marker'}}
        return 200, {'id':'a','internalDate':'1789776000000',
                      'payload':{'mimeType':'text/html','body':{'attachmentId':'body'}}}
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=FakeHttp(respond)):
        with app.state.gmail_for_user(a) as client:
            with pytest.raises(GmailReauthorizationRequired):
                client.read_message('a')


def test_builder_failure_closes_transport_without_leaking_credentials(web):
    _, app, google = web
    a, _ = seed(app, google)
    transport = FakeHttp()
    with patch('app.services.user_gmail_service.httplib2.Http', return_value=transport), \
         patch('app.services.user_gmail_service.build', side_effect=RuntimeError('private-token-marker')):
        with pytest.raises(GmailError) as caught:
            app.state.gmail_for_user(a)
    assert transport.closed
    assert 'private-token-marker' not in ''.join(traceback.format_exception(caught.value))
