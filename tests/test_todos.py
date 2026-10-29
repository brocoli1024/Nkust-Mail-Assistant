from datetime import datetime,timezone
from dataclasses import replace
from sqlalchemy import select,func,delete
import pytest
from tests.test_action_card_corrections import database,seed,A,B,save,patch
from app.services.action_card_corrections import load_private_view,CorrectionConflict,CorrectionNotFound
from app.models.multi_user import User,Announcement
from app.services.todos import next_snooze,todo_view,add_private_todo,update_private_todo,list_private_todos,get_private_todo
from app.models.todos import PrivateTodo

NOW=datetime(2026,10,29,16,tzinfo=timezone.utc)
def add(db,aid,revision=0):
    v=load_private_view(db,A,aid)
    return add_private_todo(db,A,aid,expected_revision=revision,baseline_hash=v.base.baseline_hash,card_revision=v.revision,now=NOW)

def test_taipei_snooze_and_deadline_boundary(database):
    assert next_snooze(NOW).isoformat()=='2026-10-31T01:00:00+00:00'
    assert next_snooze(datetime(2026,12,31,16,tzinfo=timezone.utc)).isoformat()=='2027-01-02T01:00:00+00:00'
    db,_=database;aid=seed(db);add(db,aid)
    r=list_private_todos(db,A,now=NOW)[0]
    r['status']='snoozed';r['snoozed_until']='2026-10-29T16:00:00+00:00'
    assert todo_view(r,NOW)['effective_status']=='active'
    for date,group in [('2026-10-29','overdue'),('2026-10-30','today'),('2026-11-05','soon'),('2026-11-06','later')]:
        r['card']['fields']['deadline'].update(value=date,state='user_confirmed')
        assert todo_view(r,NOW)['deadline_group']==group
    r['card']['fields']['deadline']['state']='pending'
    assert todo_view(r,NOW)['deadline_group']=='none'

def test_explicit_add_complete_snooze_remove_readd(database):
    db,_=database;aid=seed(db);v=load_private_view(db,A,aid)
    assert list_private_todos(db,A)==[] and get_private_todo(db,A,v.base.source.source_ref) is None
    assert add(db,aid)==1
    row=list_private_todos(db,A)[0];tid=row['id']
    with pytest.raises(CorrectionConflict):add(db,aid)
    assert update_private_todo(db,A,tid,operation='complete',expected_revision=1,now=NOW)==2
    assert list_private_todos(db,A)[0]['effective_status']=='done'
    update_private_todo(db,A,tid,operation='reopen',expected_revision=2,now=NOW)
    update_private_todo(db,A,tid,operation='snooze',expected_revision=3,now=NOW)
    assert list_private_todos(db,A,now=NOW)[0]['effective_status']=='snoozed'
    assert list_private_todos(db,A,now=next_snooze(NOW))[0]['effective_status']=='active'
    update_private_todo(db,A,tid,operation='remove',expected_revision=4,now=NOW)
    assert list_private_todos(db,A)==[]
    assert add(db,aid,5)==6
    with pytest.raises(CorrectionConflict):update_private_todo(db,A,tid,operation='complete',expected_revision=1)
    with db.transaction() as s:assert s.scalar(select(func.count()).select_from(PrivateTodo))==1

def test_owner_identity_cascade_and_reparse(database):
    db,_=database;aid=seed(db);add(db,aid);row=list_private_todos(db,A)[0]
    for user in (B,replace(A,google_user_id='old-sub')):
        with pytest.raises(CorrectionNotFound):update_private_todo(db,user,row['id'],operation='remove',expected_revision=1)
    with db.transaction() as s:s.execute(delete(Announcement).where(Announcement.id==aid))
    assert list_private_todos(db,A)[0]['source_missing']
    with db.transaction() as s:s.execute(delete(User).where(User.id==1))
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(PrivateTodo))==0
        assert s.get(User,2)

def test_correction_version_cannot_be_silently_added(database):
    db,_=database;aid=seed(db);v=load_private_view(db,A,aid)
    save(db,aid,p=patch('新材料'))
    with pytest.raises(CorrectionConflict):add_private_todo(db,A,aid,expected_revision=0,baseline_hash=v.base.baseline_hash,card_revision=0)
    add(db,aid)
    assert list_private_todos(db,A)[0]['card']['fields']['materials']['value']=='新材料'

def test_two_todo_writers_have_one_winner(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.action_card_corrections import CorrectionUnavailable
    db,_=database;aid=seed(db);add(db,aid);tid=list_private_todos(db,A)[0]['id'];barrier=Barrier(2)
    def write(operation):
        barrier.wait(timeout=5)
        try:update_private_todo(db,A,tid,operation=operation,expected_revision=1);return 'saved'
        except (CorrectionConflict,CorrectionUnavailable):return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as p:assert sorted(p.map(write,['complete','remove']))==['rejected','saved']
