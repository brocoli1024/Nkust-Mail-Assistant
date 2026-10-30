from datetime import datetime,timedelta,timezone
from dataclasses import replace
from sqlalchemy import select,func,delete
import pytest
from tests.test_multi_user_database import database
from tests.test_source_identity import URL
from tests.test_public_source import feed,item
from tests.test_api import mail
from app.models.source_history import PublicSourceVersion as PV,PrivateSourceVersion as MV
from app.models.public_announcements import PublicAnnouncement as P
from app.models.multi_user import User,Announcement
from app.services.public_sync import sync_recent
from app.services.source_history import snapshot_changes
from app.database.user_mail import UserMailRepository,UserSyncLease
from app.services.announcement_parser import parse_email

NOW=datetime(2026,10,30,tzinfo=timezone.utc)

def sync(db,text,minute=0):return sync_recent(db,source=lambda:feed(item(url=URL,excerpt=text)),now=NOW+timedelta(minutes=minute))

def test_public_versions_keep_a_b_a_and_unchanged(database):
    db,_=database
    for i,text in enumerate(['報名截止：2026年11月10日','報名截止：2026年11月12日','報名截止：2026年11月10日']):assert sync(db,text,i).status=='success'
    sync(db,'報名截止：2026年11月10日',4)
    with db.transaction() as s:
        rows=s.scalars(select(PV).order_by(PV.id)).all()
        assert len(rows)==3 and rows[0].snapshot==rows[2].snapshot
        assert any('2026-11-12' in x for x in snapshot_changes(rows[0].snapshot,rows[1].snapshot))
        assert all(r.snapshot['source_kind']=='public' and r.snapshot['html'] is None for r in rows)

def test_preexisting_public_baseline_and_archive_failure_roll_back(database,monkeypatch):
    db,_=database
    with db.transaction() as s:s.add(P(source_key='nkust-latest',canonical_url=URL,title='原始公開標題',excerpt='舊內容',content_hash='old'))
    sync(db,'新內容')
    with db.transaction() as s:
        rows=s.scalars(select(PV).order_by(PV.id)).all();assert len(rows)==2 and rows[0].baseline
        assert rows[0].snapshot['text']=='舊內容'
    import app.services.source_history as history
    def fail(*a,**kw):raise RuntimeError('synthetic archive failure')
    monkeypatch.setattr(history,'record_public_version',fail)
    assert sync(db,'不可提交內容',2).status=='failed'
    with db.transaction() as s:
        assert s.scalar(select(P)).excerpt=='新內容'
        assert s.scalar(select(func.count()).select_from(PV))==2

def test_private_reparse_retains_original_and_isolates_cascade(database):
    db,_=database;email=mail('a');lease=UserSyncLease(db,1,google_user_id='google-a');lease.acquire()
    try:
        repo=UserMailRepository(db,1,lease);result=parse_email(email)
        repo.save_processed(email,result,'v1')
        count=len(result.announcements)
        changed=replace(email,html_body=email.html_body.replace('獎學金','變更獎學金'))
        repo.save_processed(changed,parse_email(changed),'v2',force=True)
        with db.transaction() as s:
            versions=s.scalars(select(MV).order_by(MV.id)).all()
            assert len(versions)>=count*2
            assert any(v.snapshot['metadata']['source_parser_version']=='v1' for v in versions)
            assert any(v.snapshot['metadata']['source_parser_version']=='v2' for v in versions)
            assert any(v.snapshot['html'] for v in versions)
            assert s.scalar(select(func.count()).select_from(Announcement))==count
        repo.save_processed(changed,parse_email(changed),'v2',force=True)
        with db.transaction() as s:assert s.scalar(select(func.count()).select_from(MV))==len(versions)
    finally:lease.release()
    sync(db,'公開不動')
    with db.transaction() as s:s.execute(delete(User).where(User.id==1))
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(MV))==0
        assert s.scalar(select(func.count()).select_from(PV))==1 and s.get(User,2)


def test_private_archive_failure_rolls_back_original(database,monkeypatch):
    db,_=database;email=mail('rollback');lease=UserSyncLease(db,1,google_user_id='google-a');lease.acquire()
    try:
        repo=UserMailRepository(db,1,lease);repo.save_processed(email,parse_email(email),'v1')
        with db.transaction() as s:before=[v.snapshot for v in s.scalars(select(MV).order_by(MV.id))]
        import app.services.source_history as history
        original=history.record_private_version
        def fail(session,row,email,now,**kwargs):
            original(session,row,email,now,**kwargs)
            if kwargs.get('parser_version')=='v2':raise RuntimeError('synthetic write failure')
        monkeypatch.setattr(history,'record_private_version',fail)
        with pytest.raises(RuntimeError):repo.save_processed(email,parse_email(email),'v2',force=True)
        with db.transaction() as s:
            from app.models.multi_user import Email
            assert s.scalar(select(Email)).parser_version=='v1'
            assert [v.snapshot for v in s.scalars(select(MV).order_by(MV.id))]==before
    finally:lease.release()
