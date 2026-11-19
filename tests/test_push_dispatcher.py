from datetime import timedelta
from sqlalchemy import select
from tests.test_multi_user_database import database
from tests.test_push_devices import repository,subscription,NOW
from tests.test_push_intents import seeded,intent
from app.push.models import PushReminder,PushDevice
from app.models.public_announcements import PublicAnnouncement
from app.push.dispatcher import run_due
from app.push.transport import SendOutcome

class Sender:
    def __init__(self,cipher,outcome='accepted'):self.cipher=cipher;self.outcome=outcome;self.sent=[]
    def send(self,subscription,payload,ttl,now):
        self.sent.append((payload,ttl));return SendOutcome(self.outcome,'PUSH_TEST')

def setup(db,outcome='accepted'):
    r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db);i=intent(ref)
    r.apply_intent(d.id,i,None,NOW)
    return r,d,i,Sender(r.cipher,outcome)

def test_accepted_not_delivered_and_no_duplicate(database):
    db,_=database;r,d,i,sender=setup(db);due=NOW+timedelta(days=1,hours=1)
    result=run_due(db,sender,due)
    assert result.accepted==1 and len(sender.sent)==1 and sender.sent[0][1]>0
    assert run_due(db,sender,due).accepted==0

def test_cancel_fence_before_send(database):
    db,_=database;r,d,i,sender=setup(db)
    r.apply_intent(d.id,i.model_copy(update={'enabled':False,'operation_id':__import__('uuid').uuid4(),'client_revision':2}),1,NOW)
    assert run_due(db,sender,NOW+timedelta(days=1,hours=1)).accepted==0 and not sender.sent

def test_changed_source_sends_review_only(database):
    db,_=database;r,d,i,sender=setup(db)
    with db.transaction() as s:s.scalar(select(PublicAnnouncement)).excerpt='期限更新'
    run_due(db,sender,NOW+timedelta(days=1,hours=1))
    assert sender.sent[0][0]['kind']=='review' and '截止' not in sender.sent[0][0]['title']

def test_410_erases_endpoint(database):
    db,_=database;r,d,i,sender=setup(db,'invalid')
    run_due(db,sender,NOW+timedelta(days=1,hours=1))
    with db.transaction() as s:
        row=s.get(PushDevice,str(d.id));assert not row.enabled and row.subscription_cipher is None

def test_expired_sending_lease_is_unknown(database):
    db,_=database;r,d,i,sender=setup(db)
    with db.transaction() as s:
        row=s.scalar(select(PushReminder));row.status='sending';row.claim='old';row.claim_expires_at=NOW
    run_due(db,sender,NOW+timedelta(days=1,hours=1))
    with db.transaction() as s:assert s.scalar(select(PushReminder)).status=='unknown'
    assert not sender.sent

def test_unknown_and_expired_jobs_never_resend(database):
    db,_=database;r,d,i,sender=setup(db,'unknown');due=NOW+timedelta(days=1,hours=1)
    assert run_due(db,sender,due).unknown==1
    run_due(db,sender,due);assert len(sender.sent)==1

def test_budget_zero_preserves_backlog(database):
    db,_=database;r,d,i,sender=setup(db)
    run_due(db,sender,NOW+timedelta(days=1,hours=1),budget_seconds=0)
    assert not sender.sent

def test_retry_is_bounded(database):
    db,_=database;r,d,i,sender=setup(db,'retryable');due=NOW+timedelta(days=1,hours=1)
    for minutes in [0,1,6,21,60]:run_due(db,sender,due+timedelta(minutes=minutes))
    assert len(sender.sent)==4
    with db.transaction() as s:assert s.scalar(select(PushReminder)).status=='failed'

def test_subscription_rotation_preserves_pending_reminder(database):
    db,_=database;r,d,i,sender=setup(db)
    r.register_device('a'*43,subscription(),NOW)
    assert run_due(db,sender,NOW+timedelta(days=1,hours=1)).accepted==1
