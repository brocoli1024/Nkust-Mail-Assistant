from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup

from app.api.user_announcements import calendar, dashboard_counts, safe_url
from app.models.multi_user import User, Email, Announcement
from tests.test_sessions import web, login
from tests.test_auth import oauth


def seed(web, count=1):
    client, app, _, _ = web
    login(client)
    uid = client.get('/api/me').json()['id']
    today, start, end = calendar()
    with app.state.database.transaction() as session:
        other = User(google_user_id='other', email='other@example.invalid')
        session.add(other)
        session.flush()
        ids = []
        for owner, prefix, amount in ((uid, 'OWN', count), (other.id, 'PRIVATE-OTHER', 1)):
            email = Email(user_id=owner, gmail_message_id='same-id', status='processed', received_at=start)
            session.add(email)
            session.flush()
            for index in range(amount):
                row = Announcement(user_id=owner, email_id=email.id, source_index=index,
                    source_fingerprint=str(index), department=prefix, source_category='課程',
                    category='課程', title=f'{prefix}-{index}', original_text='<script>alert(1)</script>',
                    original_html='<img src=x onerror=alert(1)>', url='javascript:alert(1)',
                    deadline=today + timedelta(days=6), requires_action=True)
                session.add(row)
                session.flush()
                ids.append(row.id)
        other_id = other.id
    return uid, other_id, ids


def test_anonymous_pages_require_login(web):
    client, _, _, _ = web
    for path in ('/announcements', '/announcements/1'):
        response = client.get(path)
        assert response.status_code == 303
        assert response.headers['location'] == '/login'


def test_list_detail_and_dashboard_ownership(web):
    uid, other, ids = seed(web)
    client, app, _, _ = web
    for query in ('', '?view=today', '?view=deadline', '?view=action', '?category=課程', f'?user_id={other}'):
        response = client.get('/announcements' + query)
        assert response.status_code == 200
        assert 'OWN-0' in response.text and 'PRIVATE-OTHER' not in response.text
    actor = app.state.sessions.resolve(client.cookies.get(app.state.sessions.cookie_name))
    assert dashboard_counts(app.state.database, actor) == dict(all=1, today=1, deadline=1, action=1)
    assert '查看全部 1 則公告' in client.get('/dashboard').text
    response = client.get(f'/announcements/{ids[0]}')
    assert response.status_code == 200
    assert '&lt;script&gt;' in response.text
    assert '<script>' not in response.text and 'javascript:' not in response.text and '<img' not in response.text
    denied = client.get(f'/announcements/{ids[-1]}')
    absent = client.get('/announcements/999999')
    assert denied.status_code == absent.status_code == 404
    assert denied.content == absent.content
    # Switch to a separately issued server session, not a client-supplied user id.
    value = app.state.sessions.create(other)
    client.cookies.clear()
    client.cookies.set(app.state.sessions.cookie_name, value)
    assert 'PRIVATE-OTHER' in client.get('/announcements').text
    assert 'OWN-0' not in client.get('/announcements').text
    assert client.get(f'/announcements/{ids[0]}').status_code == 404


def test_pagination_filters_and_validation(web):
    _, _, ids = seed(web, count=21)
    client, _, _, _ = web
    first = client.get('/announcements?category=課程').text
    second = client.get('/announcements?category=課程&page=2').text
    assert first.count('class="announcement"') == 20
    assert second.count('class="announcement"') == 1
    assert f'href="/announcements/{ids[0]}"' not in first
    assert f'href="/announcements/{ids[0]}"' in second
    assert '目前沒有符合條件' in client.get('/announcements?category=實習').text
    for query in ('?category=invalid', '?view=invalid', '?page=0', '?page=1000001'):
        assert client.get('/announcements' + query).status_code == 422


def test_category_filter_finds_unclassified_source_and_title_matches(web):
    _, _, ids = seed(web, count=3)
    client, app, _, _ = web
    with app.state.database.transaction() as session:
        source_match = session.get(Announcement, ids[0])
        source_match.category = None
        source_match.source_category = '獎學金申請'

        title_match = session.get(Announcement, ids[1])
        title_match.category = None
        title_match.source_category = '校園訊息'
        title_match.title = '獎助學金說明'

        classified_elsewhere = session.get(Announcement, ids[2])
        classified_elsewhere.category = '課程'
        classified_elsewhere.source_category = '獎學金申請'
        classified_elsewhere.title = '獎學金說明'

    response = client.get('/announcements?view=all&category=獎學金')
    assert response.status_code == 200
    assert '共 2 則' in response.text
    assert f'href="/announcements/{ids[0]}"' in response.text
    assert f'href="/announcements/{ids[1]}"' in response.text
    assert f'href="/announcements/{ids[2]}"' not in response.text
    assert '原始分類：獎學金申請' in response.text
    assert '原始分類：校園訊息' in response.text
    assert 'PRIVATE-OTHER' not in response.text


