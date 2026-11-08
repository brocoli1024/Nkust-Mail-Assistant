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
