"""Read-only, owner-checked source grouping and archived originals."""
from datetime import timezone
from functools import wraps
from zoneinfo import ZoneInfo
from sqlalchemy import select,and_,or_
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from app.models.multi_user import Announcement as A,Email as E
from app.models.public_announcements import PublicAnnouncement as P
from app.models.source_history import PublicSourceVersion as PV,PrivateSourceVersion as MV
from app.schemas.action_cards import ActionCard
from app.services.source_history import official_identity,public_snapshot,private_snapshot,snapshot_changes
from app.services.public_source import SOURCE_KEY
from app.services.action_card_corrections import _identity,CorrectionNotFound,CorrectionUnavailable


def guarded(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (SQLAlchemyError,ValidationError,KeyError,TypeError,ValueError):raise CorrectionUnavailable() from None
    return run


def checked(snapshot,kind):
    if not isinstance(snapshot,dict) or snapshot.get('source_kind')!=kind:raise ValueError('Invalid source snapshot')
    if not all(isinstance(snapshot.get(k),str) for k in ('title','text')):raise ValueError('Invalid original')
    if snapshot.get('html') is not None and not isinstance(snapshot['html'],str):raise ValueError('Invalid HTML')
    if kind=='public' and snapshot.get('html') is not None:raise ValueError('Private content in public snapshot')
    if not isinstance(snapshot.get('metadata'),dict):raise ValueError('Invalid source metadata')
    card=ActionCard.model_validate(snapshot['card'])
    if card.source.kind!=kind:raise ValueError('Invalid source card')
    return snapshot


def version(row,kind,previous=None):
    snap=checked(row.snapshot,kind)
    old=checked(previous.snapshot,kind) if previous else None
    when=row.captured_at
    return {'id':row.id,'snapshot':snap,'baseline':row.baseline,
        'captured':(when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when).astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S'),
        'changes':snapshot_changes(old,snap),'previous':previous.id if previous else None}


def page_data(rows,page_number):
    return {'items':rows[:20],'has_more':len(rows)>20,'page_number':page_number}


@guarded
def public_history(database,pid,page_number=1):
    with database.transaction() as s:
        p=s.scalar(select(P).where(P.id==pid,P.source_key==SOURCE_KEY))
        if not p:raise CorrectionNotFound()
        scope=(PV.source_key==SOURCE_KEY,PV.canonical_url==p.canonical_url)
        rows=s.scalars(select(PV).where(*scope).order_by(PV.id.desc()).offset((page_number-1)*20).limit(21)).all()
        data=page_data(rows,page_number)
        data['items']=[version(r,'public',s.scalar(select(PV).where(*scope,PV.id<r.id).order_by(PV.id.desc()).limit(1))) for r in data['items']]
        return dict(data,title=p.title,private=False,back=f'/public/announcements/{pid}')


@guarded
def private_history(database,user,page_number=1):
    with database.transaction() as s:
        _identity(s,user)
        rows=s.scalars(select(MV).where(MV.user_id==user.id).order_by(MV.id.desc()).offset((page_number-1)*20).limit(21)).all()
        data=page_data(rows,page_number)
        data['items']=[version(r,'private') for r in data['items']]
        return dict(data,title='我的來源留存',private=True,back='/announcements')


@guarded
def private_version(database,user,vid):
    with database.transaction() as s:
        _identity(s,user)
        row=s.scalar(select(MV).where(MV.id==vid,MV.user_id==user.id))
        if not row:raise CorrectionNotFound()
        # Same mail + reliable article URL, otherwise exact original position/fingerprint.
        scope=[MV.user_id==user.id,MV.email_id==row.email_id,MV.id<row.id]
        scope+=([MV.canonical_url==row.canonical_url] if row.canonical_url else
            [MV.source_index==row.source_index,MV.source_fingerprint==row.source_fingerprint])
        prior=s.scalar(select(MV).where(*scope).order_by(MV.id.desc()).limit(1))
        return version(row,'private',prior)


@guarded
def related_sources(database,user,aid,page_number=1):
    with database.transaction() as s:
        _identity(s,user)
        join=select(A,E).join(E,and_(A.email_id==E.id,A.user_id==E.user_id)).where(A.user_id==user.id,E.user_id==user.id)
        found=s.execute(join.where(A.id==aid)).first()
        if not found:raise CorrectionNotFound()
        row,email=found;anchor=private_snapshot(row,email);key=official_identity(row.url)
        result={'anchor':anchor,'aid':aid,'identity':key,'public':[],'private':[],'has_more':False,'page_number':page_number}
        if not key:return result
        pubs=s.scalars(select(P).where(P.source_key==SOURCE_KEY,P.canonical_url==key).order_by(P.id).offset((page_number-1)*20).limit(21)).all()
        # Fetch only the owner's URL-prefix candidates; exact normalized validation precedes pagination.
        from sqlalchemy import func
        from urllib.parse import urlsplit,urlunsplit
        parsed=urlsplit(key)
        port_key=urlunsplit((parsed.scheme,parsed.netloc+':443',parsed.path,parsed.query,''))
        candidates=s.execute(join.where(or_(func.lower(A.url).startswith(key.lower(),autoescape=True),
            func.lower(A.url).startswith(port_key.lower(),autoescape=True))).order_by(A.id)).all()
        matches=[(a,e) for a,e in candidates if official_identity(a.url)==key]
        privs=matches[(page_number-1)*20:page_number*20+1]
        result['has_more']=len(privs)>20 or len(pubs)>20
        for p in pubs[:20]:
            snap=public_snapshot(p)
            result['public'].append({'snapshot':snap,'link':f'/public/announcements/{p.id}','changes':snapshot_changes(snap,anchor)})
        for a,e in privs[:20]:
            snap=private_snapshot(a,e)
            result['private'].append({'snapshot':snap,'link':f'/announcements/{a.id}','changes':snapshot_changes(snap,anchor)})
        return result