def test_category_filter_shows_matched_category_without_claiming_ai_classification(web):
    _, _, ids = seed(web, count=2)
    client, app, _, _ = web
    with app.state.database.transaction() as session:
        matched = session.get(Announcement, ids[0])
        matched.category = None
        matched.source_category = '獎學金申請'
        classified = session.get(Announcement, ids[1])
        classified.category = '獎學金'
    response = client.get('/announcements?category=獎學金')
    assert response.status_code == 200
    assert response.text.count('class="tag">符合：獎學金') == 1
    assert response.text.count('class="tag">獎學金') == 1
    assert '原始分類：獎學金申請' in response.text


def test_filter_selects_apply_without_button_and_keep_get_navigation(web):
    client, _, _, _ = web
    login(client)
    response = client.get('/announcements?view=today&category=課程')
    assert response.status_code == 200
    assert '<form method="get" action="/announcements"' in response.text
    assert '<script src="/assets/announcement-filters.js" defer></script>' in response.text
    assert 'value="today" selected' in response.text
    assert '<option selected>課程</option>' in response.text
    page = BeautifulSoup(response.text, 'html.parser')
    assert not [button for button in page.select('button[type=submit]')
                if button.find_parent('noscript') is None]
    assert client.get('/assets/announcement-filters.js').status_code == 200

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is not installed; filter interaction simulation unavailable')
    script = Path(__file__).resolve().parent / 'announcement_filter_check.cjs'
    result = subprocess.run([node, str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_taipei_boundaries_and_unknown_values(web, monkeypatch):
    uid, _, ids = seed(web)
    client, app, _, _ = web
    actor = app.state.sessions.resolve(client.cookies.get(app.state.sessions.cookie_name))
    fixed = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)
    dates = calendar(fixed)
    assert dates[0].isoformat() == '2026-09-28'
    monkeypatch.setattr('app.api.user_announcements.calendar', lambda: dates)
    today, start, end = dates
    with app.state.database.transaction() as session:
        row = session.get(Announcement, ids[0])
        row.deadline = today + timedelta(days=7)
        row.requires_action = None
        row.category = None
        session.get(Email, row.email_id).received_at = end
    assert dashboard_counts(app.state.database, actor) == dict(all=1, today=0, deadline=0, action=0)
    assert 'OWN-0' in client.get('/announcements?category=未分類').text
    assert '尚未判定' in client.get(f'/announcements/{ids[0]}').text
    with app.state.database.transaction() as session:
        row = session.get(Announcement, ids[0])
        row.deadline = today
        session.get(Email, row.email_id).received_at = start
    assert dashboard_counts(app.state.database, actor)['today'] == 1
    assert dashboard_counts(app.state.database, actor)['deadline'] == 1


def test_deadline_view_orders_urgent_items_before_pagination(web):
    _, _, ids = seed(web, count=21)
    client, app, _, _ = web
    today, _, _ = calendar()
    with app.state.database.transaction() as session:
        # The oldest item must move ahead of twenty later deadlines.
        session.get(Announcement, ids[0]).deadline = today
    first = client.get('/announcements?view=deadline').text
    second = client.get('/announcements?view=deadline&page=2').text
    urgent = f'href="/announcements/{ids[0]}"'
    assert urgent in first
    assert urgent not in second
    assert first.index(urgent) < first.index(f'href="/announcements/{ids[20]}"')
    # Other views retain the existing newest-first ordering.
    assert urgent not in client.get('/announcements').text


@pytest.mark.parametrize('url', ['javascript:alert(1)', '//evil.invalid', 'data:text/html,test',
    'https://user:pass@example.invalid', 'https://example.invalid\\x', 'https://[bad', 'https://example.invalid\n'])
def test_unsafe_links_are_not_clickable(url):
    assert safe_url(url) is None


def test_https_link_preserved():
    assert safe_url('https://example.invalid/a?q=1&x=2') == 'https://example.invalid/a?q=1&x=2'
