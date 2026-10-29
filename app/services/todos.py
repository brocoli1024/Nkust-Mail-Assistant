"""Todo projections and owner-checked atomic changes. No network or AI calls."""
from datetime import datetime,time,timedelta,timezone,date
from sqlalchemy import select,update
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from app.models.todos import PrivateTodo as T
from app.models.multi_user import Announcement
from app.models.action_cards import PrivateActionRevision as R
from app.schemas.action_cards import ActionCard,CorrectionPatch
from app.services.action_cards import TAIPEI,apply_patch
from app.services.action_card_corrections import (_identity,_source,_snapshots,CorrectionNotFound,CorrectionConflict,CorrectionUnavailable)

def aware(value):
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def clock(now=None):return aware(now or datetime.now(timezone.utc))

def next_snooze(now):
    tomorrow=clock(now).astimezone(TAIPEI).date()+timedelta(days=1)
    return datetime.combine(tomorrow,time(9),TAIPEI).astimezone(timezone.utc)

def todo_view(record,now):
    out=dict(record);now=clock(now)
    if out['status'] not in ('active','done','snoozed','removed'):raise ValueError('Invalid todo state')
    card=ActionCard.model_validate(out['card']);deadline=card.fields['deadline']
    out['effective_status']='active' if out['status']=='snoozed' and aware(out['snoozed_until'])<=now else out['status']
    d=date.fromisoformat(deadline.value) if deadline.value and deadline.state in ('supported','user_confirmed') else None
    today=now.astimezone(TAIPEI).date()
    out.update(deadline=d.isoformat() if d else None,deadline_group=('none' if d is None else 'overdue' if d<today else 'today' if d==today else 'soon' if d<=today+timedelta(days=6) else 'later'),
        snooze_label=next_snooze(now).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M'),
        snoozed_label=aware(out['snoozed_until']).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M') if out.get('snoozed_until') else None,
        snooze_after_deadline=bool(d and d<next_snooze(now).astimezone(TAIPEI).date()))
    return out

def data(row):
    return {k:getattr(row,k) for k in ('id','source_ref','card','status','snoozed_until','revision','created_at','updated_at')}

def get_private_todo(database,user,source_ref):
    try:
        with database.transaction() as s:
            _identity(s,user)
            row=s.scalar(select(T).where(T.user_id==user.id,T.source_ref==source_ref))
            return data(row) if row else None
    except SQLAlchemyError:raise CorrectionUnavailable() from None

def list_private_todos(database,user,now=None):
    try:
        with database.transaction() as s:
            _identity(s,user);items=[]
            for row in s.scalars(select(T).where(T.user_id==user.id,T.status!='removed').order_by(T.id)):
                item=todo_view(data(row),clock(now))
                current=s.scalar(select(Announcement).where(Announcement.user_id==user.id,Announcement.email_id==row.email_id,
                    Announcement.source_index==row.source_index,Announcement.source_fingerprint==row.source_fingerprint))
                item['source_missing']=current is None
                item['local_url']=f'/announcements/{current.id}' if current else None
                item['source_changed']=bool(current and current.original_text!=item['card']['source']['segments'][0]['text'])
                items.append(item)
            return sorted(items,key=lambda r:(r['deadline'] is None,r['deadline'] or '',r['id']))
    except (SQLAlchemyError,ValidationError,ValueError,KeyError,TypeError):raise CorrectionUnavailable() from None

def add_private_todo(database,user,aid,*,expected_revision,baseline_hash,card_revision,now=None):
    if type(expected_revision) is not int or expected_revision<0 or type(card_revision) is not int or card_revision<0:raise ValueError('Invalid revision')
    try:
        with database.transaction() as s:
            _identity(s,user,lock=True);row,email,base=_source(s,user,aid)
            snap=_snapshots(s,user,row,base);revision=snap.revision_count if snap else 0
            if base.baseline_hash!=baseline_hash or revision!=card_revision:raise CorrectionConflict()
            effective=base
            if revision:
                saved=s.scalar(select(R).where(R.user_id==user.id,R.snapshot_id==snap.id,R.revision==revision))
                if not saved:raise CorrectionUnavailable()
                if saved.operation=='save':effective=apply_patch(base,CorrectionPatch.model_validate(saved.overrides))
            old=s.scalar(select(T).where(T.user_id==user.id,T.source_ref==base.source.source_ref))
            if (old.revision if old else 0)!=expected_revision:raise CorrectionConflict()
            if old and old.status!='removed':raise CorrectionConflict()
            values=dict(card=effective.model_dump(mode='json'),status='active',snoozed_until=None,updated_at=clock(now),revision=expected_revision+1)
            if old:
                changed=s.execute(update(T).where(T.id==old.id,T.user_id==user.id,T.revision==expected_revision).values(**values))
                if changed.rowcount!=1:raise CorrectionConflict()
            else:s.add(T(user_id=user.id,email_id=email.id,source_ref=base.source.source_ref,source_index=row.source_index,
                source_fingerprint=row.source_fingerprint,created_at=clock(now),**values))
            return expected_revision+1
    except (SQLAlchemyError,ValidationError):raise CorrectionUnavailable() from None

def update_private_todo(database,user,tid,*,operation,expected_revision,now=None):
    if operation not in ('complete','reopen','snooze','remove') or type(expected_revision) is not int or expected_revision<1:raise ValueError('Invalid operation')
    try:
        with database.transaction() as s:
            _identity(s,user,lock=True)
            row=s.scalar(select(T).where(T.id==tid,T.user_id==user.id))
            if not row:raise CorrectionNotFound()
            if row.revision!=expected_revision or row.status=='removed':raise CorrectionConflict()
            status={'complete':'done','reopen':'active','snooze':'snoozed','remove':'removed'}[operation]
            changed=s.execute(update(T).where(T.id==tid,T.user_id==user.id,T.revision==expected_revision).values(
                status=status,snoozed_until=next_snooze(clock(now)) if status=='snoozed' else None,revision=expected_revision+1,updated_at=clock(now)))
            if changed.rowcount!=1:raise CorrectionConflict()
            return expected_revision+1
    except SQLAlchemyError:raise CorrectionUnavailable() from None
