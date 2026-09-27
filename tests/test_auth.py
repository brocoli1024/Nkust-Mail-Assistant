"""Offline OAuth routes, real signed ID tokens, and encrypted account storage."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from alembic import command
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from sqlalchemy import func, select
from sqlalchemy.engine import URL

from app.auth.attempts import COOKIE, digest
from app.auth.config import OAuthSettings, WEB_SCOPES
from app.auth.errors import AuthError, ReauthorizationRequired
from app.auth.google_oauth import GoogleOAuth, TOKEN_URL, REVOKE_URL, Tokens
from app.auth.token_service import TokenService
from app.config import Settings
from app.models.multi_user import OAuthAccount, OAuthAttempt, User
from app.web import create_app, RedactQuery
from tests.test_multi_user_database import configuration


@pytest.fixture
def oauth():
    return OAuthSettings('test-client', 'client-secret-marker',
                         'http://localhost/auth/google/callback', 'http://localhost',
                         Fernet.generate_key().decode())


def tokens(**kwargs):
    values = dict(access_token='access-private-marker', refresh_token='refresh-private-marker',
                  id_token='id-private-marker', expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                  scopes=list(WEB_SCOPES))
    return Tokens(**(values | kwargs))


class FakeGoogle:
    def __init__(self, settings):
        self.settings = settings
        self.claims = {'sub': 'google-a', 'email': 'a@example.invalid', 'name': 'Student'}
        self.token = tokens()
        self.error = None
        self.exchanges = 0
        self.refreshes = 0
        self.revoked = []

    authorization_url = GoogleOAuth.authorization_url

    def exchange(self, code, verifier):
        self.exchanges += 1
        if self.error:
            raise self.error
        return self.token

    def verify_identity(self, token, nonce):
        return self.claims

    def refresh(self, token, scopes):
        self.refreshes += 1
        if self.error:
            raise self.error
        return self.token

    def revoke(self, token):
        if self.error:
            raise self.error
        self.revoked.append(token)


@pytest.fixture
def web(tmp_path, oauth):
    url = URL.create('sqlite', database=str(tmp_path / 'web.db'))
    command.upgrade(configuration(url), 'head')
    google = FakeGoogle(oauth)
    app = create_app(Settings(database_url=url), oauth, google_factory=lambda _: google)
    with TestClient(app, base_url='http://localhost', follow_redirects=False) as client:
        yield client, app, google


def begin(client):
    response = client.get('/auth/google')
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers['location']).query)
    return query, response


def finish(client, state):
    return client.get('/auth/google/callback', params={'state': state, 'code': 'private-code-marker'})


def test_authorization_url_cookie_and_server_side_secrets(web):
    client, app, google = web
    query, response = begin(client)
    assert set(query['scope'][0].split()) == set(WEB_SCOPES)
    assert query['access_type'] == ['offline']
    assert query['code_challenge_method'] == ['S256']
    assert query['include_granted_scopes'] == ['false']
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Max-Age=600' in cookie
    assert 'client-secret-marker' not in response.headers['location']
    with app.state.database.transaction() as session:
        attempt = session.get(OAuthAttempt, digest(query['state'][0]))
        assert query['nonce'][0] not in attempt.context_encrypted
        assert client.cookies.get(COOKIE) != attempt.browser_hash


def test_callback_saves_encrypted_credentials_without_session_or_mail_access(web):
    client, app, google = web
    query, _ = begin(client)
    response = finish(client, query['state'][0])
    assert response.status_code == 303 and response.headers['location'] == '/auth/complete'
    assert response.headers['cache-control'] == 'no-store'
    assert not client.cookies.get(COOKIE)
    with app.state.database.transaction() as session:
        user = session.scalar(select(User))
        account = session.scalar(select(OAuthAccount))
        assert user.google_user_id == account.provider_user_id == 'google-a'
        assert 'access-private-marker' not in account.access_token_encrypted
        assert 'refresh-private-marker' not in account.refresh_token_encrypted
        assert session.scalar(select(func.count()).select_from(OAuthAttempt)) == 0
    for path in ('/dashboard', '/api/announcements', '/api/summary', '/settings'):
        assert client.get(path).status_code == 404
    assert client.post('/api/gmail/sync').status_code == 404
    assert not client.cookies


def test_state_cookie_required_and_replay_rejected(web):
    client, app, google = web
    query, _ = begin(client)
    browser = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert finish(client, query['state'][0]).status_code == 400
    assert google.exchanges == 0
    client.cookies.set(COOKIE, browser, domain='localhost.local', path='/auth/google/callback')
    assert finish(client, query['state'][0]).status_code == 303
    client.cookies.set(COOKIE, browser, domain='localhost.local', path='/auth/google/callback')
    assert finish(client, query['state'][0]).status_code == 400
    assert google.exchanges == 1


def test_expired_state_does_not_exchange_code(web):
    client, app, google = web
    query, _ = begin(client)
    with app.state.database.transaction() as session:
        session.get(OAuthAttempt, digest(query['state'][0])).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert finish(client, query['state'][0]).status_code == 400
    assert google.exchanges == 0


def test_denied_consent_consumes_attempt_and_does_not_echo_provider_error(web):
    client, app, google = web
    query, _ = begin(client)
    response = client.get('/auth/google/callback', params={'state': query['state'][0], 'error': 'secret-body-marker'})
    assert response.status_code == 400
    assert 'secret-body-marker' not in response.text
    assert google.exchanges == 0


def test_duplicate_parameters_and_malformed_state_rejected(web):
    client, app, google = web
    assert client.get('/auth/google/callback?state=x&state=y&code=secret').status_code == 400
    assert client.get('/auth/google/callback?state=%E6%B8%AC%E8%A9%A6&code=secret').status_code == 400
    assert google.exchanges == 0


def test_relogin_updates_same_subject_and_preserves_missing_refresh(web):
    client, app, google = web
    query, _ = begin(client)
    finish(client, query['state'][0])
    google.token = tokens(refresh_token=None)
    google.claims['email'] = 'changed@example.invalid'
    query, _ = begin(client)
    assert finish(client, query['state'][0]).status_code == 303
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert session.scalar(select(User)).email == 'changed@example.invalid'
        row = session.scalar(select(OAuthAccount))
        assert app.state.tokens.decrypt(row.refresh_token_encrypted, context='google:1:refresh') == 'refresh-private-marker'


def test_same_email_different_subject_does_not_merge(web):
    client, app, google = web
    for subject in ('google-a', 'google-b'):
        google.claims['sub'] = subject
        query, _ = begin(client)
        assert finish(client, query['state'][0]).status_code == 303
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 2
        assert session.scalar(select(func.count()).select_from(OAuthAccount)) == 2


def test_missing_initial_refresh_rolls_back_user(web):
    client, app, google = web
    google.token = tokens(refresh_token=None)
    query, _ = begin(client)
    assert finish(client, query['state'][0]).status_code == 400
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_provider_exception_does_not_escape_to_response_or_logs(web, caplog):
    client, app, google = web
    google.error = RuntimeError('private-token-body-marker')
    query, _ = begin(client)
    response = finish(client, query['state'][0])
    assert response.status_code == 500
    assert 'private-token-body-marker' not in response.text + caplog.text


def test_query_redacted_from_uvicorn_access_record():
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d',
                               ('client', 'GET', '/auth/google/callback?code=private&state=private', '1.1', 303), None)
    RedactQuery().filter(record)
    assert 'private' not in record.getMessage()


def test_https_cookie_secure_and_settings_repr(oauth):
    from app.api.auth import cookie_options
    config = replace(oauth, base_url='https://mail.example.invalid',
                     redirect_uri='https://mail.example.invalid/auth/google/callback')
    config.validate()
    assert cookie_options(config)['secure'] is True
    assert oauth.client_secret not in repr(oauth)
    assert oauth.encryption_key not in repr(oauth)
    with pytest.raises(ValueError):
        replace(config, base_url='http://mail.example.invalid').validate()


def test_refresh_encrypted_rotated_token_and_revoke(web):
    client, app, google = web
    uid = app.state.tokens.save_identity(google.claims, tokens(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    google.token = tokens(access_token='new-access', refresh_token='new-refresh')
    assert app.state.tokens.access_token(uid) == 'new-access'
    assert app.state.tokens.access_token(uid) == 'new-access'
    assert google.refreshes == 1
    with app.state.database.transaction() as session:
        row = session.scalar(select(OAuthAccount))
        assert app.state.tokens.decrypt(row.refresh_token_encrypted, context=f'google:{uid}:refresh') == 'new-refresh'
    app.state.tokens.revoke(uid)
    assert google.revoked == ['new-refresh']
    with pytest.raises(ReauthorizationRequired):
        app.state.tokens.access_token(uid)


def test_refresh_failure_preserves_ciphertext_and_requires_reauth(web):
    client, app, google = web
    uid = app.state.tokens.save_identity(google.claims, tokens(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    with app.state.database.transaction() as session:
        before = session.scalar(select(OAuthAccount)).refresh_token_encrypted
    google.error = ReauthorizationRequired('OAUTH_REAUTHORIZE')
    with pytest.raises(ReauthorizationRequired):
        app.state.tokens.access_token(uid)
    with app.state.database.transaction() as session:
        assert session.scalar(select(OAuthAccount)).refresh_token_encrypted == before


def test_encryption_wrong_key_context_and_tampering_fail(web):
    _, app, google = web
    encrypted = app.state.tokens.encrypt('private-token', context='google:1:access')
    wrong_key = TokenService(app.state.database, Fernet.generate_key().decode(), google)
    for service, value, context in ((wrong_key, encrypted, 'google:1:access'),
                                    (app.state.tokens, encrypted, 'google:2:access'),
                                    (app.state.tokens, encrypted[:-8] + 'tampered', 'google:1:access')):
        with pytest.raises(AuthError):
            service.decrypt(value, context=context)


def test_google_http_exchange_refresh_and_revoke(oauth):
    requests_seen = []
    def respond(request):
        requests_seen.append(request)
        assert request.method == 'POST'
        if str(request.url) == REVOKE_URL:
            assert parse_qs(request.content.decode())['token'] == ['refresh-marker']
            return httpx.Response(200)
        return httpx.Response(200, json={'access_token': 'access-marker', 'token_type': 'Bearer',
                                        'expires_in': 3600, 'id_token': 'signed',
                                        'scope': ' '.join(WEB_SCOPES)})
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(respond))
    result = google.exchange('code-marker', 'verifier-marker')
    form = parse_qs(requests_seen[0].content.decode())
    assert str(requests_seen[0].url) == TOKEN_URL
    assert form['code_verifier'] == ['verifier-marker']
    assert form['redirect_uri'] == [oauth.redirect_uri]
    assert 'access-marker' not in repr(result)
    google.refresh('refresh-marker', list(WEB_SCOPES))
    google.revoke('refresh-marker')


@pytest.mark.parametrize('scope', ['openid email profile', ' '.join(WEB_SCOPES) + ' https://www.googleapis.com/auth/gmail.send'])
def test_wrong_scopes_rejected(oauth, scope):
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        'access_token': 'private', 'id_token': 'private', 'expires_in': 3600, 'token_type': 'Bearer', 'scope': scope})))
    with pytest.raises(AuthError, match='SCOPE'):
        google.exchange('code', 'verifier')


def test_http_invalid_grant_is_sanitized(oauth):
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(lambda r: httpx.Response(400, json={
        'error': 'invalid_grant', 'error_description': 'private-secret-marker'})))
    with pytest.raises(ReauthorizationRequired) as exc:
        google.refresh('private-refresh', list(WEB_SCOPES))
    assert str(exc.value) == 'OAUTH_REAUTHORIZE'


def test_google_refresh_accepts_omitted_scope_and_refresh_token(oauth):
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        'access_token': 'new', 'expires_in': 3600, 'token_type': 'Bearer'})))
    value = google.refresh('existing', list(WEB_SCOPES))
    assert value.refresh_token is None
    assert set(value.scopes) == set(WEB_SCOPES)


def test_google_scope_aliases(oauth):
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        'access_token': 'new', 'id_token': 'signed', 'expires_in': 3600, 'token_type': 'Bearer',
        'scope': 'openid https://www.googleapis.com/auth/userinfo.email '
                 'https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.readonly'})))
    assert set(google.exchange('code', 'verifier').scopes) == set(WEB_SCOPES)


def test_token_operations_are_scoped_to_the_requested_user(web):
    _, app, google = web
    first = app.state.tokens.save_identity(google.claims, tokens(access_token='user-a-access'))
    second = app.state.tokens.save_identity({'sub': 'google-b', 'email': 'b@example.invalid'},
                                           tokens(access_token='user-b-access', refresh_token='user-b-refresh'))
    assert app.state.tokens.access_token(first) == 'user-a-access'
    assert app.state.tokens.access_token(second) == 'user-b-access'
    app.state.tokens.revoke(second)
    assert google.revoked == ['user-b-refresh']
    assert app.state.tokens.access_token(first) == 'user-a-access'
    with pytest.raises(ReauthorizationRequired):
        app.state.tokens.access_token(99999)


def test_revoke_failure_preserves_credentials(web):
    _, app, google = web
    uid = app.state.tokens.save_identity(google.claims, tokens())
    google.error = AuthError('OAUTH_PROVIDER_FAILED')
    with pytest.raises(AuthError):
        app.state.tokens.revoke(uid)
    assert app.state.tokens.access_token(uid) == 'access-private-marker'


@pytest.mark.parametrize('status', [302, 500])
def test_provider_redirect_and_server_errors_do_not_expose_body(oauth, status):
    google = GoogleOAuth(oauth, transport=httpx.MockTransport(lambda r: httpx.Response(
        status, text='private-provider-body', headers={'location': 'https://evil.invalid'})))
    with pytest.raises(AuthError) as exc:
        google.exchange('private-code', 'private-verifier')
    assert str(exc.value) == 'OAUTH_PROVIDER_FAILED'


@pytest.fixture(scope='module')
def signing_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return crypt.RSASigner.from_string(private, key_id='test-key'), public.decode()


@pytest.mark.parametrize('change', [{}, {'aud': 'wrong-client'}, {'iss': 'https://evil.invalid'},
                                     {'exp': 1}, {'nonce': 'wrong'}, {'email_verified': False},
                                     {'azp': 'wrong'}, {'at_hash': 'wrong'}])
def test_real_signed_id_token_validation(oauth, signing_key, change):
    signer, public = signing_key
    claims = {'iss': 'https://accounts.google.com', 'aud': oauth.client_id, 'sub': 'google-subject',
              'email': 'student@example.invalid', 'email_verified': True, 'nonce': 'expected-nonce',
              'iat': int(time.time()) - 1, 'exp': int(time.time()) + 3600} | change
    encoded = jwt.encode(signer, claims).decode()
    class CertResponse:
        status = 200
        data = json.dumps({'test-key': public}).encode()
    google = GoogleOAuth(oauth, id_request=lambda *a, **k: CertResponse())
    if change:
        with pytest.raises(AuthError, match='IDENTITY'):
            google.verify_identity(tokens(id_token=encoded), 'expected-nonce')
    else:
        assert google.verify_identity(tokens(id_token=encoded), 'expected-nonce')['sub'] == 'google-subject'


@pytest.mark.parametrize('iat_offset,exp_offset,accepted', [
    (4, 3600, True), (29, 3600, True), (120, 3600, False),
    (-3600, -120, False),
])
@pytest.mark.parametrize('injected_request', [True, False])
def test_identity_clock_skew_is_bounded(oauth, signing_key, monkeypatch,
                                       iat_offset, exp_offset, accepted, injected_request):
    signer, public = signing_key
    now = int(time.time())
    encoded = jwt.encode(signer, {
        'iss': 'https://accounts.google.com', 'aud': oauth.client_id,
        'sub': 'subject', 'email': 'student@example.invalid',
        'email_verified': True, 'nonce': 'nonce',
        'iat': now + iat_offset, 'exp': now + exp_offset,
    }).decode()

    class CertResponse:
        status = 200
        data = json.dumps({'test-key': public}).encode()

    def cert_request(*args, **kwargs):
        return CertResponse()

    monkeypatch.setattr('app.auth.google_oauth.Request', lambda **kwargs: cert_request)
    google = GoogleOAuth(oauth, id_request=cert_request if injected_request else None)
    if accepted:
        assert google.verify_identity(tokens(id_token=encoded), 'nonce')['sub'] == 'subject'
    else:
        with pytest.raises(AuthError, match='IDENTITY'):
            google.verify_identity(tokens(id_token=encoded), 'nonce')


def test_bad_signature_rejected(oauth, signing_key):
    signer, public = signing_key
    encoded = jwt.encode(signer, {'iss': 'https://accounts.google.com', 'aud': oauth.client_id,
                                 'sub': 'subject', 'email': 'student@example.invalid',
                                 'email_verified': True, 'nonce': 'nonce',
                                 'iat': int(time.time()) - 1, 'exp': int(time.time()) + 3600}).decode()
    head, payload, signature = encoded.split('.')
    damaged = (('A' if signature[0] != 'A' else 'B') + signature[1:])
    class CertResponse:
        status = 200
        data = json.dumps({'test-key': public}).encode()
    google = GoogleOAuth(oauth, id_request=lambda *a, **k: CertResponse())
    with pytest.raises(AuthError, match='IDENTITY'):
        google.verify_identity(tokens(id_token=f'{head}.{payload}.{damaged}'), 'nonce')
