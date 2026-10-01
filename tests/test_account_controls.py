"""Account removal exercises the actual session, token and database boundaries."""
from dataclasses import replace
import pytest
from sqlalchemy import func, select

from app.auth.errors import AuthError
from app.core.session import CurrentUser, current_page_user
from app.database.user_mail import UserSyncLease
from app.models.multi_user import User, Email, Announcement, OAuthAccount, WebSession, Analysis, Scrape
from app.services.user_sync_service import UserSyncService
from app.services.account_service import delete_account
from tests.test_auth import oauth
from tests.test_sessions import web, login, csrf
from tests.test_api import mail
from tests.test_sync_multi_user import FakeMailbox


def test_data_use_notice_is_available_before_login(web):
    client, _, _, _ = web
    response = client.get('/privacy')
    assert response.status_code == 200
    assert 'href="/privacy"' in client.get('/login').text
    assert 'Gmail' in response.text and '刪除' in response.text
    assert response.headers['cache-control'] == 'no-store'


def test_deletion_removes_only_current_users_data_and_all_their_sessions(web):
    client, app, google, _ = web
    google.token = replace(google.token, refresh_token='first-refresh-marker')
    login(client)
    first = client.get('/api/me').json()
    first_cookie = client.cookies.get(app.state.sessions.cookie_name)
    first_csrf = csrf(client)
    extra_cookie = app.state.sessions.create(first['id'])
    service = UserSyncService(app.state.database, lambda _: FakeMailbox({'a': mail('a')}))
    service.sync_gmail_for_user(CurrentUser(first['id'], first['email'], None, 'google-a'))
    with app.state.database.transaction() as session:
        item = session.scalar(select(Announcement).where(Announcement.user_id == first['id']))
        session.add(Analysis(user_id=first['id'], announcement_id=item.id, input_hash='x' * 64,
                             provider='synthetic', model='synthetic', version='v1', status='completed'))
        session.add(Scrape(user_id=first['id'], announcement_id=item.id, status='completed',
                           attempted_at=app.state.sessions.now()))
    client.cookies.clear()
    google.claims = {'sub': 'google-b', 'email': 'b@example.invalid'}
    google.token = replace(google.token, refresh_token='second-refresh-marker')
    login(client)
    second = client.get('/api/me').json()
    second_cookie = client.cookies.get(app.state.sessions.cookie_name)
    service.sync_gmail_for_user(CurrentUser(second['id'], second['email'], None, 'google-b'))
    client.cookies.clear()
    client.cookies.set(app.state.sessions.cookie_name, first_cookie, domain='localhost.local', path='/')
    response = client.post('/account/delete', data={'csrf_token': first_csrf, 'confirm': 'DELETE'},
                           headers={'origin': 'http://localhost'})
    assert response.status_code == 303 and response.headers['location'] == '/login?deleted=1'
    assert not client.cookies.get(app.state.sessions.cookie_name)
    assert app.state.sessions.resolve(first_cookie) is None
    assert app.state.sessions.resolve(extra_cookie) is None
    assert app.state.sessions.resolve(second_cookie).id == second['id']
    assert google.revoked == ['first-refresh-marker']
    with app.state.database.transaction() as session:
        assert session.scalars(select(User.id)).all() == [second['id']]
        for model in (Email, Announcement, OAuthAccount, WebSession):
            assert session.scalar(select(func.count()).select_from(model).where(model.user_id == first['id'])) == 0
            assert session.scalar(select(func.count()).select_from(model).where(model.user_id == second['id'])) > 0
        assert session.scalar(select(func.count()).select_from(Analysis)) == 0
        assert session.scalar(select(func.count()).select_from(Scrape)) == 0


@pytest.mark.parametrize('body,headers,status', [
    ({'confirm': 'DELETE'}, {}, 403),
    ({'confirm': 'DELETE', 'csrf_token': 'bad'}, {}, 403),
    ({'confirm': 'DELETE'}, {'origin': 'https://evil.invalid'}, 403),
    ({'confirm': 'DELETE'}, {'origin': 'null'}, 403),
    ({'confirm': 'DELETE'}, {'sec-fetch-site': 'cross-site'}, 403),
    ({}, {}, 422),
    ({'confirm': 'DELETE', 'user_id': '2'}, {}, 422),
])
def test_deletion_requires_confirmation_and_csrf_without_other_user_input(web, body, headers, status):
    client, app, _, _ = web
    login(client)
    if 'origin' in headers or 'sec-fetch-site' in headers or not body or 'user_id' in body:
        body = dict(body, csrf_token=csrf(client))
    assert client.post('/account/delete', data=body, headers=headers).status_code == status
    assert client.get('/api/me').status_code == 200
    with app.state.database.transaction() as session:
        assert session.scalar(select(OAuthAccount)).refresh_token_encrypted


def test_active_sync_blocks_deletion_without_revoking_credentials(web):
    client, app, _, _ = web
    login(client)
    uid = client.get('/api/me').json()['id']
    lease = UserSyncLease(app.state.database, uid)
    lease.acquire()
    try:
        response = client.post('/account/delete', data={'csrf_token': csrf(client), 'confirm': 'DELETE'})
        assert response.status_code == 409
        assert response.headers['referrer-policy'] == 'same-origin'
        assert client.get('/api/me').status_code == 200
        with app.state.database.transaction() as session:
            assert session.scalar(select(OAuthAccount)).refresh_token_encrypted
    finally:
        lease.release()


