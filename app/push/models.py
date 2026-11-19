from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint
from app.models.multi_user import MultiUserBase

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
