from dataclasses import asdict
from datetime import timedelta
import json
from uuid import uuid4
import pytest
from sqlalchemy import select
from tests.test_multi_user_database import database
from tests.test_push_devices import repository,subscription,NOW
from app.models.public_announcements import PublicAnnouncement
from app.push.contracts import Deadline,ReminderIntent
from app.push.models import PushReminder
from app.push.sources import resolve_public_ref
from app.push.security import PushError

def seeded(db):
    ref=json.dumps(['nkust-office-mail','https://officemail.nkust.edu.tw/Mail/MailView/69929'],ensure_ascii=False)
    with db.transaction() as s:
        s.add(PublicAnnouncement(source_key='nkust-office-mail',canonical_url=json.loads(ref)[1],title='合成公開公告',excerpt='截止11月10日',content_hash='x'))
    with db.transaction() as s:return resolve_public_ref(s,ref)
def intent(ref,todo=None,revision=1,enabled=True):
    return ReminderIntent(todo_id=todo or uuid4(),source_ref=ref.source_ref,source_version=ref.version,client_revision=revision,operation_id=uuid4(),enabled=enabled,deadline=Deadline(kind='date',value='2026-11-10',confirmed=True,basis='official') if enabled else None)
def test_cancel_before_create_is_tombstone(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db);todo=uuid4()
    result=r.apply_intent(d.id,intent(ref,todo,2,False),None,NOW)
    assert result.status=='cancelled'
    with pytest.raises(PushError,match='PUSH_REVISION_CONFLICT'):r.apply_intent(d.id,intent(ref,todo,1),None,NOW)
def test_same_operation_is_idempotent(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db);i=intent(ref)
    a=r.apply_intent(d.id,i,None,NOW);b=r.apply_intent(d.id,i,None,NOW)
    assert a==b and a.status=='pending'
    with pytest.raises(PushError):r.apply_intent(d.id,i.model_copy(update={'enabled':False}),None,NOW)
def test_other_device_and_source_changes(database):
    db,_=database;r=repository(db);a=r.register_device('a'*43,subscription(),NOW);b=r.register_device('b'*43,subscription('https://web.push.apple.com/b'),NOW);ref=seeded(db);todo=uuid4()
    assert r.apply_intent(a.id,intent(ref,todo),None,NOW).server_revision==1
    assert r.apply_intent(b.id,intent(ref,todo),None,NOW).server_revision==1
    with db.transaction() as s:s.scalar(select(PublicAnnouncement)).excerpt='期限已變更'
    with pytest.raises(PushError,match='PUSH_SOURCE_CHANGED'):r.apply_intent(a.id,intent(ref,uuid4()),None,NOW)
def test_invalid_ref_never_fetches(database):
    db,_=database
    with db.transaction() as s:
        for ref in ['private',json.dumps(['demo','https://example.com']),json.dumps(['nkust-office-mail','https://officemail.nkust.edu.tw/Mail/MailView/999'])]:
            with pytest.raises(PushError):resolve_public_ref(s,ref)

def test_fetch_metadata_does_not_change_version(database):
    from app.models.source_history import PublicSourceVersion
    db,_=database;ref=seeded(db)
    def record(error):
        with db.transaction() as s:
            s.add(PublicSourceVersion(source_key='nkust-office-mail',canonical_url=json.loads(ref.source_ref)[1],snapshot_hash='a'*64,snapshot={'metadata':{'article':{'text':'本文','error':error,'checked_at':error}}},captured_at=NOW,baseline=False))
    record('one')
    with db.transaction() as s:a=resolve_public_ref(s,ref.source_ref)
    record('two')
    with db.transaction() as s:b=resolve_public_ref(s,ref.source_ref)
    assert a.version==b.version

def test_newer_cancel_survives_inflight_reconfiguration(database):
    db,_=database;r=repository(db);d=r.register_device('a'*43,subscription(),NOW);ref=seeded(db);todo=uuid4()
    r.apply_intent(d.id,intent(ref,todo,1),None,NOW)
    assert r.apply_intent(d.id,intent(ref,todo,2),1,NOW).server_revision==2
    # Completion was queued while rev2 was in flight and still knows server revision 1.
    assert r.apply_intent(d.id,intent(ref,todo,3,False),1,NOW).status=='cancelled'
    with pytest.raises(PushError):r.apply_intent(d.id,intent(ref,todo,2),2,NOW)
