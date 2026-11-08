"""Frozen private push schema 0011; no existing source/account rows modified."""
from alembic import op
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy import MetaData,Table
from sqlalchemy.orm import declarative_base
MultiUserBase=declarative_base(metadata=MetaData(naming_convention={
    "ix":"ix_%(table_name)s_%(column_0_name)s","uq":"uq_%(table_name)s_%(column_0_N_name)s",
    "ck":"ck_%(table_name)s_%(constraint_name)s","fk":"fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s","pk":"pk_%(table_name)s"}))
Table("public_announcements",MultiUserBase.metadata,Column("id",Integer,primary_key=True))

class PushDevice(MultiUserBase):
    __tablename__='push_devices'
    id=Column(String(36),primary_key=True)
    epoch=Column(String(36),nullable=False)
    token_hash=Column(String(64),nullable=False,unique=True)
    endpoint_hash=Column(String(64),unique=True)
    subscription_cipher=Column(Text)
    subscription_version=Column(Integer,nullable=False)
    enabled=Column(Boolean,nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    updated_at=Column(DateTime(timezone=True),nullable=False)

class PushReminder(MultiUserBase):
    __tablename__='push_reminders'
    __table_args__=(UniqueConstraint('device_id','todo_id'),CheckConstraint('client_revision >= 1',name='client_revision'))
    id=Column(String(36),primary_key=True)
    device_id=Column(String(36),ForeignKey('push_devices.id',ondelete='CASCADE'),nullable=False,index=True)
    todo_id=Column(String(36),nullable=False)
    public_id=Column(Integer,ForeignKey('public_announcements.id',ondelete='CASCADE'))
    source_ref=Column(Text,nullable=False)
    source_version=Column(String(64),nullable=False)
    client_revision=Column(Integer,nullable=False)
    server_revision=Column(Integer,nullable=False)
    subscription_version=Column(Integer,nullable=False)
    deadline=Column(JSON)
    remind_at=Column(DateTime(timezone=True),index=True)
    expires_at=Column(DateTime(timezone=True))
    status=Column(String(32),nullable=False)
    attempts=Column(Integer,nullable=False,default=0)
    next_attempt_at=Column(DateTime(timezone=True))
    claim=Column(String(36))
    claim_expires_at=Column(DateTime(timezone=True))
    updated_at=Column(DateTime(timezone=True),nullable=False)

class PushOperation(MultiUserBase):
    __tablename__='push_operations'
    device_id=Column(String(36),ForeignKey('push_devices.id',ondelete='CASCADE'),primary_key=True)
    operation_id=Column(String(36),primary_key=True)
    request_hash=Column(String(64),nullable=False)
    result=Column(JSON,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False)

class PushLease(MultiUserBase):
    __tablename__='push_leases'
    name=Column(String(64),primary_key=True)
    owner=Column(String(36))
    expires_at=Column(DateTime(timezone=True))

class PushRateBucket(MultiUserBase):
    __tablename__='push_rate_buckets'
    key=Column(String(128),primary_key=True)
    count=Column(Integer,nullable=False)
    expires_at=Column(DateTime(timezone=True),nullable=False)

revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None
TABLES=(PushDevice.__table__,PushReminder.__table__,PushOperation.__table__,PushLease.__table__,PushRateBucket.__table__)
def upgrade():
    for table in TABLES:table.create(op.get_bind())
    op.bulk_insert(PushLease.__table__,[{'name':'mutations'},{'name':'dispatcher'}])
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':
        # Keep public sync and default PUBLIC grants out of sensitive tables.
        for table in TABLES:
            op.execute('REVOKE ALL ON TABLE '+table.name+' FROM PUBLIC')
        for table in TABLES:
            op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='nkust_public_sync') THEN REVOKE ALL ON TABLE "+table.name+" FROM nkust_public_sync; END IF; END $$")
def downgrade():
    for table in reversed(TABLES):table.drop(op.get_bind())
