"""Bounded owner discovery. Only anonymously re-fetched pages reach public tables."""
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta,timezone
import time
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.core.session import CurrentUser
from app.core.office_discovery import DiscoveryError
from app.database.office_discovery import DiscoveryRepository
from app.database.user_mail import UserSyncLease,SyncBusy,SyncLeaseLost,UserAccountChanged
from app.models.multi_user import User
from app.models.public_announcements import PublicSourceState as S,PublicSyncRun as R
from app.services.office_mail_discovery_source import extract_office_urls
from app.services.office_mail_sync import import_office_mail
from app.services.public_sync import aware
from app.services.gmail_service import GmailError
from app.services.user_gmail_service import GmailReauthorizationRequired
from app.services.email_parser import EmailParseError
class _BudgetPending(Exception):pass
KEY='nkust-office-discovery'
SAFE={'GMAIL_REAUTHORIZE','GMAIL_CREDENTIALS_UNAVAILABLE','GMAIL_DISCOVERY_UNAVAILABLE','GMAIL_RESPONSE_INVALID','GMAIL_DISCOVERY_PAGE_TOKEN','OFFICE_DISCOVERY_BUSY','OFFICE_DISCOVERY_COOLDOWN','OFFICE_DISCOVERY_LEASE','OFFICE_DISCOVERY_IDENTITY','OFFICE_DISCOVERY_PENDING','OFFICE_DISCOVERY_SOURCE_UNAVAILABLE','OFFICE_DISCOVERY_OWNER_UNAVAILABLE','OFFICE_DISCOVERY_DISABLED','OFFICE_DISCOVERY_UNAVAILABLE'}
@dataclass
class DiscoveryResult:
 status:str='success'
 scanned:int=0
 discovered:int=0
 published:int=0
 rejected:int=0
 pending:int=0
 error_code:str|None=None
 def to_public_dict(self):return asdict(self)

def _code(exc):
 code=str(exc).split(':',1)[0]
 return code if code in SAFE else 'OFFICE_DISCOVERY_UNAVAILABLE'

def _summary(repo,token,result,started,now):
 state=repo.state()
 with repo.database.transaction() as s:
  repo.fence(s,token,now);public=s.get(S,KEY)
  if public is None:public=S(source_key=KEY);s.add(public)
  public.last_success_at=state.get('last_complete_scan_at')
  public.history_status='complete' if state.get('window_complete') else 'incomplete'
  s.add(R(source_key=KEY,mode='recent',status=result.status,started_at=started,finished_at=now,added=result.published,updated=0,unchanged=0,failed=1 if result.error_code not in (None,'OFFICE_DISCOVERY_PENDING') else 0,error_code=result.error_code))

def _early_failure(database,result,stamp):
 with database.transaction() as s:
  if s.get(S,KEY) is None:s.add(S(source_key=KEY))
  s.add(R(source_key=KEY,mode='recent',status='failed',started_at=stamp,finished_at=stamp,added=0,updated=0,unchanged=0,failed=1,error_code=result.error_code))
 return result

