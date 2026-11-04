"""Private operational state; never granted to the public sync role."""
from sqlalchemy import Column,Integer,String,Text,DateTime,Boolean,ForeignKey,UniqueConstraint,CheckConstraint
from app.models.multi_user import MultiUserBase
class OfficeDiscoveryState(MultiUserBase):
 __tablename__='office_discovery_state'
 user_id=Column(Integer,ForeignKey('users.id',ondelete='CASCADE'),primary_key=True,autoincrement=False)
 google_user_id=Column(String(255),nullable=False)
 window_start=Column(DateTime(timezone=True));window_end=Column(DateTime(timezone=True))
 window_complete=Column(Boolean,nullable=False,default=False)
 page_token=Column(Text)
 last_complete_scan_at=Column(DateTime(timezone=True))
 last_status=Column(String(32),nullable=False,default='not_started');last_error_code=Column(String(64))
 lease_owner=Column(String(64));lease_expires_at=Column(DateTime(timezone=True));next_allowed_at=Column(DateTime(timezone=True))
class OfficeDiscoveryCandidate(MultiUserBase):
 __tablename__='office_discovery_candidates'
 __table_args__=(UniqueConstraint('user_id','canonical_url'),CheckConstraint("status IN ('pending','retry','published','rejected')",name='status'),CheckConstraint('attempts >= 0',name='attempts'))
 id=Column(Integer,primary_key=True)
 user_id=Column(Integer,ForeignKey('users.id',ondelete='CASCADE'),nullable=False,index=True)
 canonical_url=Column(String(4096),nullable=False)
 discovered_at=Column(DateTime(timezone=True),nullable=False)
 status=Column(String(32),nullable=False,default='pending')
 attempts=Column(Integer,nullable=False,default=0)
 next_retry_at=Column(DateTime(timezone=True));error_code=Column(String(64))
