from datetime import timedelta
from dataclasses import replace
from uuid import uuid4
import pytest
from sqlalchemy import select
from tests.test_multi_user_database import database
from tests.test_push_devices import repository,subscription,NOW
from tests.test_push_intents import seeded,intent
from tests.test_push_dispatcher import Sender
from app.push.security import PushError
from app.push.models import PushDevice,PushReminder,PushOperation
from app.push.dispatcher import run_due

def test_private_ref_cannot_be_saved_even_in_cancel(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db)
    payload=intent(ref,enabled=False).model_copy(update={'source_ref':'PRIVATE_EMAIL_CONTENT'})
    with pytest.raises(PushError):r.apply_intent(d.id,payload,None,NOW)
    with db.transaction() as s:assert not s.scalars(select(PushReminder)).all()
def test_expired_device_credentials_are_removed(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW)
    run_due(db,Sender(r.cipher),NOW+timedelta(days=401))
    with db.transaction() as s:
        row=s.get(PushDevice,str(d.id));assert row is None or not row.subscription_cipher

def test_operation_receipts_are_bounded_by_retention(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db)
    r.apply_intent(d.id,intent(ref,enabled=False),None,NOW)
    run_due(db,Sender(r.cipher),NOW+timedelta(days=8))
    with db.transaction() as s:
        assert not s.scalars(select(PushOperation)).all()
        assert s.scalar(select(PushReminder)).status=='cancelled'

def test_invalid_curve_point_is_rejected(database):
    db,_=database;r=repository(db);sub=subscription();sub['keys']['p256dh']='B'+'A'*86
    with pytest.raises(PushError):r.register_device('a'*43,sub,NOW)

def test_repeated_registration_is_idempotent(database):
    db,_=database;r=repository(db);a=r.register_device('a'*43,subscription(),NOW);b=r.register_device('a'*43,subscription(),NOW)
    assert a.subscription_version==b.subscription_version

def test_independent_verifier_rejects_missing_marker_or_remote(monkeypatch):
    from app.push.verify import validate_test_target
    with pytest.raises(ValueError):validate_test_target('postgresql://test:secret@localhost/nkust_disposable','')
    with pytest.raises(ValueError):validate_test_target('postgresql://test:secret@production.invalid/neondb','yes')
    assert validate_test_target('postgresql+psycopg://test:secret@127.0.0.1/nkust_disposable_push','yes')
