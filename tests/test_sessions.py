"""Authentication, revocation, fixation, CSRF and per-browser user isolation."""
from datetime import timedelta
import re

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, delete, func
from sqlalchemy.engine import URL

from app.config import Settings
from app.core.session import SessionService, session_hash, SESSION_SECONDS
from app.models.multi_user import WebSession, User, OAuthAccount
from app.web import create_app
from tests.test_auth import oauth, FakeGoogle, begin, finish
from tests.test_multi_user_database import configuration


@pytest.fixture
def web(tmp_path, oauth):
    url = URL.create('sqlite', database=str(tmp_path / 'sessions.db'))
    command.upgrade(configuration(url), 'head')
    google = FakeGoogle(oauth)
    settings = Settings(database_url=url)
    app = create_app(settings, oauth, google_factory=lambda _: google,
                     session_enabled=True, session_secret='test-only-session-secret-32-characters')
    with TestClient(app, base_url='http://localhost', follow_redirects=False) as client:
        yield client, app, google, settings


def login(client):
    query, _ = begin(client)
    response = finish(client, query['state'][0])
    assert response.status_code == 303
    assert response.headers['location'] == '/dashboard'
    return response


def csrf(client):
    return re.search(r'name="csrf_token" value="([a-f0-9]+)"', client.get('/dashboard').text)[1]


def test_anonymous_pages_redirect_and_api_denies(web):
    client, _, _, _ = web
    for path in ('/dashboard', '/settings'):
        response = client.get(path)
        assert response.status_code == 303 and response.headers['location'] == '/login'
    assert client.get('/api/me').status_code == 401
    assert client.post('/logout').status_code == 401
    response = client.get('/login')
    assert response.status_code == 200 and '使用 Google 登入' in response.text


def test_login_cookie_hash_and_user_page(web):
    client, app, google, _ = web
    response = login(client)
    sessions = app.state.sessions
    value = client.cookies.get(sessions.cookie_name)
    cookie = response.headers.get_list('set-cookie')[0]
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and f'Max-Age={SESSION_SECONDS}' in cookie
    assert 'Domain=' not in cookie and 'Path=/' in cookie
    with app.state.database.transaction() as session:
        row = session.scalar(select(WebSession))
        assert row.id_hash == session_hash(value) and row.id_hash != value
    assert client.get('/api/me').json()['email'] == google.claims['email']
    assert google.claims['email'] in client.get('/dashboard').text
    assert client.get('/login').headers['location'] == '/dashboard'
    assert client.get('/').headers['location'] == '/dashboard'
    assert client.get('/auth/complete').headers['location'] == '/dashboard'
    assert 'private-marker' not in client.get('/settings').text


def test_logout_revokes_session_not_google_credentials(web):
    client, app, google, _ = web
    login(client)
    sessions = app.state.sessions
    old = client.cookies.get(sessions.cookie_name)
    response = client.post('/logout', data={'csrf_token': csrf(client)}, headers={'origin': 'http://localhost'})
    assert response.status_code == 303
    assert not client.cookies.get(sessions.cookie_name)
    assert google.revoked == []
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(WebSession)) == 0
        assert session.scalar(select(OAuthAccount)).refresh_token_encrypted
    client.cookies.set(sessions.cookie_name, old)
    assert client.get('/api/me').status_code == 401
    assert client.get('/dashboard').status_code == 303


@pytest.mark.parametrize('headers,body', [({}, {}), ({}, {'csrf_token':'bad'}),
    ({'origin':'https://evil.invalid'}, None), ({'origin':'null'}, None),
    ({'sec-fetch-site':'cross-site'}, None)])
def test_logout_csrf_rejected_without_revoking(web, headers, body):
    client, app, _, _ = web
    login(client)
    response = client.post('/logout', data={'csrf_token':csrf(client)} if body is None else body, headers=headers)
    assert response.status_code == 403
    assert client.get('/api/me').status_code == 200


def test_get_logout_not_allowed(web):
    client, _, _, _ = web
    login(client)
    assert client.get('/logout').status_code == 405
    assert client.get('/api/me').status_code == 200