def test_google_failure_does_not_prevent_local_data_deletion_or_expose_secrets(web, caplog):
    client, app, google, _ = web
    login(client)
    token = csrf(client)
    google.error = AuthError('OAUTH_PROVIDER_FAILED: PRIVATE-MARKER')
    response = client.post('/account/delete', data={'csrf_token': token, 'confirm': 'DELETE'})
    assert response.status_code == 303
    assert response.headers['location'] == '/login?deleted=1&disconnect=manual'
    notice = client.get(response.headers['location'])
    assert 'myaccount.google.com' in notice.text
    assert 'PRIVATE-MARKER' not in response.text + notice.text + caplog.text
    assert client.get('/api/me').status_code == 401
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_deletion_has_no_get_or_anonymous_side_effect(web):
    client, _, _, _ = web
    assert client.post('/account/delete').status_code == 401
    login(client)
    assert client.get('/account/delete').status_code == 405
    settings = client.get('/settings')
    assert 'action="/account/delete"' in settings.text
    assert settings.headers['referrer-policy'] == 'same-origin'


@pytest.mark.parametrize('operation', ['delete', 'sync'])
def test_stale_authenticated_request_cannot_target_a_reused_account_id(web, operation):
    client, app, google, _ = web
    login(client)
    old_user = app.state.sessions.resolve(client.cookies.get(app.state.sessions.cookie_name))
    assert client.post('/account/delete', data={'csrf_token': csrf(client), 'confirm': 'DELETE'}).status_code == 303
    google.claims = {'sub': 'google-b', 'email': 'b@example.invalid'}
    login(client)
    new_id = client.get('/api/me').json()['id']
    with pytest.raises(PermissionError):
        if operation == 'delete':
            delete_account(app.state.database, app.state.tokens, old_user)
        else:
            UserSyncService(app.state.database, lambda _: FakeMailbox({'a': mail('a')})).sync_gmail_for_user(old_user)
    assert client.get('/api/me').json()['email'] == 'b@example.invalid'
    with app.state.database.transaction() as session:
        assert session.get(User, new_id).google_user_id == 'google-b'
        assert session.scalar(select(func.count()).select_from(Email)) == 0


def test_reconnect_cannot_replace_tokens_during_account_deletion(web):
    client, app, google, _ = web
    login(client)
    user_id = client.get('/api/me').json()['id']
    original_revoke = google.revoke
    def concurrent_reconnect(token):
        with pytest.raises(AuthError, match='OAUTH_ACCOUNT_BUSY'):
            app.state.tokens.save_identity(google.claims, replace(google.token, refresh_token='new-grant'))
        original_revoke(token)
    google.revoke = concurrent_reconnect
    response = client.post('/account/delete', data={'csrf_token': csrf(client), 'confirm': 'DELETE'})
    assert response.status_code == 303 and response.headers['location'] == '/login?deleted=1'
    with app.state.database.transaction() as session:
        assert session.get(User, user_id) is None


def test_delayed_callback_cannot_issue_session_for_a_reused_user_id(web):
    client, app, google, _ = web
    login(client)
    old_id = client.get('/api/me').json()['id']
    client.post('/account/delete', data={'csrf_token': csrf(client), 'confirm': 'DELETE'})
    google.claims = {'sub': 'google-b', 'email': 'b@example.invalid'}
    login(client)
    with pytest.raises(AuthError, match='OAUTH_ACCOUNT_CHANGED'):
        app.state.sessions.create(old_id, google_user_id='google-a')
    assert client.get('/api/me').json()['email'] == 'b@example.invalid'


@pytest.mark.parametrize('view', ['list', 'detail', 'dashboard'])
def test_stale_request_cannot_read_a_reused_accounts_announcements(web, view):
    client, app, google, _ = web
    login(client)
    old_user = app.state.sessions.resolve(client.cookies.get(app.state.sessions.cookie_name))
    client.post('/account/delete', data={'csrf_token': csrf(client), 'confirm': 'DELETE'})
    google.claims = {'sub': 'google-b', 'email': 'b@example.invalid'}
    login(client)
    new_user = app.state.sessions.resolve(client.cookies.get(app.state.sessions.cookie_name))
    UserSyncService(app.state.database, lambda _: FakeMailbox({'a': mail('a')})).sync_gmail_for_user(new_user)
    with app.state.database.transaction() as session:
        item = session.scalar(select(Announcement).where(Announcement.user_id == new_user.id))
        item.title = 'PRIVATE-B-ANNOUNCEMENT'
        item.original_text = 'PRIVATE-B-ANNOUNCEMENT'
        item_id = item.id
    # A request can already have resolved its identity when another request deletes it.
    app.dependency_overrides[current_page_user] = lambda: old_user
    try:
        path = {'list': '/announcements', 'detail': f'/announcements/{item_id}',
                'dashboard': '/dashboard'}[view]
        response = client.get(path)
        if view == 'detail':
            assert response.status_code == 404
        elif view == 'dashboard':
            assert '查看全部 0 則公告' in response.text
        else:
            assert response.status_code == 200
            assert 'PRIVATE-B-ANNOUNCEMENT' not in response.text
    finally:
        app.dependency_overrides.clear()
