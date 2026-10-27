from datetime import datetime,timezone
from sqlalchemy import select
from tests.test_sessions import web, login, csrf
from tests.test_auth import oauth
from app.models.multi_user import Email, Announcement
from app.models.public_announcements import PublicAnnouncement as P


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
