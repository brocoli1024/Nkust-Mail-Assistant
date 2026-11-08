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
            if row.enabled and row.subscription_cipher and utc(row.expires_at)>utc(now):
                if self.cipher.decrypt(row.id,row.subscription_version,row.subscription_cipher)==subscription:
                    row.expires_at=now+timedelta(days=400);row.updated_at=now
                    return self.state(row)
            # A genuinely changed subscription invalidates in-flight old sends.
            row.subscription_version+=1
            row.subscription_cipher=self.cipher.encrypt(UUID(row.id),row.subscription_version,subscription)
            row.endpoint_hash=endpoint_hash;row.enabled=True
            row.expires_at=now+timedelta(days=400);row.updated_at=now
            s.flush()
            # Rotate delivery credentials without losing confirmed pending dates.
            s.execute(update(PushReminder).where(PushReminder.device_id==row.id,PushReminder.status.in_(('pending','retry'))).values(subscription_version=row.subscription_version))
            s.execute(update(PushReminder).where(PushReminder.device_id==row.id,PushReminder.status=='sending').values(status='unknown',claim=None,updated_at=now))
            return self.state(row)

    def apply_intent(self,device_id,intent,expected_revision,now):
        from dataclasses import asdict
        import hashlib,json
        from .contracts import MutationResult
        from .models import PushOperation
        from .dates import validate_window
        from .sources import resolve_public_ref,parse_public_ref
        parse_public_ref(intent.source_ref)
        encoded=json.dumps({'intent':intent.model_dump(mode='json'),'expected_revision':expected_revision},sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        with self.db.transaction() as s:
            self.lock(s)
            d=s.get(PushDevice,str(device_id))
            if not d or not d.enabled or utc(d.expires_at)<=utc(now):raise PushError('PUSH_DEVICE_UNAUTHORIZED')
            op=s.get(PushOperation,(str(device_id),str(intent.operation_id)))
            if op:
                if op.request_hash!=digest:raise PushError('PUSH_OPERATION_CONFLICT')
                return MutationResult(**op.result)
            row=s.scalar(select(PushReminder).where(PushReminder.device_id==str(device_id),PushReminder.todo_id==str(intent.todo_id)))
            if row and (intent.client_revision<=row.client_revision or (expected_revision is not None and expected_revision!=row.server_revision)):
                raise PushError('PUSH_REVISION_CONFLICT')
            if not row and expected_revision not in (None,0):raise PushError('PUSH_REVISION_CONFLICT')
            # Cancellation deliberately needs no source lookup: deleted sources must remain cancellable.
            ref=resolve_public_ref(s,intent.source_ref) if intent.enabled else None
            window=None
            if intent.enabled:
                if ref.version!=intent.source_version:raise PushError('PUSH_SOURCE_CHANGED')
                window=validate_window(intent.deadline,intent.remind_at,now)
                active=select(PushReminder.id).where(PushReminder.status.in_(('pending','sending','retry')),PushReminder.expires_at>now)
                own=s.scalar(select(func.count()).select_from(active.where(PushReminder.device_id==str(device_id)).subquery()))
                total=s.scalar(select(func.count()).select_from(active.subquery()))
                already_active=row and row.status in ('pending','sending','retry') and row.expires_at and utc(row.expires_at)>utc(now)
                if not already_active and (own>=self.settings.per_device or total>=self.settings.max_active):raise PushError('PUSH_CAPACITY_REACHED')
            if row is None:
                own_records=s.scalar(select(func.count()).select_from(PushReminder).where(PushReminder.device_id==str(device_id)))
                all_records=s.scalar(select(func.count()).select_from(PushReminder))
                if own_records>=200 or all_records>=50000:raise PushError('PUSH_CAPACITY_REACHED')
                row=PushReminder(id=str(uuid4()),device_id=str(device_id),todo_id=str(intent.todo_id),server_revision=0)
                s.add(row)
            row.source_ref=ref.source_ref if ref else intent.source_ref
            row.source_version=ref.version if ref else intent.source_version
            row.public_id=ref.id if ref else row.public_id
            row.client_revision=intent.client_revision;row.server_revision+=1
            row.subscription_version=d.subscription_version
            row.deadline=intent.deadline.model_dump(mode='json') if intent.enabled else None
            row.remind_at=window.remind_at if window else None;row.expires_at=window.expires_at if window else None
            row.status='pending' if intent.enabled else 'cancelled';row.attempts=0
            row.next_attempt_at=None;row.claim=None;row.claim_expires_at=None;row.updated_at=now
            result=MutationResult(row.server_revision,row.client_revision,row.status)
            s.add(PushOperation(device_id=str(device_id),operation_id=str(intent.operation_id),request_hash=digest,result=asdict(result),created_at=now))
            s.flush()
            return result

    def disable(self,device_id,now):
        with self.db.transaction() as s:
            self.lock(s);d=s.get(PushDevice,str(device_id))
            if not d:raise PushError('PUSH_DEVICE_UNAUTHORIZED')
            d.enabled=False;d.subscription_cipher=None;d.endpoint_hash=None;d.subscription_version+=1;d.updated_at=now
            s.execute(update(PushReminder).where(PushReminder.device_id==d.id).values(status='cancelled',claim=None,updated_at=now))

    def consume_rate(self,key,limit,now):
        from .models import PushRateBucket
        with self.db.transaction() as s:
            self.lock(s);row=s.get(PushRateBucket,key)
            if not row:
                row=PushRateBucket(key=key,count=0,expires_at=now+timedelta(hours=48));s.add(row)
            if row.count>=limit:raise PushError('PUSH_RATE_LIMITED')
            row.count+=1

    def queue_test(self,device_id,operation_id,now):
        from .models import PushOperation,PushRateBucket
        from .security import fingerprint
        with self.db.transaction() as s:
            self.lock(s);d=s.get(PushDevice,str(device_id))
            if not d or not d.enabled:raise PushError('PUSH_DEVICE_UNAUTHORIZED')
            op=s.get(PushOperation,(str(device_id),str(operation_id)))
            if op:
                if op.request_hash!='test':raise PushError('PUSH_OPERATION_CONFLICT')
                return
            for scope,limit in [('test-device:'+str(device_id),3),('test-global',300)]:
                key=scope+':'+now.strftime('%Y%m%d%H')
                bucket=s.get(PushRateBucket,key)
                if not bucket:
                    bucket=PushRateBucket(key=key,count=0,expires_at=now+timedelta(hours=48));s.add(bucket)
                if bucket.count>=limit:raise PushError('PUSH_RATE_LIMITED')
                bucket.count+=1
            s.add(PushReminder(id=str(uuid4()),device_id=d.id,todo_id=str(operation_id),source_ref='__test__',source_version='',client_revision=1,server_revision=1,subscription_version=d.subscription_version,status='pending',remind_at=now,expires_at=now+timedelta(minutes=5),updated_at=now))
            s.add(PushOperation(device_id=d.id,operation_id=str(operation_id),request_hash='test',result={'status':'queued'},created_at=now))
