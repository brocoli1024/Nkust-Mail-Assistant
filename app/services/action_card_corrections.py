"""Personal corrections: authenticated source reads and atomic append-only writes."""
from dataclasses import dataclass
from pydantic import ValidationError
from sqlalchemy import select,and_,update
from sqlalchemy.exc import SQLAlchemyError
from app.core.session import CurrentUser
from app.models.multi_user import User,Email,Announcement,Analysis
from app.models.action_cards import PrivateActionSnapshot as S,PrivateActionRevision as R
from app.schemas.action_cards import ActionCard,CorrectionPatch
from app.services.action_cards import private_source,build_action_card,apply_patch,TAIPEI
from datetime import timezone

class CorrectionNotFound(Exception):pass
class CorrectionConflict(Exception):pass
class CorrectionUnavailable(Exception):pass

@dataclass
class PrivateCardView:
    item:dict
    base:ActionCard
    effective:ActionCard
    patch:CorrectionPatch|None
    revision:int
    history:list[dict]
    stale:bool
    saved_at:str|None=None


def _identity(session,user,lock=False):
    if not isinstance(user,CurrentUser):raise CorrectionNotFound()
    q=select(User.google_user_id).where(User.id==user.id)
    if lock:q=q.with_for_update()
    if session.scalar(q)!=user.google_user_id:raise CorrectionNotFound()


def _source(session,user,aid):
    found=session.execute(select(Announcement,Email).join(Email,and_(Announcement.email_id==Email.id,Announcement.user_id==Email.user_id))
        .where(Announcement.id==aid,Announcement.user_id==user.id,Email.user_id==user.id)).first()
    if not found:raise CorrectionNotFound()
    row,email=found
    refs=session.scalars(select(Analysis).where(Analysis.user_id==user.id,Analysis.announcement_id==aid)
        .order_by(Analysis.created_at.desc(),Analysis.id.desc()).limit(5)).all()
    legacy={k:(getattr(row,k).isoformat() if getattr(row,k) is not None and k in ('event_date','deadline') else getattr(row,k))
        for k in ('event_date','deadline','date_evidence','summary','requires_action','analysis_version')}
    base=build_action_card(private_source(row,email.received_at,email_parser_version=email.parser_version),legacy=legacy,
        ai_references=tuple({'status':r.status,'version':r.version,'result':r.result} for r in refs))
    return row,email,base


def _snapshots(session,user,row,base):
    q=select(S).where(S.user_id==user.id,S.email_id==row.email_id,S.source_index==row.source_index,
        S.source_fingerprint==row.source_fingerprint,S.baseline_hash==base.baseline_hash)
    return session.scalar(q)


def load_private_view(database,user,announcement_id):
    try:
        with database.transaction() as session:
            _identity(session,user)
            row,email,base=_source(session,user,announcement_id)
            snap=_snapshots(session,user,row,base)
            patch=None
            rev=None
            if snap and snap.revision_count:
                rev=session.scalar(select(R).where(R.user_id==user.id,R.snapshot_id==snap.id,R.revision==snap.revision_count))
                if not rev:raise CorrectionUnavailable()
                if rev.operation=='save':patch=CorrectionPatch.model_validate(rev.overrides)
            history=[{'id':s.id,'baseline_hash':s.baseline_hash,'created_at':s.created_at,'revision':s.revision_count}
                for s in session.scalars(select(S).where(S.user_id==user.id,S.email_id==row.email_id).order_by(S.created_at.desc(),S.id.desc()).limit(20))]
            item={k:getattr(row,k) for k in ('id','department','source_category','category','title','summary','event_date','deadline','requires_action','date_inferred','original_text')}
            received=email.received_at
            item['received_at']=((received.replace(tzinfo=timezone.utc) if received.tzinfo is None else received).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M')) if received else '未知'
            item['url']=base.source.url
            return PrivateCardView(item,base,apply_patch(base,patch) if patch else base,patch,
                snap.revision_count if snap else 0,history,bool(history and not snap),
                ((rev.created_at.replace(tzinfo=timezone.utc) if rev.created_at.tzinfo is None else rev.created_at).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M')) if rev else None)
    except (SQLAlchemyError,ValidationError):raise CorrectionUnavailable() from None


def save_private_correction(database,user,announcement_id,*,expected_revision,baseline_hash,operation,patch):
    if type(expected_revision) is not int or expected_revision<0 or operation not in ('save','reset'):
        raise ValueError('Invalid correction operation')
    if (operation=='save' and not isinstance(patch,CorrectionPatch)) or (operation=='reset' and patch is not None):
        raise ValueError('Invalid correction payload')
    try:
        with database.transaction() as session:
            _identity(session,user,lock=True)
            row,email,base=_source(session,user,announcement_id)
            if base.baseline_hash!=baseline_hash:raise CorrectionConflict()
            snap=_snapshots(session,user,row,base)
            if snap is None:
                if expected_revision!=0:raise CorrectionConflict()
                snap=S(user_id=user.id,email_id=row.email_id,source_index=row.source_index,source_fingerprint=row.source_fingerprint,
                    source_hash=base.source_hash,baseline_hash=base.baseline_hash,parser_version=base.parser_version,
                    source_text=row.original_text,source_metadata=base.source.model_dump(mode='json'),original_card=base.model_dump(mode='json'),revision_count=0)
                session.add(snap);session.flush()
            changed=session.execute(update(S).where(S.id==snap.id,S.user_id==user.id,S.revision_count==expected_revision)
                .values(revision_count=expected_revision+1))
            if changed.rowcount!=1:raise CorrectionConflict()
            session.add(R(user_id=user.id,snapshot_id=snap.id,revision=expected_revision+1,operation=operation,
                overrides=patch.model_dump(mode='json') if patch else {}))
            return expected_revision+1
    except (SQLAlchemyError,ValidationError):raise CorrectionUnavailable() from None


def load_private_history(database,user,snapshot_id,*,page_number=1):
    if type(page_number) is not int or page_number<1:raise ValueError('Invalid history page')
    try:
        with database.transaction() as session:
            _identity(session,user)
            snap=session.scalar(select(S).where(S.id==snapshot_id,S.user_id==user.id))
            if not snap:raise CorrectionNotFound()
            rows=session.scalars(select(R).where(R.snapshot_id==snap.id,R.user_id==user.id)
                .order_by(R.revision.desc()).offset((page_number-1)*20).limit(21)).all()
            return {'snapshot':{'id':snap.id,'source_text':snap.source_text,'original_card':snap.original_card,'created_at':snap.created_at},
                'revisions':[{'revision':r.revision,'operation':r.operation,'overrides':r.overrides,'created_at':r.created_at} for r in rows[:20]],
                'page_number':page_number,'has_more':len(rows)>20}
    except (SQLAlchemyError,ValidationError):raise CorrectionUnavailable() from None
