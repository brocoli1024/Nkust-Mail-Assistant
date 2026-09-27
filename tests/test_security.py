"""Adversarial web checks use synthetic secrets and never contact Google."""
import pytest
from sqlalchemy.exc import SQLAlchemyError

from tests.test_auth import oauth
from tests.test_sessions import web, login, csrf
from tests.test_sync_auth import setup_sync

MARKER = 'SYNTHETIC-SECRET-DO-NOT-ECHO'


@pytest.mark.parametrize('path', [
    '/announcements/' + MARKER,
    '/announcements?page=' + MARKER,
    '/announcements?view=' + MARKER,
])
def test_invalid_input_not_reflected(web, path):
    client, _, _, _ = web
    login(client)
    response = client.get(path)
    assert response.status_code == 422
    assert MARKER not in response.text
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('path', ['/.env', '/token.json', '/credentials.json',
    '/data/nkust_multi_user.db', '/assets/../.env', '/assets/%2e%2e/%2e%2e/.env',
    '/api/announcements', '/api/summary', '/docs', '/openapi.json'])
def test_private_files_and_legacy_apis_not_exposed(web, path):
    client, _, _, _ = web
    login(client)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize('error,status', [(RuntimeError(MARKER), 500), (SQLAlchemyError(MARKER), 503)])
def test_sync_unexpected_errors_are_sanitized(web, caplog, error, status):
    client, app, calls = setup_sync(web)
    login(client)
    token = csrf(client)
    def fail(*args):
        raise error
    app.state.sync_service.sync_gmail_for_user = fail
    response = client.post('/sync', json={}, headers={'x-csrf-token': token})
    assert response.status_code == status
    assert MARKER not in response.text and MARKER not in caplog.text
    assert 'Traceback' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert calls == []


def test_csrf_from_another_session_cannot_sync_or_logout(web):
    client, app, calls = setup_sync(web)
    login(client)
    old_token = csrf(client)
    login(client)  # Session rotation gives even the same user a different CSRF token.
    assert client.post('/sync', json={}, headers={'x-csrf-token': old_token}).status_code == 403
    assert client.post('/logout', headers={'x-csrf-token': old_token}).status_code == 403
    assert calls == [] and client.get('/api/me').status_code == 200


@pytest.mark.parametrize('body,mime,status', [
    ('x' * 4097, 'application/json', 413),
    ('{"limit":', 'application/json', 422),
    ('limit=5&limit=10', 'application/x-www-form-urlencoded', 422),
    ('{}', 'text/plain', 415),
])
def test_malformed_sync_never_reaches_gmail(web, body, mime, status):
    client, app, calls = setup_sync(web)
    login(client)
    response = client.post('/sync', content=body,
        headers={'content-type': mime, 'x-csrf-token': csrf(client)})
    assert response.status_code == status and calls == []


def test_untrusted_host_rejected_and_no_open_redirect(web):
    client, _, _, _ = web
    assert client.get('/login', headers={'host': 'evil.invalid'}).status_code == 400
    login(client)
    response = client.get('/login?next=https://evil.invalid')
    assert response.headers['location'] == '/dashboard'


@pytest.mark.parametrize('path', ['/dashboard', '/settings', '/announcements', '/announcements/99999'])
def test_protected_responses_disable_caching_and_framing(web, path):
    client, _, _, _ = web
    login(client)
    response = client.get(path)
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert "default-src 'none'" in response.headers['content-security-policy']
