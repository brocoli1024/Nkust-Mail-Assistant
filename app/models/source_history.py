"""Separate append-only public and owner-scoped source archives."""
from sqlalchemy import Column,Integer,String,JSON,DateTime,Boolean,ForeignKeyConstraint,CheckConstraint
from app.models.multi_user import MultiUserBase

class PublicSourceVersion(MultiUserBase):
    __tablename__='public_source_versions'
    id=Column(Integer,primary_key=True)
    source_key=Column(String(80),nullable=False,index=True)
    canonical_url=Column(String(4096),nullable=False)
    snapshot_hash=Column(String(64),nullable=False)
    snapshot=Column(JSON,nullable=False)
    captured_at=Column(DateTime(timezone=True),nullable=False)
    baseline=Column(Boolean,nullable=False)

class PrivateSourceVersion(MultiUserBase):
    __tablename__='private_source_versions'
    __table_args__=(ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        CheckConstraint('source_index >= 0',name='source_index'))
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    email_id=Column(Integer,nullable=False)
    source_index=Column(Integer,nullable=False)
    source_fingerprint=Column(String(64),nullable=False)
    canonical_url=Column(String(4096))
    snapshot_hash=Column(String(64),nullable=False)
    snapshot=Column(JSON,nullable=False)
    captured_at=Column(DateTime(timezone=True),nullable=False)
    baseline=Column(Boolean,nullable=False)
