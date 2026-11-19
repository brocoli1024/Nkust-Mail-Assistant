"""Owner-bound immutable baselines and append-only personal revisions."""
from sqlalchemy import Column,Integer,String,Text,DateTime,JSON,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from app.models.multi_user import MultiUserBase, utcnow

class PrivateActionSnapshot(MultiUserBase):
    __tablename__='private_action_snapshots'
    __table_args__=(ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        UniqueConstraint('user_id','id'), UniqueConstraint('user_id','email_id','source_index','source_fingerprint','baseline_hash'),
        CheckConstraint('source_index >= 0',name='source_index'),CheckConstraint('revision_count >= 0',name='revision_count'))
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    email_id=Column(Integer,nullable=False)
    source_index=Column(Integer,nullable=False)
    source_fingerprint=Column(String(64),nullable=False)
    source_hash=Column(String(64),nullable=False)
    baseline_hash=Column(String(64),nullable=False)
    parser_version=Column(String(64),nullable=False)
    source_text=Column(Text,nullable=False)
    source_metadata=Column(JSON,nullable=False)
    original_card=Column(JSON,nullable=False)
    revision_count=Column(Integer,nullable=False,default=0)
    created_at=Column(DateTime(timezone=True),nullable=False,default=utcnow)

class PrivateActionRevision(MultiUserBase):
    __tablename__='private_action_revisions'
    __table_args__=(ForeignKeyConstraint(['user_id','snapshot_id'],['private_action_snapshots.user_id','private_action_snapshots.id'],ondelete='CASCADE'),
        UniqueConstraint('snapshot_id','revision'),CheckConstraint('revision > 0',name='revision'),
        CheckConstraint("operation IN ('save','reset')",name='operation'))
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    snapshot_id=Column(Integer,nullable=False)
    revision=Column(Integer,nullable=False)
    operation=Column(String(16),nullable=False)
    overrides=Column(JSON,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,default=utcnow)
