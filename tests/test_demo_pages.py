"""Synthetic demo must never fall back to a mailbox or database."""
from bs4 import BeautifulSoup
import httpx
import pytest
from sqlalchemy import select, func

from tests.test_sessions import web, login
from tests.test_auth import oauth
from tests.test_public_pages import seed
from app.models.public_announcements import PublicAnnouncement
from app.models.multi_user import User

NOTICE = '合成示範資料，非高科大真實公告，請勿據此報名或申請'
DEMO_IDS = ('demo-scholarship', 'demo-event', 'demo-notice')


def demo_links(response):
    soup = BeautifulSoup(response.text, 'html.parser')
    return [a['href'] for a in soup.select('.announcement h2 a')]


def test_demo_filter_and_detail(web):
    client, _, _, _ = web
    r = client.get('/demo')
    assert r.status_code == 200
    assert len(demo_links(r)) == 3
    assert demo_links(client.get('/demo?q=獎學金')) == ['/demo/announcements/demo-scholarship']
    assert demo_links(client.get('/demo?category=活動')) == ['/demo/announcements/demo-event']
    assert demo_links(client.get('/demo?category=活動&q=獎學金')) == []
    assert '清除篩選' in client.get('/demo?q=no-match').text
    r = client.get('/demo/announcements/demo-notice')
    assert r.status_code == 200 and '未知' in r.text and '未提供摘要' in r.text
    for demo_id, date in zip(DEMO_IDS[:2], ('2026-09-01', '2026-09-02')):
        assert '示範日期：' + date in client.get('/demo/announcements/' + demo_id).text


def test_demo_never_reads_integrations(web, monkeypatch):
    client, app, _, _ = web
    login(client)
    valid_cookie = client.cookies.get(app.state.sessions.cookie_name)
    seed(app)

    def fail(*args, **kwargs):
        raise AssertionError('PRIVATE-MARKER: integration must not be accessed')

    monkeypatch.setattr(app.state.database, 'transaction', fail)
    monkeypatch.setattr(app.state.sessions, 'resolve', fail)
    monkeypatch.setattr(app.state.sync_service, 'sync_gmail_for_user', fail)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', fail)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', fail)
    for cookie in (None, valid_cookie, 'forged-cookie'):
        client.cookies.clear()
        if cookie:
            client.cookies.set(app.state.sessions.cookie_name, cookie)
        for path in ('/demo', *('/demo/announcements/' + x for x in DEMO_IDS)):
            r = client.get(path)
            assert r.status_code == 200
            assert NOTICE in r.text and 'PRIVATE-MARKER' not in r.text
            assert 'PUBLIC-STUDENT' not in r.text
            assert '最後成功更新' not in r.text and '已收錄公開公告' not in r.text


def test_demo_labels_unknown_ids_and_escaping(web):
    client, app, _, _ = web
    def counts():
        with app.state.database.transaction() as s:
            return tuple(s.scalar(select(func.count()).select_from(model))
                         for model in (PublicAnnouncement, User))
    before = counts()
    for path in ('/demo', *('/demo/announcements/' + x for x in DEMO_IDS)):
        r = client.get(path)
        assert r.status_code == 200 and NOTICE in r.text
        assert 'no-store' in r.headers['cache-control']
        assert 'content-security-policy' in r.headers
        assert not BeautifulSoup(r.text, 'html.parser').select('form[method="post"]')
        assert '加入待辦' not in r.text
    assert counts() == before
    assert client.get('/demo/announcements/1').status_code == 404
    assert client.get('/demo?category=UNKNOWN').status_code == 422
    assert client.get('/demo?q=' + 'x' * 201).status_code == 422
    r = client.get('/demo', params={'q': '<script>alert(1)</script>'})
    assert '<script>alert(1)</script>' not in r.text and '&lt;script&gt;' in r.text
    assert client.post('/demo').status_code == 405


def test_demo_source_data_is_immutable_and_search_is_literal():
    from dataclasses import FrozenInstanceError
    from app.services.demo_announcements import (
        DEMO_ANNOUNCEMENTS, list_demo_announcements, get_demo_announcement)
    assert len(DEMO_ANNOUNCEMENTS) == 3
    with pytest.raises(FrozenInstanceError):
        DEMO_ANNOUNCEMENTS[0].title = 'changed'
    assert list_demo_announcements('  獎學金  ')[0].id == 'demo-scholarship'
    assert list_demo_announcements('%') == ()
    assert get_demo_announcement('unknown') is None


def test_public_home_and_login_explain_optional_gmail(web):
    client, _, _, _ = web
    for path in ('/', '/login'):
        r = client.get(path)
        assert 'href="/demo"' in r.text
        assert '選用' in r.text and 'Google 測試名單' in r.text
