"""Durable bounded dispatch. Accepted is not delivered; ambiguous sends never retry."""
from dataclasses import dataclass
from datetime import timedelta
import time
from uuid import uuid4
from sqlalchemy import select,update,delete,func,or_
from .models import PushDevice,PushReminder,PushLease,PushOperation,PushRateBucket
from .repository import PushRepository,utc
from .sources import resolve_public_ref
from .security import PushError

@dataclass
class RunSummary:
    accepted:int=0
    unknown:int=0
    retry:int=0
    stopped:int=0
    pending:int=0
    busy:bool=False

def run_due(db,sender,now,max_jobs=100,budget_seconds=50):
    owner=str(uuid4());start=time.monotonic();result=RunSummary()
    with db.transaction() as s:
        PushRepository.lock(s);lease=s.get(PushLease,'dispatcher')
        if lease.expires_at and utc(lease.expires_at)>utc(now):result.busy=True;return result
        lease.owner=owner;lease.expires_at=now+timedelta(seconds=max(65,budget_seconds+15))
        s.execute(update(PushReminder).where(PushReminder.status=='sending',PushReminder.claim_expires_at<=now).values(status='unknown',claim=None,updated_at=now))
    try:
        for _ in range(min(100,max_jobs)):
            remaining=budget_seconds-(time.monotonic()-start)
            if remaining<=0:break
            current=now+timedelta(seconds=time.monotonic()-start)
            with db.transaction() as s:
                PushRepository.lock(s)
                lease=s.get(PushLease,'dispatcher')
                if lease.owner!=owner or utc(lease.expires_at)<=utc(current):break
                row=s.scalar(select(PushReminder).where(PushReminder.status.in_(('pending','retry')),PushReminder.remind_at<=current,
                    or_(PushReminder.next_attempt_at.is_(None),PushReminder.next_attempt_at<=current)).order_by(PushReminder.remind_at,PushReminder.id).limit(1))
                if row is None:break
                device=s.get(PushDevice,row.device_id)
                if not device or not device.enabled or utc(device.expires_at)<=utc(current) or not row.expires_at or utc(row.expires_at)<=utc(current) or row.subscription_version!=device.subscription_version:
                    row.status='stopped';row.updated_at=current;result.stopped+=1;continue
                if row.source_ref=='__test__':
                    payload={'id':row.id,'title':'測試通知','path':'/todos','expires_at':utc(row.expires_at).isoformat(),'kind':'test'}
                else:
                    try:ref=resolve_public_ref(s,row.source_ref)
                    except PushError:
                        row.status='stopped';row.updated_at=current;result.stopped+=1;continue
                    changed=ref.version!=row.source_version
                    payload={'id':row.id,'title':'公告已更新，請核對日期' if changed else ref.title[:120],
                        'path':ref.detail_path,'expires_at':utc(row.expires_at).isoformat(),'kind':'review' if changed else 'deadline'}
                try:subscription=sender.cipher.decrypt(device.id,device.subscription_version,device.subscription_cipher)
                except PushError:
                    row.status='stopped';result.stopped+=1;continue
                row.status='sending';row.claim=owner;row.claim_expires_at=current+timedelta(seconds=15);row.updated_at=current
                item=(row.id,row.server_revision,device.id,device.subscription_version)
                expiry=utc(row.expires_at)
            # Final fence immediately before network; cancellation after provider submission cannot retract it.
            with db.transaction() as s:
                row=s.get(PushReminder,item[0]);device=s.get(PushDevice,item[2])
                if (not row or row.status!='sending' or row.claim!=owner or row.server_revision!=item[1]
                    or not device.enabled or device.subscription_version!=item[3]):continue
            current=now+timedelta(seconds=time.monotonic()-start)
            remaining=budget_seconds-(time.monotonic()-start)
            if remaining<=0 or expiry<=current:
                # Nothing submitted; safe to release rather than mark uncertain.
                with db.transaction() as s:
                    s.execute(update(PushReminder).where(PushReminder.id==item[0],PushReminder.claim==owner).values(status='pending',claim=None))
                break
            sender.timeout=min(5,remaining)
            outcome=sender.send(subscription,payload,max(0,int((expiry-current).total_seconds())),current)
            with db.transaction() as s:
                PushRepository.lock(s);row=s.get(PushReminder,item[0]);device=s.get(PushDevice,item[2])
                if row.status!='sending' or row.claim!=owner or row.server_revision!=item[1]:continue
                row.claim=None;row.claim_expires_at=None;row.updated_at=current
                if outcome.status=='accepted':row.status='accepted';result.accepted+=1
                elif outcome.status=='unknown':row.status='unknown';result.unknown+=1
                elif outcome.status=='invalid':
                    row.status='stopped';result.stopped+=1
                    if device.subscription_version==item[3]:
                        device.enabled=False;device.subscription_cipher=None;device.endpoint_hash=None;device.subscription_version+=1
                        s.execute(update(PushReminder).where(PushReminder.device_id==device.id,PushReminder.status.in_(('pending','retry'))).values(status='stopped',updated_at=current))
                elif outcome.status=='retryable' and row.attempts<3:
                    delay=(60,300,900)[row.attempts];row.attempts+=1
                    row.next_attempt_at=current+timedelta(seconds=delay)
                    row.status='retry' if utc(row.next_attempt_at)<expiry else 'stopped';result.retry+=row.status=='retry'
                else:row.status='failed';result.stopped+=1
        with db.transaction() as s:
            result.pending=s.scalar(select(func.count()).select_from(PushReminder).where(PushReminder.status.in_(('pending','retry')),PushReminder.remind_at<=now))
            # Minimal cancellation tombstones persist for device lifetime; operation receipts expire after seven days.
            tests=s.scalars(select(PushReminder.id).where(PushReminder.source_ref=='__test__',or_(PushReminder.expires_at<now-timedelta(days=7),PushReminder.updated_at<now-timedelta(days=7))).limit(100)).all()
            if tests:s.execute(delete(PushReminder).where(PushReminder.id.in_(tests)))
            ids=s.scalars(select(PushReminder.id).where(PushReminder.status.in_(('accepted','failed','unknown','stopped','cancelled')),PushReminder.updated_at<now-timedelta(days=7)).limit(100)).all()
            # Retain minimal version tombstone, erase payload/date rather than deleting the identity.
            if ids:s.execute(update(PushReminder).where(PushReminder.id.in_(ids)).values(deadline=None,remind_at=None,expires_at=None,status='archived'))
            receipts=s.execute(select(PushOperation.device_id,PushOperation.operation_id).where(PushOperation.created_at<now-timedelta(days=7)).limit(100)).all()
            for device_id,operation_id in receipts:s.execute(delete(PushOperation).where(PushOperation.device_id==device_id,PushOperation.operation_id==operation_id))
            devices=s.scalars(select(PushDevice.id).where(PushDevice.expires_at<now).limit(100)).all()
            if devices:s.execute(delete(PushDevice).where(PushDevice.id.in_(devices)))
            keys=s.scalars(select(PushRateBucket.key).where(PushRateBucket.expires_at<now).limit(100)).all()
            if keys:s.execute(delete(PushRateBucket).where(PushRateBucket.key.in_(keys)))
    finally:
        with db.transaction() as s:
            s.execute(update(PushLease).where(PushLease.name=='dispatcher',PushLease.owner==owner).values(owner=None,expires_at=None))
    return result
