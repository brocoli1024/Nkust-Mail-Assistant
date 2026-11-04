from dataclasses import replace
from datetime import timedelta
from sqlalchemy import select
import pytest
from tests.test_office_discovery_state import database,OWNER,NOW,URL
from tests.test_office_discovery_source import EMAIL
from tests.test_office_mail_sync import document
from app.core.office_discovery import DiscoverySettings
from app.services.office_mail_discovery import run_office_discovery
from app.database.office_discovery import DiscoveryRepository
from app.models.public_announcements import PublicAnnouncement,PublicSourceState
from app.models.source_history import PublicSourceVersion
from app.services.gmail_service import GmailError
SETTINGS=DiscoverySettings(True,'google-a','x'*40)
URL2=URL[:-1]+'2'
class Mail:
 def __init__(self,pages=None,fail=None):self.pages=pages or {None:(('m1','m2','m3'),None)};self.fail=fail;self.closed=False;self.calls=[]
 def __enter__(self):return self
 def __exit__(self,*args):self.closed=True
 def list_discovery_page(self,start,end,*,page_token=None):self.calls.append((start,end,page_token));return self.pages[page_token]
 def read_message(self,mid):
  if mid==self.fail:raise GmailError('GMAIL_DISCOVERY_UNAVAILABLE')
  return replace(EMAIL,text_body=(URL2 if mid=='m2' else URL)+' PRIVATE-BODY')
class Factory:
 def __init__(self,mail):self.mail=mail
 def discovery(self,owner,*,timeout_seconds):assert owner.google_user_id=='google-a' and 1<=timeout_seconds<=10;return self.mail

def execute(db,mail,now=NOW,source=None):return run_office_discovery(db,SETTINGS,Factory(mail),now=lambda:now,public_source=source or (lambda url:document(url,'官方合成公開內容')))

def test_owner_mail_only_discovers_and_publication_uses_anonymous_page(database):
 db,_=database;mail=Mail();r=execute(db,mail)
 assert r.to_public_dict()['published']==2 and r.scanned==3 and r.discovered==2 and r.pending==0 and mail.closed
 with db.transaction() as s:
  assert len(s.scalars(select(PublicAnnouncement)).all())==2
  for version in s.scalars(select(PublicSourceVersion)):assert 'PRIVATE' not in str(version.snapshot)
  assert s.get(PublicSourceState,'nkust-office-discovery').last_success_at is not None
 r=execute(db,Mail(),NOW+timedelta(seconds=301));assert r.published==0 and r.pending==0

def test_partial_page_is_not_skipped_on_next_run(database):
 db,_=database;r=execute(db,Mail(fail='m2'));assert r.status=='failed' and r.discovered==0
 state=DiscoveryRepository(db,OWNER).state();assert not state['window_complete'] and state['page_token'] is None
 r=execute(db,Mail(),NOW+timedelta(seconds=301));assert r.published==2

def test_backfill_continues_after_twenty_and_complete_time_is_not_faked(database):
 db,_=database;pages={None:(tuple('m'+str(i) for i in range(10)),'p1'),'p1':(tuple('n'+str(i) for i in range(10)),'p2'),'p2':(('last',),None)}
 first=execute(db,Mail(pages));assert first.scanned==20 and first.status=='partial'
 state=DiscoveryRepository(db,OWNER).state();assert state['page_token']=='p2' and not state['last_complete_scan_at']
 m=Mail(pages);second=execute(db,m,NOW+timedelta(seconds=301));assert second.status=='success' and m.calls[0][2]=='p2'

def test_source_failure_retries_without_losing_candidate(database):
 from app.services.public_source import PublicSourceError
 db,_=database
 def unavailable(url):raise PublicSourceError('PUBLIC_SOURCE_UNAVAILABLE')
 first=execute(db,Mail(),source=unavailable);assert first.pending==2 and first.status=='partial'
 state=DiscoveryRepository(db,OWNER).counts();assert state=={'retry':2}
 second=execute(db,Mail(),NOW+timedelta(hours=2));assert second.published==2 and not second.pending


def test_owner_deleted_during_public_fetch_cannot_publish(database):
 from sqlalchemy import delete,func
 from app.models.multi_user import User
 db,_=database
 def deleted(url):
  with db.transaction() as s:s.execute(delete(User).where(User.id==OWNER.id))
  return document(url,'官方合成公開內容')
 r=execute(db,Mail(),source=deleted)
 assert r.status=='failed'
 with db.transaction() as s:assert s.scalar(select(func.count()).select_from(PublicAnnouncement))==0

def test_public_commit_before_candidate_mark_is_idempotent(database,monkeypatch):
 from sqlalchemy import func
 from sqlalchemy.exc import SQLAlchemyError
 db,_=database;original=DiscoveryRepository.mark_candidate
 def interrupted(*args,**kwargs):raise SQLAlchemyError('PRIVATE-ERROR')
 monkeypatch.setattr(DiscoveryRepository,'mark_candidate',interrupted)
 assert execute(db,Mail()).status=='failed'
 monkeypatch.setattr(DiscoveryRepository,'mark_candidate',original)
 r=execute(db,Mail(),NOW+timedelta(seconds=301))
 assert r.pending==0
 with db.transaction() as s:assert s.scalar(select(func.count()).select_from(PublicAnnouncement))==2


def test_page_token_recovery_reopens_same_fixed_window(database):
 db,_=database;r=DiscoveryRepository(db,OWNER);t=r.acquire(NOW)
 r.commit_page(t,window_start=NOW-timedelta(days=14),window_end=NOW,page_token='expired',urls=[],complete=False,now=NOW);r.release(t)
 class Expired(Mail):
  def list_discovery_page(self,start,end,*,page_token=None):
   if page_token:raise GmailError('GMAIL_DISCOVERY_PAGE_TOKEN')
   return super().list_discovery_page(start,end,page_token=page_token)
 mail=Expired();result=execute(db,mail,NOW+timedelta(seconds=301))
 assert result.published==2 and mail.calls[0][:2]==(NOW-timedelta(days=14),NOW)

def test_budget_exhaustion_before_client_does_not_read_gmail(database):
 db,_=database
 class Never:
  def discovery(self,*a,**kw):raise AssertionError('must not connect')
 ticks=iter((0,61));r=run_office_discovery(db,SETTINGS,Never(),now=lambda:NOW,monotonic=lambda:next(ticks,61))
 assert r.status=='partial' and r.error_code=='OFFICE_DISCOVERY_PENDING'

def test_restricted_pages_are_rejected_without_public_content(database):
 from app.services.public_source import PublicSourceError
 from sqlalchemy import func
 db,_=database
 def restricted(url):raise PublicSourceError('OFFICE_MAIL_NOT_PUBLIC')
 r=execute(db,Mail(),source=restricted);assert r.rejected==2 and r.pending==0
 with db.transaction() as s:assert not s.scalar(select(func.count()).select_from(PublicAnnouncement))


def test_missing_provider_records_public_safe_failure(database):
 from sqlalchemy import delete
 from app.models.multi_user import User
 from app.models.public_announcements import PublicSyncRun
 db,_=database
 with db.transaction() as s:s.execute(delete(User).where(User.id==OWNER.id))
 r=execute(db,Mail());assert r.error_code=='OFFICE_DISCOVERY_OWNER_UNAVAILABLE'
 with db.transaction() as s:
  last=s.scalar(select(PublicSyncRun).where(PublicSyncRun.source_key=='nkust-office-discovery'))
  assert last and last.status=='failed'
