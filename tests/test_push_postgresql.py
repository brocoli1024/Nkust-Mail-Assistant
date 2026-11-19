import pytest
from tests.test_postgresql import database
from tests import test_push_devices as contracts

@pytest.mark.parametrize('contract',[contracts.test_device_isolation_and_redaction,contracts.test_endpoint_cannot_be_claimed_by_new_device,contracts.test_0011_preserves_0010_and_public_role_denied],ids=lambda f:f.__name__)
def test_push_on_postgresql(database,contract):contract(database)

from tests import test_push_intents as intents
@pytest.mark.parametrize('contract',[intents.test_cancel_before_create_is_tombstone,intents.test_same_operation_is_idempotent,intents.test_other_device_and_source_changes],ids=lambda f:f.__name__)
def test_push_intents_postgresql(database,contract):contract(database)

def test_concurrent_cancel_and_create(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from tests.test_push_devices import repository,subscription,NOW
    from app.push.security import PushError
    from app.push.models import PushReminder
    from sqlalchemy import select
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=intents.seeded(db);todo=uuid4();gate=Barrier(2)
    def write(enabled):
        gate.wait(timeout=5)
        try:r.apply_intent(d.id,intents.intent(ref,todo,1 if enabled else 2,enabled),None,NOW)
        except PushError as e:assert str(e)=='PUSH_REVISION_CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(write,[True,False]))
    with db.transaction() as s:
        row=s.scalar(select(PushReminder).where(PushReminder.todo_id==str(todo)))
        assert row.status=='cancelled' and row.client_revision==2

from tests import test_push_dispatcher as dispatch
@pytest.mark.parametrize('contract',[dispatch.test_accepted_not_delivered_and_no_duplicate,dispatch.test_cancel_fence_before_send,dispatch.test_changed_source_sends_review_only,dispatch.test_expired_sending_lease_is_unknown],ids=lambda f:f.__name__)
def test_dispatch_postgresql(database,contract):contract(database)

def test_two_dispatchers_do_not_duplicate(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from datetime import timedelta
    from tests.test_push_devices import NOW
    from app.push.dispatcher import run_due
    db,_=database;r,d,i,sender=dispatch.setup(db)
    entered=Event();release=Event();original=sender.send
    def send(*args):
        entered.set();assert release.wait(5);return original(*args)
    sender.send=send
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(run_due,db,sender,NOW+timedelta(days=1,hours=1))
        assert entered.wait(5)
        try:assert run_due(db,sender,NOW+timedelta(days=1,hours=1)).busy
        finally:release.set()
        assert first.result().accepted==1
    assert len(sender.sent)==1

@pytest.mark.parametrize('contract',[intents.test_newer_cancel_survives_inflight_reconfiguration],ids=lambda f:f.__name__)
def test_review_cancel_postgresql(database,contract):contract(database)

def test_cross_epoch_writes_are_rejected_inside_transaction(database):
    from uuid import uuid4
    from tests.test_push_devices import repository,subscription,NOW
    from app.push.security import PushError
    from app.push.models import PushDevice,PushReminder
    from sqlalchemy import select
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=intents.seeded(db)
    with pytest.raises(PushError,match='PUSH_DEVICE_CHANGED'):r.apply_intent(d.id,intents.intent(ref,enabled=False),None,NOW,uuid4())
    with pytest.raises(PushError,match='PUSH_DEVICE_CHANGED'):r.disable(d.id,NOW,uuid4())
    with db.transaction() as s:
        assert s.get(PushDevice,str(d.id)).enabled and not s.scalars(select(PushReminder)).all()
