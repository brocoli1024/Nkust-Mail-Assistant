"""Identity-fenced private progress, with durable page commits."""
from datetime import timedelta
import secrets
from sqlalchemy import select,update,or_,func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.multi_user import User
from app.models.office_discovery import OfficeDiscoveryState as S,OfficeDiscoveryCandidate as C
from app.core.office_discovery import DiscoveryError
from app.services.office_mail_source import normalize_office_url
from app.services.public_sync import aware
class DiscoveryRepository:
 def __init__(self,database,owner):self.database=database;self.owner=owner
 def identity(self,s):
  if s.scalar(select(User.google_user_id).where(User.id==self.owner.id).with_for_update())!=self.owner.google_user_id:raise DiscoveryError('OFFICE_DISCOVERY_IDENTITY')
 def acquire(self,now):
  token=secrets.token_hex(32);insert=sqlite_insert if self.database.engine.dialect.name=='sqlite' else pg_insert
  with self.database.transaction() as s:
   self.identity(s)
   statement=insert(S).values(user_id=self.owner.id,google_user_id=self.owner.google_user_id,window_complete=False,last_status='running',lease_owner=token,lease_expires_at=now+timedelta(seconds=120),next_allowed_at=now+timedelta(seconds=300))
   statement=statement.on_conflict_do_update(index_elements=[S.user_id],set_={'lease_owner':token,'lease_expires_at':now+timedelta(seconds=120),'next_allowed_at':now+timedelta(seconds=300),'last_status':'running'},where=((S.lease_expires_at.is_(None))|(S.lease_expires_at<=now))&((S.next_allowed_at.is_(None))|(S.next_allowed_at<=now))&(S.google_user_id==self.owner.google_user_id)).returning(S.user_id)
   if s.scalar(statement) is None:
    old=s.get(S,self.owner.id)
    busy=old and old.lease_expires_at and aware(old.lease_expires_at)>aware(now)
    raise DiscoveryError('OFFICE_DISCOVERY_BUSY' if busy else 'OFFICE_DISCOVERY_COOLDOWN')
  return token
 def fence(self,s,token,now):
  self.identity(s)
  result=s.execute(update(S).where(S.user_id==self.owner.id,S.google_user_id==self.owner.google_user_id,S.lease_owner==token,S.lease_expires_at>now).values(lease_expires_at=now+timedelta(seconds=120)))
  if result.rowcount!=1:raise DiscoveryError('OFFICE_DISCOVERY_LEASE')
 def release(self,token):
  with self.database.transaction() as s:s.execute(update(S).where(S.user_id==self.owner.id,S.google_user_id==self.owner.google_user_id,S.lease_owner==token).values(lease_owner=None,lease_expires_at=None))
 def state(self):
  with self.database.transaction() as s:
   self.identity(s);row=s.get(S,self.owner.id)
   if row and row.google_user_id!=self.owner.google_user_id:raise DiscoveryError('OFFICE_DISCOVERY_IDENTITY')
   return {c.name:getattr(row,c.name) for c in S.__table__.columns} if row else {}
 def commit_page(self,token,*,window_start,window_end,page_token,urls,complete,now):
  urls=list(dict.fromkeys(normalize_office_url(u) for u in urls))
  insert=sqlite_insert if self.database.engine.dialect.name=='sqlite' else pg_insert
  with self.database.transaction() as s:
   self.fence(s,token,now);row=s.get(S,self.owner.id)
   for url in urls:s.execute(insert(C).values(user_id=self.owner.id,canonical_url=url,discovered_at=now,status='pending',attempts=0).on_conflict_do_nothing(index_elements=[C.user_id,C.canonical_url]))
   row.window_start=window_start;row.window_end=window_end;row.page_token=page_token;row.window_complete=complete
   if complete:row.last_complete_scan_at=now
 def due_candidates(self,token,now,limit=3):
  with self.database.transaction() as s:
   self.fence(s,token,now)
   return [{'url':c.canonical_url,'attempts':c.attempts} for c in s.scalars(select(C).where(C.user_id==self.owner.id,C.status.in_(('pending','retry')),or_(C.next_retry_at.is_(None),C.next_retry_at<=now)).order_by(C.id).limit(limit))]
 def mark_candidate(self,token,url,*,status,error_code=None,next_retry_at=None,now):
  if status not in ('pending','retry','published','rejected'):raise ValueError('OFFICE_DISCOVERY_STATUS')
  with self.database.transaction() as s:
   self.fence(s,token,now);row=s.scalar(select(C).where(C.user_id==self.owner.id,C.canonical_url==url))
   if row is None:raise DiscoveryError('OFFICE_DISCOVERY_CANDIDATE')
   row.status=status;row.error_code=error_code;row.next_retry_at=next_retry_at;row.attempts+=1
 def report(self,token,status,error_code,now):
  with self.database.transaction() as s:
   self.fence(s,token,now);row=s.get(S,self.owner.id);row.last_status=status;row.last_error_code=error_code
 def counts(self):
  with self.database.transaction() as s:
   self.identity(s)
   return dict(s.execute(select(C.status,func.count()).where(C.user_id==self.owner.id).group_by(C.status)).all())
