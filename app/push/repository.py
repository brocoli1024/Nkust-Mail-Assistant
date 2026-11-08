from datetime import timedelta,timezone
from uuid import UUID,uuid4
from sqlalchemy import select,update,func
from .models import PushDevice,PushLease,PushReminder
from .contracts import DeviceState
from .security import PushError,token_hash,validate_subscription,fingerprint
from .config import PushSettings

def utc(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

class PushRepository:
    def __init__(self,db,cipher,hash_key,settings=None):
        self.db,self.cipher,self.hash_key=db,cipher,hash_key
        self.settings=settings or PushSettings()

    @staticmethod
    def lock(session):
        # Seeded by migration: also force a write lock on SQLite.
        session.execute(update(PushLease).where(PushLease.name=='mutations').values(owner='serialized'))

    @staticmethod
    def state(row):return DeviceState(UUID(row.id),UUID(row.epoch),row.subscription_version,utc(row.expires_at))

    @staticmethod
    def device(session,token,now):
        row=session.scalar(select(PushDevice).where(PushDevice.token_hash==token_hash(token)))
        if not row or not row.enabled or utc(row.expires_at)<=utc(now):raise PushError('PUSH_DEVICE_UNAUTHORIZED')
        return row

    def authenticate(self,token,now):
        with self.db.transaction() as s:return self.state(self.device(s,token,now))

    def register_device(self,token,subscription,now):
        validate_subscription(subscription);digest=token_hash(token)
        endpoint_hash=fingerprint(self.hash_key,subscription['endpoint'])
        with self.db.transaction() as s:
            self.lock(s)
            row=s.scalar(select(PushDevice).where(PushDevice.token_hash==digest))
            collision=s.scalar(select(PushDevice).where(PushDevice.endpoint_hash==endpoint_hash))
            if collision is not None and (row is None or collision.id!=row.id):raise PushError('PUSH_SUBSCRIPTION_IN_USE')
            if row is None:
                count=s.scalar(select(func.count()).select_from(PushDevice).where(PushDevice.enabled.is_(True),PushDevice.expires_at>now))
                if count>=self.settings.max_devices:raise PushError('PUSH_CAPACITY_REACHED')
                row=PushDevice(id=str(uuid4()),epoch=str(uuid4()),token_hash=digest,subscription_version=0)
                s.add(row)
            # Every subscription registration invalidates in-flight old sends.
            row.subscription_version+=1
            row.subscription_cipher=self.cipher.encrypt(UUID(row.id),row.subscription_version,subscription)
            row.endpoint_hash=endpoint_hash;row.enabled=True
            row.expires_at=now+timedelta(days=400);row.updated_at=now
            s.flush()
            return self.state(row)
