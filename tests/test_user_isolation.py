"""Two real web OAuth/session flows, fake Gmail, actual parser and SQL storage."""
from sqlalchemy import select, func

from app.models.multi_user import Announcement, Email
from tests.test_auth import oauth
from tests.test_sessions import web, login, csrf
from tests.test_sync_auth import setup_sync


def test_login_sync_read_logout_end_to_end_isolation(web):
    client, app, calls = setup_sync(web)
    login(client)
    first = client.get('/api/me').json()['id']
    first_cookie = client.cookies.get(app.state.sessions.cookie_name)
    first_csrf = csrf(client)
    assert client.post('/sync', json={}, headers={'x-csrf-token': first_csrf}).json()['announcements_created'] == 3
    with app.state.database.transaction() as session:
        first_ids = list(session.scalars(select(Announcement.id).where(Announcement.user_id == first)))
    client.cookies.clear()
    web[2].claims = {'sub': 'isolated-b', 'email': 'b@example.invalid'}
    login(client)
    second = client.get('/api/me').json()['id']
    assert second != first
    assert '共 0 則' in client.get('/announcements').text
    assert '查看全部 0 則公告' in client.get('/dashboard').text
    for row_id in first_ids:
        assert client.get(f'/announcements/{row_id}?user_id={first}').status_code == 404
    assert client.post('/sync', json={}, headers={'x-csrf-token': first_csrf}).status_code == 403
    second_csrf = csrf(client)
    result = client.post('/sync', json={}, headers={'x-csrf-token': second_csrf})
    assert result.json()['database_counts']['emails'] == 1
    with app.state.database.transaction() as session:
        second_ids = list(session.scalars(select(Announcement.id).where(Announcement.user_id == second)))
        assert session.scalar(select(func.count()).select_from(Email)) == 2
    assert set(first_ids).isdisjoint(second_ids)
    assert client.get(f'/announcements/{second_ids[0]}').status_code == 200
    client.post('/logout', headers={'x-csrf-token': second_csrf})
    assert client.get(f'/announcements/{second_ids[0]}').status_code == 303
    client.cookies.clear()
    client.cookies.set(app.state.sessions.cookie_name, first_cookie)
    assert client.get(f'/announcements/{first_ids[0]}').status_code == 200
    assert client.get(f'/announcements/{second_ids[0]}').status_code == 404
    result = client.post('/sync', json={}, headers={'x-csrf-token': first_csrf})
    assert result.json()['emails_skipped'] == 1
    assert result.json()['announcements_created'] == 0
    assert calls == [first, second, first]
