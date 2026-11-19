"""Explicit personal todo records; source snapshots survive announcement reparse."""
from sqlalchemy import Column,Integer,String,JSON,DateTime,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from app.models.multi_user import MultiUserBase,Timestamps

class PrivateTodo(Timestamps,MultiUserBase):
    __tablename__='private_todos'
    __table_args__=(ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        UniqueConstraint('user_id','source_ref'),CheckConstraint('revision > 0',name='revision'),
        CheckConstraint("status IN ('active','done','snoozed','removed')",name='status'),
        CheckConstraint("(status = 'snoozed' AND snoozed_until IS NOT NULL) OR (status != 'snoozed' AND snoozed_until IS NULL)",name='snooze'))
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    email_id=Column(Integer,nullable=False)
    source_ref=Column(String(512),nullable=False)
    source_index=Column(Integer,nullable=False)
    source_fingerprint=Column(String(64),nullable=False)
    card=Column(JSON,nullable=False)
    status=Column(String(16),nullable=False)
    snoozed_until=Column(DateTime(timezone=True))
    revision=Column(Integer,nullable=False)
