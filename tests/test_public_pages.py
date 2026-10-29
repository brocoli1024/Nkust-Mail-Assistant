from datetime import datetime,timezone
from sqlalchemy import select
from tests.test_sessions import web, login, csrf
from tests.test_auth import oauth
from app.models.multi_user import Email, Announcement
from app.models.public_announcements import PublicAnnouncement as P
from app.models.public_announcements import PublicSourceState, PublicSyncRun
from bs4 import BeautifulSoup
import pytest


def seed(app):
    with app.state.database.transaction() as s:
        s.add_all([
            P(id=1,source_key='nkust-latest',canonical_url='https://osa.nkust.edu.tw/a',title='PUBLIC-STUDENT 獎學金',excerpt='<script>bad()</script>',content_hash='a',student_relevance='relevant',category='獎學金'),
            P(id=2,source_key='nkust-latest',canonical_url='https://osa.nkust.edu.tw/b',title='PUBLIC-UNKNOWN',excerpt='',content_hash='b'),
            P(id=3,source_key='nkust-latest',canonical_url='https://osa.nkust.edu.tw/c',title='PUBLIC-STAFF',excerpt='',content_hash='c',student_relevance='not_student')])


def test_anonymous_public_pages_never_resolve_private_sessions(web,monkeypatch):
    client,app,_,_=web
    login(client)
    uid=client.get('/api/me').json()['id']
    seed(app)
    with app.state.database.transaction() as s:
        e=Email(user_id=uid,gmail_message_id='private-marker',status='processed')
        s.add(e)
        s.flush()
        s.add(Announcement(id=900,user_id=uid,email_id=e.id,source_index=0,source_fingerprint='f',
                           department='私人單位',source_category='私人分類',title='PRIVATE-MARKER',original_text='PRIVATE-BODY'))
    def fail(*args): raise RuntimeError('public routes must not read private sessions')
    monkeypatch.setattr(app.state.sessions,'resolve',fail)
    for cookie in (None,'forged-cookie'):
        client.cookies.clear()
        if cookie: client.cookies.set(app.state.sessions.cookie_name,cookie)
        for path in ('/','/public/announcements','/public/announcements/1'):
            r=client.get(path)
            assert r.status_code==200
            assert 'PRIVATE-MARKER' not in r.text and 'PRIVATE-BODY' not in r.text
        assert client.get('/public/announcements/900').status_code==404


def test_student_filter_does_not_delete_unknown_rows(web):
    client,app,_,_=web
    seed(app)
    all_rows=client.get('/public/announcements')
    assert all(x in all_rows.text for x in ('PUBLIC-STUDENT','PUBLIC-UNKNOWN','PUBLIC-STAFF'))
    filtered=client.get('/public/announcements?audience=student&q=PUBLIC&category=獎學金')
    assert 'PUBLIC-STUDENT' in filtered.text and 'PUBLIC-UNKNOWN' not in filtered.text
    assert 'PUBLIC-STAFF' not in filtered.text
    assert 'PUBLIC-UNKNOWN' in client.get('/public/announcements').text


def test_public_validation_escaping_and_no_write_routes(web):
    client,app,_,_=web
    seed(app)
    r=client.get('/public/announcements/1')
    assert '<script>bad()</script>' not in r.text and '&lt;script&gt;' in r.text
    for query in ('audience=other','page=0','category=UNKNOWN','q='+'x'*201):
        assert client.get('/public/announcements?'+query).status_code==422
    assert client.post('/public/announcements').status_code==405
    assert client.get('/announcements').status_code==303
    assert client.get('/api/me').status_code==401
    assert 'no-store' in r.headers['cache-control'] and 'content-security-policy' in r.headers
    with app.state.database.transaction() as s:
        s.get(P,1).canonical_url='javascript:alert(1)'
    assert 'javascript:' not in client.get('/public/announcements/1').text


def test_public_pagination_keeps_filters_and_literal_search(web):
    client,app,_,_=web
    with app.state.database.transaction() as s:
        for i in range(22):
            s.add(P(source_key='nkust-latest',canonical_url=f'https://osa.nkust.edu.tw/{i}',
                    title=f'學生公告-{i}',excerpt='',content_hash=str(i),student_relevance='relevant'))
    r=client.get('/public/announcements?audience=student&q=學生')
    assert r.status_code==200 and 'page=2' in r.text and 'audience=student' in r.text
    assert '學生公告-0' in client.get('/public/announcements?audience=student&page=2').text
    assert '學生公告-' not in client.get('/public/announcements?q=%25').text


def test_account_deletion_preserves_public_announcements(web):
    client,app,_,_=web
    seed(app)
    login(client)
    r=client.post('/account/delete',data={'confirm':'DELETE','csrf_token':csrf(client)})
    assert r.status_code==303
    assert 'PUBLIC-STUDENT' in client.get('/public/announcements').text


