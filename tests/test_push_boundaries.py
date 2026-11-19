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
        assert s.scalar(select(PushReminder)).status in ('cancelled','archived')

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

@pytest.mark.parametrize('query',['host=remote.invalid','hostaddr=8.8.8.8','dbname=other','service=other','options=-csearch_path%3Dpublic'])
def test_verifier_rejects_driver_query_overrides(query):
    from app.push.verify import validate_test_target
    with pytest.raises(ValueError):validate_test_target('postgresql+psycopg://test:synthetic@localhost/nkust_disposable?'+query,'yes')

def test_cancel_rejects_json_object_and_normalizes_identity(database):
    import json
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db)
    key,url=json.loads(ref.source_ref)
    bad=intent(ref,enabled=False).model_copy(update={'source_ref':json.dumps({key:'PRIVATE',url:'PRIVATE'})})
    with pytest.raises(PushError):r.apply_intent(d.id,bad,None,NOW)
    good=intent(ref,enabled=False).model_copy(update={'source_ref':json.dumps([key,url],separators=(',',':'))})
    r.apply_intent(d.id,good,None,NOW)
    with db.transaction() as session:assert session.scalar(select(PushReminder)).source_ref==ref.source_ref

@pytest.mark.parametrize('endpoint',['https://FCM.GOOGLEAPIS.COM/fcm/send/synthetic','https://fcm.googleapis.com:443/fcm/send/synthetic'])
def test_endpoint_alias_cannot_be_claimed_by_second_device(database,endpoint):
    db,_=database;r=repository(db);r.register_device('a'*43,subscription(),NOW)
    with pytest.raises(PushError):r.register_device('b'*43,subscription(endpoint),NOW)

def test_empty_userinfo_rejected(database):
    db,_=database
    with pytest.raises(PushError):repository(db).register_device('a'*43,subscription('https://@fcm.googleapis.com/fcm/send/synthetic'),NOW)

def test_push_bookkeeping_preserves_existing_correction_baseline(database):
    from app.services.action_cards import build_action_card,public_source
    from app.models.public_announcements import PublicAnnouncement
    db,_=database;seeded(db)
    with db.transaction() as session:
        row=session.scalar(select(PublicAnnouncement));before=build_action_card(public_source(row))
        source=public_source(row);source.metadata['push_source_version']='a'*64;after=build_action_card(source)
        assert after.source_hash==before.source_hash and after.baseline_hash==before.baseline_hash

def test_test_jobs_do_not_exhaust_durable_todo_capacity(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db)
    for n in range(200):r.queue_test(d.id,uuid4(),NOW+timedelta(hours=n//3))
    assert r.apply_intent(d.id,intent(ref),None,NOW).status=='pending'
    run_due(db,Sender(r.cipher),NOW+timedelta(days=10))
    run_due(db,Sender(r.cipher),NOW+timedelta(days=10,seconds=1))
    with db.transaction() as session:assert not session.scalars(select(PushReminder).where(PushReminder.source_ref=='__test__')).all()

def test_disable_clears_dates_but_preserves_cancellation_tombstone(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db)
    r.apply_intent(d.id,intent(ref),None,NOW);r.disable(d.id,NOW)
    with db.transaction() as session:
        row=session.scalar(select(PushReminder));assert row.status=='cancelled'
        assert row.deadline is None and row.remind_at is None and row.expires_at is None