def run_office_discovery(database,settings,gmail_factory,*,now=None,monotonic=None,public_source=None):
 clock=now or (lambda:datetime.now(timezone.utc));tick=monotonic or time.monotonic
 result=DiscoveryResult();started=clock();deadline=tick()+60
 if not settings.enabled:return DiscoveryResult(status='failed',error_code='OFFICE_DISCOVERY_DISABLED')
 with database.transaction() as s:
  row=s.scalar(select(User).where(User.google_user_id==settings.owner_sub))
  if row is None:owner=None
  else:owner=CurrentUser(row.id,row.email,row.display_name,row.google_user_id)
 if owner is None:return _early_failure(database,DiscoveryResult(status='failed',error_code='OFFICE_DISCOVERY_OWNER_UNAVAILABLE'),started)
 repo=DiscoveryRepository(database,owner)
 try:token=repo.acquire(clock())
 except DiscoveryError as exc:return DiscoveryResult(status='busy',error_code=_code(exc))
 try:
  state=repo.state();end=state.get('window_end');start=state.get('window_start');page_token=state.get('page_token')
  if not end or state.get('window_complete'):
   start=aware(end)-timedelta(hours=24) if end else started-timedelta(days=14);end=started;page_token=None
   repo.commit_page(token,window_start=start,window_end=end,page_token=None,urls=[],complete=False,now=clock())
  else:start=aware(start);end=aware(end)
  if deadline-tick()<10:raise _BudgetPending()
  user_lease=UserSyncLease(database,owner.id,google_user_id=owner.google_user_id,now=clock);user_lease.acquire()
  try:
   with gmail_factory.discovery(owner,timeout_seconds=max(1,min(10,int(deadline-tick())))) as gmail:
    restarted=False
    for _ in range(2):
     if deadline-tick()<10:break
     try:ids,next_token=gmail.list_discovery_page(start,end,page_token=page_token)
     except GmailError as exc:
      if str(exc)=='GMAIL_DISCOVERY_PAGE_TOKEN' and page_token and not restarted:
       page_token=None;restarted=True
       repo.commit_page(token,window_start=start,window_end=end,page_token=None,urls=[],complete=False,now=clock());continue
      raise
     urls=[];page_complete=True
     for mid in ids:
      if deadline-tick()<10:page_complete=False;break
      user_lease.heartbeat()
      try:urls.extend(extract_office_urls(gmail.read_message(mid)))
      except EmailParseError:pass
      result.scanned+=1
     if not page_complete:break
     old=sum(repo.counts().values())
     repo.commit_page(token,window_start=start,window_end=end,page_token=next_token,urls=urls,complete=not next_token,now=clock())
     result.discovered+=sum(repo.counts().values())-old
     page_token=next_token
     if not next_token:break
  finally:user_lease.release()
  # User lease has been released before acquiring the public source lease.
  for candidate in repo.due_candidates(token,clock(),3):
   if deadline-tick()<15:break
   with database.transaction() as s:repo.fence(s,token,clock())
   imported=import_office_mail(database,[candidate['url']],source=public_source,now=clock(),write_fence=lambda session:repo.fence(session,token,clock()))
   if not imported.failed:
    result.published+=imported.added
    repo.mark_candidate(token,candidate['url'],status='published',now=clock())
   else:
    error=imported.failures[0]['error_code']
    permanent=error in {'OFFICE_MAIL_NOT_PUBLIC','OFFICE_MAIL_STRUCTURE','OFFICE_MAIL_BODY','OFFICE_MAIL_ENCODING','OFFICE_MAIL_SIZE','OFFICE_MAIL_HTTP_404','OFFICE_MAIL_URL','OFFICE_MAIL_REDIRECT'}
    delay=(1,6,24)[min(candidate['attempts'],2)]
    repo.mark_candidate(token,candidate['url'],status='rejected' if permanent else 'retry',error_code=error,next_retry_at=None if permanent else clock()+timedelta(hours=delay),now=clock())
    if permanent:result.rejected+=1
    else:result.error_code='OFFICE_DISCOVERY_SOURCE_UNAVAILABLE'
  counts=repo.counts();result.pending=counts.get('pending',0)+counts.get('retry',0)
  if result.pending or not repo.state().get('window_complete') or result.error_code:
   result.status='partial';result.error_code=result.error_code or 'OFFICE_DISCOVERY_PENDING'
 except _BudgetPending:
  result.status='partial';result.error_code='OFFICE_DISCOVERY_PENDING'
  counts=repo.counts();result.pending=counts.get('pending',0)+counts.get('retry',0)
 except Exception as exc:
  result.status='failed';result.error_code=_code(exc)
  try:counts=repo.counts();result.pending=counts.get('pending',0)+counts.get('retry',0)
  except (DiscoveryError,SQLAlchemyError):pass
 finally:
  try:
   repo.report(token,result.status,result.error_code,clock());_summary(repo,token,result,started,clock())
  except (DiscoveryError,SQLAlchemyError):
   result.status='failed';result.error_code='OFFICE_DISCOVERY_UNAVAILABLE'
   _early_failure(database,result,clock())
  finally:repo.release(token)
 return result
