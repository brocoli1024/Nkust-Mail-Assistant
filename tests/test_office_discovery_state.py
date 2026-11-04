from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import delete,select
from tests.test_multi_user_database import database
from app.core.session import CurrentUser
from app.core.office_discovery import DiscoverySettings,DiscoveryError
from app.database.office_discovery import DiscoveryRepository
from app.models.multi_user import User
from app.models.office_discovery import OfficeDiscoveryState,OfficeDiscoveryCandidate
NOW=datetime(2026,11,5,tzinfo=timezone.utc)
OWNER=CurrentUser(1,'a@example.invalid','A','google-a')
URL='https://officemail.nkust.edu.tw/Mail/MailView/70001'

def test_configuration_is_disabled_by_default_and_secret_is_redacted():
 assert not DiscoverySettings().enabled
 with pytest.raises(ValueError):DiscoverySettings(True,'google-a','short')
 assert 'PRIVATE-SECRET' not in repr(DiscoverySettings(True,'google-a','PRIVATE-SECRET'+'x'*32))

def test_candidates_and_cursor_commit_together_with_cooldown(database):
 db,_=database;r=DiscoveryRepository(db,OWNER);token=r.acquire(NOW)
 r.commit_page(token,window_start=NOW-timedelta(days=14),window_end=NOW,page_token='private-page',urls=[URL,URL],complete=False,now=NOW)
 assert len(r.due_candidates(token,NOW))==1 and r.state()['page_token']=='private-page'
 with pytest.raises(DiscoveryError):r.acquire(NOW)
 r.release(token)
 with pytest.raises(DiscoveryError):r.acquire(NOW+timedelta(seconds=299))
 token=r.acquire(NOW+timedelta(seconds=300))
 r.commit_page(token,window_start=NOW-timedelta(days=14),window_end=NOW,page_token=None,urls=[],complete=True,now=NOW+timedelta(seconds=300))
 assert r.state()['window_complete'] and r.state()['last_complete_scan_at'] is not None

def test_expired_worker_identity_reuse_and_cascade(database):
 db,_=database;r=DiscoveryRepository(db,OWNER);token=r.acquire(NOW)
 with pytest.raises(DiscoveryError):
  with db.transaction() as s:r.fence(s,token,NOW+timedelta(seconds=121))
 r.release(token);token=r.acquire(NOW+timedelta(seconds=300))
 r.commit_page(token,window_start=NOW,window_end=NOW,page_token=None,urls=[URL],complete=True,now=NOW+timedelta(seconds=300))
 with db.transaction() as s:s.execute(delete(User).where(User.id==1))
 with db.transaction() as s:
  assert s.get(OfficeDiscoveryState,1) is None
  assert not s.scalars(select(OfficeDiscoveryCandidate)).all()
  s.add(User(id=1,google_user_id='new-google',email='new@example.invalid'))
 with pytest.raises(DiscoveryError):r.state()

def test_foreign_subject_is_rejected(database):
 db,_=database
 with pytest.raises(DiscoveryError):DiscoveryRepository(db,CurrentUser(1,'x','X','google-b')).acquire(NOW)