@pytest.mark.parametrize('run_status', ['failed', 'partial'])
def test_source_status_is_visible_on_all_public_pages(web, run_status):
    client, app, _, _ = web
    seed(app)
    with app.state.database.transaction() as s:
        s.add(PublicSourceState(source_key='nkust-latest',
            last_success_at=datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc),
            history_status='incomplete'))
        s.add(PublicSyncRun(source_key='nkust-latest', mode='recent', status=run_status,
            started_at=datetime(2026, 10, 29, 2, 0, tzinfo=timezone.utc)))
    for path in ('/', '/public/announcements', '/public/announcements/1'):
        response = client.get(path)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, 'html.parser')
        status = soup.select_one('[aria-label="公告來源與更新狀態"]')
        assert status is not None
        for details in status.select('details'):
            details.decompose()
        text = status.get_text()
        assert '高科大最新消息' in text
        assert '2026-10-28 10:00' in text
        assert '台灣時間' in text and '保留先前取得的資料' in text
        assert '僅涵蓋指定來源' in text
        assert '2026-10-29 10:00' not in text


def test_missing_success_is_not_invented(web):
    client, app, _, _ = web
    seed(app)
    for path in ('/', '/public/announcements', '/public/announcements/1'):
        assert '尚無成功更新紀錄' in client.get(path).text


def test_empty_source_differs_from_empty_search(web):
    client, app, _, _ = web
    response = client.get('/public/announcements')
    assert '目前尚無收錄資料' in response.text and 'href="/demo"' in response.text
    seed(app)
    response = client.get('/public/announcements?q=does-not-match')
    assert '沒有符合篩選的公告' in response.text
    assert '目前尚無收錄資料' not in response.text
    assert '清除篩選' in response.text


@pytest.mark.parametrize('path,code', [
    ('/public/announcements?q=' + 'x' * 201, 422),
    ('/public/announcements?category=UNKNOWN', 422),
    ('/public/announcements?page=0', 422),
    ('/public/announcements/900', 404),
    ('/public/announcements/not-an-id', 422),
    ('/demo?category=UNKNOWN', 422),
    ('/demo?q=' + 'x' * 201, 422),
    ('/demo/announcements/missing', 404),
])
def test_public_page_errors_are_safe_html(web, path, code):
    client, _, _, _ = web
    r = client.get(path)
    assert r.status_code == code
    assert r.headers['content-type'].startswith('text/html')
    assert '返回合成示範' in r.text if path.startswith('/demo') else '返回公開公告' in r.text
    assert '請檢查搜尋與篩選條件' in r.text if code == 422 else '找不到這則公告' in r.text
    assert 'no-store' in r.headers['cache-control']
    assert 'content-security-policy' in r.headers
    if path.startswith('/demo'):
        assert '合成示範資料，非高科大真實公告' in r.text


@pytest.mark.parametrize('path', ['/', '/public/announcements', '/public/announcements/1'])
def test_public_database_failure_has_retry_without_exposing_error(web, monkeypatch, path):
    from sqlalchemy.exc import SQLAlchemyError
    client, app, _, _ = web
    def fail(*args, **kwargs):
        raise SQLAlchemyError('PRIVATE-SQL-MARKER')
    monkeypatch.setattr(app.state.database, 'transaction', fail)
    r = client.get(path)
    assert r.status_code == 503
    assert r.headers['content-type'].startswith('text/html')
    assert '暫時無法讀取公告' in r.text and '重新載入' in r.text
    assert 'PRIVATE-SQL-MARKER' not in r.text
    assert 'href="/demo"' in r.text


def test_public_errors_do_not_change_private_api_contracts(web):
    client, _, _, _ = web
    r = client.get('/api/me')
    assert r.status_code == 401 and r.headers['content-type'].startswith('application/json')
    login(client)
    r = client.get('/announcements?page=0')
    assert r.status_code == 422 and r.json()['error'] == 'INVALID_REQUEST'
    assert client.post('/demo').status_code == 405


def test_public_filter_form_preserves_get_and_no_old_page(web):
    client, app, _, _ = web
    seed(app)
    for path in ('/public/announcements?page=2&category=獎學金', '/demo?category=活動'):
        r = client.get(path)
        soup = BeautifulSoup(r.text, 'html.parser')
        form = soup.select_one('#announcement-filters')
        assert form['method'] == 'get' and not form.select('[name="page"]')
        assert form.select_one('noscript button[type="submit"]')
        assert form.select_one('option[selected]').text in ('全部公告', '獎學金', '活動')
        assert soup.select_one('#filter-status[role="status"][aria-live="polite"]')
