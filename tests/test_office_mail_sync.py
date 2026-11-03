import json
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import select,func
from app.models.public_announcements import PublicAnnouncement as P,PublicSourceState as S
from app.models.source_history import PublicSourceVersion as V
from app.services.public_source import PublicSourceError
from app.services.office_mail_source import parse_office_mail,OFFICE_SOURCE_KEY
from tests.test_office_mail_source import html,URL
from tests.test_multi_user_database import database
NOW=datetime(2026,11,4,tzinfo=timezone.utc)

def document(url=URL,body='建工校區施工，11/5西門封閉，請改走東門。'):
    return parse_office_mail(html('<p>'+body+'</p>'),url)

def test_import_dedup_version_update_and_source_isolation(database):
    from app.services.office_mail_sync import import_office_mail
    db,_=database
    r=import_office_mail(db,[URL,URL],source=document,now=NOW)
    assert r.added==1 and r.status=='success'
    assert import_office_mail(db,[URL],source=document,now=NOW+timedelta(hours=1)).unchanged==1
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(V))==1
        row=s.scalar(select(P));assert row.source_key==OFFICE_SOURCE_KEY
        snap=s.scalar(select(V)).snapshot
        assert snap['metadata']['office']['campus_flags']['jiangong']
        assert '施工' in snap['text']
    updated=import_office_mail(db,[URL],source=lambda u:document(u,'楠梓校區11/6改為停水。'),now=NOW+timedelta(hours=2))
    assert updated.updated==1
    assert import_office_mail(db,[URL[:-1]+'8'],source=document,now=NOW).added==1
    with db.transaction() as s:assert s.scalar(select(func.count()).select_from(V))==3


def test_refresh_failure_retains_body_brief_and_recovery(database):
    from app.services.office_mail_sync import import_office_mail,refresh_office_mail
    db,_=database;import_office_mail(db,[URL],source=document,now=NOW)
    def fail(u):raise RuntimeError('PRIVATE-KEY token=secret')
    r=refresh_office_mail(db,source=fail,now=NOW+timedelta(hours=1))
    assert r.failed==1 and r.status=='failed' and 'PRIVATE' not in str(r)
    with db.transaction() as s:
        row=s.scalar(select(P));assert '建工' in row.excerpt
        v=s.scalar(select(V).order_by(V.id.desc()));assert v.snapshot['metadata']['office']['campus_flags']['jiangong']
        assert v.snapshot['metadata']['office']['fetch_error']=='OFFICE_MAIL_UNAVAILABLE'
        assert s.get(S,OFFICE_SOURCE_KEY).last_success_at.replace(tzinfo=timezone.utc)==NOW
    assert refresh_office_mail(db,source=document,now=NOW+timedelta(hours=2)).status=='success'
    with db.transaction() as s:assert s.scalar(select(V).order_by(V.id.desc())).snapshot['metadata']['office']['fetch_error'] is None


def test_all_urls_are_validated_before_fetch_or_write(database):
    from app.services.office_mail_sync import import_office_mail
    db,_=database;calls=[]
    with pytest.raises(PublicSourceError):import_office_mail(db,[URL,'https://evil.invalid/private'],source=lambda u:calls.append(u))
    assert not calls
    with db.transaction() as s:assert s.scalar(select(func.count()).select_from(P))==0


def test_source_leases_are_independent_and_invalid_source_rejected(database):
    from app.services.public_sync import SourceLease
    db,_=database
    a=SourceLease(db,now=NOW);b=SourceLease(db,now=NOW,source_key=OFFICE_SOURCE_KEY)
    a.acquire();b.acquire()
    try:
        with db.transaction() as s:
            assert a.verify(s).source_key=='nkust-latest'
            assert b.verify(s).source_key==OFFICE_SOURCE_KEY
    finally:a.release();b.release()
    with pytest.raises(ValueError):SourceLease(db,source_key='private-email')


def test_office_cli_import_refresh_and_safe_failure_output(database,tmp_path,monkeypatch,capsys):
    from app.services import office_mail_sync
    from app.public_cli import main
    from app.config import Settings
    db,_=database
    monkeypatch.setattr('app.public_cli.Settings.load',lambda:Settings(database_url=db.engine.url))
    monkeypatch.setattr(office_mail_sync,'fetch_office_mail',document)
    urls=tmp_path/'urls.txt';urls.write_text(URL+'\n',encoding='utf-8')
    assert main(['office-import','--urls-file',str(urls)])==0
    assert json.loads(capsys.readouterr().out)['added']==1
    assert main(['office-refresh','--limit','8'])==0
    assert json.loads(capsys.readouterr().out)['unchanged']==1
    urls.write_text(URL+'?PRIVATE=secret',encoding='utf-8')
    assert main(['office-import','--urls-file',str(urls)])==1
    assert 'PRIVATE' not in capsys.readouterr().out


def test_partial_import_and_unknown_errors_do_not_leak(database):
    from app.services.office_mail_sync import import_office_mail
    db,_=database;other=URL[:-1]+'8'
    def source(url):
        if url==other:raise PublicSourceError('SECRET token=private')
        return document(url)
    r=import_office_mail(db,[URL,other],source=source,now=NOW)
    assert r.status=='partial' and r.added==1 and r.failed==1
    assert r.failures==[{'announcement_id':'69928','error_code':'OFFICE_MAIL_UNAVAILABLE'}]
    with db.transaction() as s:assert s.get(S,OFFICE_SOURCE_KEY).last_success_at is None
    with pytest.raises(PublicSourceError):import_office_mail(db,[URL]*21,source=source)


def test_official_mail_identity_remains_exact():
    from app.services.source_history import official_identity
    assert official_identity(URL)==URL
    assert official_identity(URL+'?token=secret') is None
    assert official_identity('https://officemail.nkust.edu.tw/Admin') is None