def test_expired_tampered_and_unknown_sessions_denied(web):
    client, app, _, _ = web
    login(client)
    name = app.state.sessions.cookie_name
    raw = client.cookies.get(name)
    with app.state.database.transaction() as session:
        row = session.get(WebSession, session_hash(raw))
        row.expires_at = app.state.sessions.now() - timedelta(seconds=1)
    assert client.get('/api/me').status_code == 401
    for value in ('tampered', 'x' * 43, '中文'):
        client.cookies.clear()
        if value == '中文':
            assert app.state.sessions.resolve(value) is None
        else:
            client.cookies.set(name, value)
            assert client.get('/api/me').status_code == 401


def test_reauthentication_rotates_and_invalidates_previous_session(web):
    client, app, _, _ = web
    login(client)
    name = app.state.sessions.cookie_name
    first = client.cookies.get(name)
    login(client)
    second = client.cookies.get(name)
    assert second != first
    assert app.state.sessions.resolve(first) is None
    assert app.state.sessions.resolve(second) is not None
    assert not app.state.sessions.valid_csrf(second, app.state.sessions.csrf(first))


def test_failed_reauthentication_does_not_create_or_rotate_session(web):
    from app.auth.errors import AuthError
    client, app, google, _ = web
    login(client)
    before = client.cookies.get(app.state.sessions.cookie_name)
    google.error = AuthError('OAUTH_PROVIDER_FAILED')
    query, _ = begin(client)
    assert finish(client, query['state'][0]).status_code == 400
    assert client.cookies.get(app.state.sessions.cookie_name) == before
    assert client.get('/api/me').status_code == 200


def test_two_users_isolated_and_logout_does_not_affect_other(web):
    client, app, google, _ = web
    login(client)
    sessions = app.state.sessions
    first = client.cookies.get(sessions.cookie_name)
    first_csrf = csrf(client)
    client.cookies.clear()
    google.claims = {'sub':'google-b', 'email':'b@example.invalid', 'name':'Student B'}
    login(client)
    second = client.cookies.get(sessions.cookie_name)
    assert client.get('/api/me').json()['email'] == 'b@example.invalid'
    assert 'a@example.invalid' not in client.get('/dashboard').text
    assert client.post('/logout', data={'csrf_token':first_csrf}).status_code == 403
    assert client.post('/logout', data={'csrf_token':csrf(client)}).status_code == 303
    assert sessions.resolve(second) is None
    assert sessions.resolve(first).email == 'a@example.invalid'


def test_session_survives_app_restart(web, oauth):
    client, app, google, settings = web
    login(client)
    name = app.state.sessions.cookie_name
    value = client.cookies.get(name)
    other = create_app(settings, oauth, google_factory=lambda _: google,
                       session_enabled=True, session_secret='test-only-session-secret-32-characters')
    with TestClient(other, base_url='http://localhost') as second:
        second.cookies.set(name, value)
        assert second.get('/api/me').json()['email'] == 'a@example.invalid'
        app.state.sessions.revoke(value)
        assert second.get('/api/me').status_code == 401


def test_deleted_user_session_invalidated(web):
    client, app, _, _ = web
    login(client)
    with app.state.database.transaction() as session:
        session.execute(delete(User))
    assert client.get('/api/me').status_code == 401


def test_html_escaping_and_no_store(web):
    client, app, google, _ = web
    google.claims['name'] = '<script>alert(1)</script>'
    login(client)
    response = client.get('/dashboard')
    assert '<script>' not in response.text and '&lt;script&gt;' in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert "form-action 'self'" in response.headers['content-security-policy']


def test_secure_cookie_policy_and_secret_validation(web):
    from fastapi.responses import Response
    _, app, _, _ = web
    service = SessionService(app.state.database, 's' * 48, secure=True)
    response = Response()
    service.set_cookie(response, 'x' * 43)
    cookie = response.headers['set-cookie']
    assert cookie.startswith('__Host-nkust_session=') and 'Secure' in cookie
    assert 'Domain=' not in cookie and 'HttpOnly' in cookie
    with pytest.raises(ValueError):
        SessionService(app.state.database, '', secure=True)


def test_old_routes_still_not_mounted(web):
    client, _, _, _ = web
    login(client)
    for path in ('/api/announcements', '/api/summary', '/api/ai/status'):
        assert client.get(path).status_code == 404
    assert client.post('/api/gmail/sync').status_code == 404
