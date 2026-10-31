from datetime import datetime,timezone
from dataclasses import replace
from sqlalchemy import select,func
import pytest
from tests.test_sessions import web,login
from tests.test_auth import oauth
from tests.test_action_card_corrections import seed,A
from tests.test_source_identity import URL
from app.models.multi_user import Announcement,Email,User
from app.models.public_announcements import PublicAnnouncement as P
from app.models.source_history import PublicSourceVersion as PV,PrivateSourceVersion as MV
from app.services.source_history import record_public_version,record_private_version
from app.services.source_views import related_sources,private_version
from app.services.action_card_corrections import CorrectionNotFound

NOW=datetime(2026,10,30,tzinfo=timezone.utc)

def setup(c,app):
    login(c);db=app.state.database;aid=seed(db)
    with db.transaction() as s:
        a=s.get(Announcement,aid);a.url=URL+'#private';a.title='PRIVATE-A';a.original_text='報名截止：2026年11月12日 PRIVATE-A';a.original_html='<script>PRIVATE-A</script>'
        record_private_version(s,a,s.get(Email,a.email_id),NOW)
        s.add(User(id=2,google_user_id='google-b',email='b@example.invalid'));s.flush()
        e=Email(user_id=2,gmail_message_id='b',status='processed');s.add(e);s.flush()
        s.add(Announcement(user_id=2,email_id=e.id,source_index=0,source_fingerprint='b',department='test',source_category='test',title='PRIVATE-B',original_text='SECRET-B',url=URL))
        p=P(source_key='nkust-latest',canonical_url=URL,title='PUBLIC',excerpt='報名截止：2026年11月10日',content_hash='a');s.add(p);s.flush();record_public_version(s,p,NOW)
        p.excerpt='報名截止：2026年11月11日';record_public_version(s,p,NOW)
    return aid

def test_related_sources_owner_and_original_differences(web):
    c,app,_,_=web;aid=setup(c,app)
    r=c.get(f'/announcements/{aid}/sources');assert r.status_code==200
    assert 'PUBLIC' in r.text and 'PRIVATE-A' in r.text and 'PRIVATE-B' not in r.text and 'SECRET-B' not in r.text
    assert '來源差異' in r.text and '2026-11-11' in r.text and '2026-11-12' in r.text
    assert '<script>PRIVATE-A' not in r.text
    with pytest.raises(CorrectionNotFound):related_sources(app.state.database,replace(A,google_user_id='old-sub'),aid)
    with app.state.database.transaction() as s:s.get(Announcement,aid).url='https://www.nkust.edu.tw/'
    assert '無法可靠關聯' in c.get(f'/announcements/{aid}/sources').text
    assert c.get(f'/announcements/{aid}/sources?page=0').status_code==422

def test_public_history_never_resolves_session_or_exposes_private(web,monkeypatch):
    c,app,_,_=web;setup(c,app)
    def fail(*a,**kw):raise AssertionError('must not resolve session')
    monkeypatch.setattr(app.state.sessions,'resolve',fail)
    r=c.get('/public/announcements/1/history');assert r.status_code==200
    assert 'PRIVATE-A' not in r.text and 'SECRET-B' not in r.text
    assert '2026-11-10' in r.text and '2026-11-11' in r.text and '留存時間' in r.text

def test_private_history_survives_reparse_escaped_read_only_and_owner(web):
    c,app,google,_=web;aid=setup(c,app);db=app.state.database
    with db.transaction() as s:
        before=s.scalar(select(func.count()).select_from(MV));s.delete(s.get(Announcement,aid))
    assert c.get('/my/source-history').status_code==200
    r=c.get('/my/source-history/1');assert r.status_code==200 and 'PRIVATE-A' in r.text
    assert '<script>PRIVATE-A' not in r.text and '&lt;script&gt;' in r.text
    with db.transaction() as s:assert s.scalar(select(func.count()).select_from(MV))==before
    c.cookies.clear();assert c.get('/my/source-history/1').status_code==303
    google.claims={'sub':'google-b','email':'b@example.invalid'};login(c)
    assert c.get('/my/source-history/1').status_code==404
    assert 'PRIVATE-A' not in c.get('/my/source-history').text

def test_history_pagination_and_corrupt_snapshot_returns_503(web):
    c,app,_,_=web;setup(c,app);db=app.state.database
    with db.transaction() as s:
        a=s.scalar(select(Announcement).where(Announcement.user_id==1));e=s.get(Email,a.email_id)
        for i in range(21):a.original_text=f'PRIVATE-VERSION-{i}';record_private_version(s,a,e,NOW)
    r=c.get('/my/source-history');assert '下一頁' in r.text
    assert 'PRIVATE-A' in c.get('/my/source-history?page=2').text
    with db.transaction() as s:s.get(MV,1).snapshot={'broken':True}
    assert c.get('/my/source-history/1').status_code==503
    assert '並非沒有紀錄' in c.get('/my/source-history/1').text


def test_related_exact_matching_precedes_pagination_and_does_not_merge_titles(web):
    c,app,_,_=web;aid=setup(c,app)
    with app.state.database.transaction() as s:
        a=s.get(Announcement,aid)
        for i in range(23):
            s.add(Announcement(user_id=1,email_id=a.email_id,source_index=i+1,source_fingerprint=str(i),
                department='test',source_category='test',title=f'SAME-TITLE-{i}',original_text='synthetic',
                url=URL+'2' if i<2 else URL+'#'+str(i)))
    one=c.get(f'/announcements/{aid}/sources');two=c.get(f'/announcements/{aid}/sources?page=2')
    assert '下一頁' in one.text and 'SAME-TITLE-22' in two.text
    assert 'SAME-TITLE-0<' not in one.text and 'SAME-TITLE-1<' not in one.text
    assert 'SAME-TITLE-22' not in one.text

def test_public_history_pagination_empty_and_corrupt_fail_closed(web):
    c,app,_,_=web;setup(c,app)
    with app.state.database.transaction() as s:
        p=s.get(P,1)
        for i in range(21):p.excerpt=f'PUBLIC-VERSION-{i}';record_public_version(s,p,NOW)
    one=c.get('/public/announcements/1/history');two=c.get('/public/announcements/1/history?page=2')
    assert '下一頁' in one.text and 'PUBLIC-VERSION-0' in two.text
    assert '尚無留存版本' in c.get('/public/announcements/1/history?page=10').text
    with app.state.database.transaction() as s:s.get(PV,1).snapshot={'broken':True}
    assert c.get('/public/announcements/1/history?page=2').status_code==503


def test_related_sources_include_default_https_port_from_both_anchors(web):
    c,app,_,_=web;aid=setup(c,app)
    with app.state.database.transaction() as s:
        a=s.get(Announcement,aid)
        b=Announcement(user_id=1,email_id=a.email_id,source_index=7,source_fingerprint='port',department='test',source_category='test',title='PORT-443',original_text='synthetic',url=URL.replace('.tw/','.tw:443/'))
        s.add(b);s.flush();bid=b.id
    for anchor in (aid,bid):
        r=c.get(f'/announcements/{anchor}/sources')
        assert f'href="/announcements/{aid}"' in r.text and f'href="/announcements/{bid}"' in r.text
