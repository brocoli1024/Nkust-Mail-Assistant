from datetime import datetime, timezone
from dataclasses import replace
from sqlalchemy import select, func, delete, inspect
from sqlalchemy.exc import IntegrityError
from alembic import command
import pytest
from tests.test_multi_user_database import database, seed_email, announcement
from app.core.session import CurrentUser
from app.models.multi_user import Announcement, User
from app.models.action_cards import PrivateActionSnapshot as S, PrivateActionRevision as R
from app.schemas.action_cards import CorrectionPatch
from app.services.action_card_corrections import (load_private_view, save_private_correction, load_private_history, CorrectionNotFound, CorrectionConflict)

A=CurrentUser(1,'a@example.invalid',None,'google-a')
B=CurrentUser(2,'b@example.invalid',None,'google-b')


def seed(db):
    seed_email(db)
    with db.transaction() as s:
        row=announcement();s.add(row);s.flush();return row.id


def patch(value='在學證明'):
    return CorrectionPatch.model_validate({'fields':{'materials':{'mode':'value','value':value}}})


def save(db, aid, revision=0, operation='save', p=None):
    v=load_private_view(db,A,aid)
    return save_private_correction(db,A,aid,expected_revision=revision,baseline_hash=v.base.baseline_hash,operation=operation,patch=p or patch() if operation=='save' else None)


def test_save_reset_preserves_original_and_is_read_only(database):
    db,_=database;aid=seed(db)
    before=load_private_view(db,A,aid)
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(S))==0
    assert save(db,aid)==1
    assert save(db,aid,1,p=patch('成績單'))==2
    view=load_private_view(db,A,aid)
    assert view.effective.fields['materials'].value=='成績單'
    assert view.base.model_dump(mode='json')==before.base.model_dump(mode='json')
    assert view.patch.fields['materials'].value=='成績單'
    assert save(db,aid,2,operation='reset')==3
    view=load_private_view(db,A,aid)
    assert view.effective.fields['materials'].state=='pending'
    with db.transaction() as s:
        snapshot=s.scalar(select(S));sid=snapshot.id
        assert snapshot.original_card==before.base.model_dump(mode='json')
        assert s.scalar(select(func.count()).select_from(R))==3
    assert len(load_private_history(db,A,sid)['revisions'])==3
    with pytest.raises(CorrectionNotFound):load_private_history(db,B,sid)


def test_owner_identity_and_version_conflicts(database):
    db,_=database;aid=seed(db)
    v=load_private_view(db,A,aid)
    for user in (B,replace(A,google_user_id='old-sub')):
        with pytest.raises(CorrectionNotFound):load_private_view(db,user,aid)
        with pytest.raises(CorrectionNotFound):save_private_correction(db,user,aid,expected_revision=0,baseline_hash=v.base.baseline_hash,operation='save',patch=patch())
    save(db,aid)
    with pytest.raises(CorrectionConflict):save(db,aid)
    with pytest.raises(CorrectionConflict):save_private_correction(db,A,aid,expected_revision=1,baseline_hash='x'*64,operation='save',patch=patch())


def test_reparse_preserves_history_without_applying_to_reused_id(database):
    db,_=database;aid=seed(db);save(db,aid)
    with db.transaction() as s:
        s.execute(delete(Announcement).where(Announcement.id==aid))
        row=announcement();row.original_text='重新解析的不同內容';s.add(row);s.flush();newid=row.id
    v=load_private_view(db,A,newid)
    assert v.stale and v.revision==0 and v.patch is None
    assert v.effective.fields['materials'].value is None
    assert v.history
    h=load_private_history(db,A,v.history[0]['id'])
    assert h['snapshot']['source_text']=='合成本文'


def test_cascade_only_owner_and_schema(database):
    db,config=database;aid=seed(db);save(db,aid)
    with db.transaction() as s:s.execute(delete(User).where(User.id==1))
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(S))==0
        assert s.scalar(select(func.count()).select_from(R))==0
        assert s.get(User,2)
    assert {'private_action_snapshots','private_action_revisions'}<=set(inspect(db.engine).get_table_names())
    command.downgrade(config,'0006');command.upgrade(config,'head')
    with db.transaction() as s:assert s.get(User,2)


def test_snapshot_owner_foreign_key(database):
    db,_=database;aid=seed(db);save(db,aid)
    with db.transaction() as s:sid=s.scalar(select(S.id))
    with pytest.raises(IntegrityError):
        with db.transaction() as s:s.add(R(user_id=2,snapshot_id=sid,revision=2,operation='reset',overrides={}))


def test_two_writers_never_silently_overwrite(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.services.action_card_corrections import CorrectionUnavailable
    db,_=database;aid=seed(db);baseline=load_private_view(db,A,aid).base.baseline_hash
    ready=Barrier(2)
    def write(value):
        ready.wait(timeout=5)
        try:
            save_private_correction(db,A,aid,expected_revision=0,baseline_hash=baseline,operation='save',patch=patch(value))
            return 'saved'
        except (CorrectionConflict,CorrectionUnavailable):return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(write,['A','B']))
    assert sorted(outcomes)==['rejected','saved']
    with db.transaction() as s:
        assert s.scalar(select(func.count()).select_from(R))==1


def test_complete_patch_can_keep_unedited_materials(database):
    db,_=database;aid=seed(db);save(db,aid)
    view=load_private_view(db,A,aid)
    payload=view.patch.model_dump()
    payload['fields']['event_date']={'mode':'value','value':'2026-11-01','confirmed':True}
    save(db,aid,1,p=CorrectionPatch.model_validate(payload))
    assert load_private_view(db,A,aid).effective.fields['materials'].value=='在學證明'


def test_all_source_snapshots_are_discoverable(database):
    from app.services.action_card_corrections import load_private_snapshots
    db,_=database;aid=seed(db)
    for i in range(21):
        with db.transaction() as s:s.get(Announcement,aid).original_text=f'第{i}版原文'
        save(db,aid)
    first=load_private_snapshots(db,A,aid,page_number=1)
    second=load_private_snapshots(db,A,aid,page_number=2)
    assert len(first['snapshots'])==20 and first['has_more']
    assert len(second['snapshots'])==1 and not second['has_more']
    assert len({h['id'] for h in first['snapshots']+second['snapshots']})==21
    with pytest.raises(CorrectionNotFound):load_private_snapshots(db,B,aid)
