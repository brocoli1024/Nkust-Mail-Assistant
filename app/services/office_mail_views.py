"""Public-table-only office mail reads; ranking precedes pagination."""
from datetime import datetime,timezone,timedelta
from sqlalchemy import select,func,and_,or_,case
from app.models.public_announcements import PublicAnnouncement as P,PublicSourceState as S,PublicSyncRun as R
from app.models.source_history import PublicSourceVersion as V
from app.services.office_mail_source import OFFICE_SOURCE_KEY,normalize_office_url
from app.services.office_mail_briefs import CAMPUS_LABELS
from app.services.public_sync import aware
from app.services.public_source import TAIPEI


def _time(value):return aware(value).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M') if value else '未知'


def _status(s):
    state=s.get(S,OFFICE_SOURCE_KEY)
    run=s.scalar(select(R).where(R.source_key==OFFICE_SOURCE_KEY).order_by(R.id.desc()).limit(1))
    discovery=s.get(S,'nkust-office-discovery')
    discovery_run=s.scalar(select(R).where(R.source_key=='nkust-office-discovery').order_by(R.id.desc()).limit(1))
    success=state.last_success_at if state else None
    return {'last_success':_time(success) if success else '尚無成功更新紀錄',
            'stale':not success or datetime.now(timezone.utc)-aware(success)>timedelta(hours=2),
            'last_run_status':run.status if run else None,
            'discovery_success':_time(discovery.last_success_at) if discovery and discovery.last_success_at else '尚無完整檢查紀錄',
            'discovery_started':discovery is not None,
            'discovery_backfill':discovery.history_status if discovery else 'not_started',
            'discovery_status':discovery_run.status if discovery_run else None,
            'discovery_error':discovery_run.error_code if discovery_run else None}


def _item(row,snapshot):
    brief=(snapshot or {}).get('metadata',{}).get('office')
    if not isinstance(brief,dict) or brief.get('version')!='office-brief-v1':
        brief={'headline':row.title,'kind':'general','department':'未提供','campus_flags':{},'campus_global':False,
               'campus_evidence':[],'sections':[],'warnings':['內容尚未整理，請核對完整原文。'],'fetch_error':None}
    return {'id':row.id,'external_id':row.external_id,'title':row.title,'body':row.excerpt,
            'url':normalize_office_url(row.canonical_url),'published':_time(row.published_at),'category':row.category,
            'brief':brief,'campus_names':[name for key,name in CAMPUS_LABELS.items() if brief.get('campus_flags',{}).get(key) is True]}


def _latest_ids():
    return select(V.canonical_url.label('url'),func.max(V.id).label('vid')).where(V.source_key==OFFICE_SOURCE_KEY).group_by(V.canonical_url).subquery()


def _query():
    latest=_latest_ids()
    return select(P,V.snapshot).outerjoin(latest,latest.c.url==P.canonical_url).outerjoin(V,V.id==latest.c.vid).where(P.source_key==OFFICE_SOURCE_KEY)


def list_office_mail(database,*,q='',category='',campuses=(),mode='all',page_number=1)->dict:
    statement=_query()
    if q.strip():statement=statement.where(or_(P.title.contains(q.strip(),autoescape=True),P.excerpt.contains(q.strip(),autoescape=True)))
    if category:statement=statement.where(P.category.is_(None) if category=='未分類' else P.category==category)
    rank=None
    if campuses and mode=='priority':
        def flag(key):return func.coalesce(V.snapshot['metadata']['office']['campus_flags'][key].as_boolean(),False)
        global_scope=func.coalesce(V.snapshot['metadata']['office']['campus_global'].as_boolean(),False)
        rank=case((or_(global_scope,*[flag(k) for k in campuses]),0),
                  (and_(~global_scope,*[~flag(k) for k in CAMPUS_LABELS]),1),else_=2)
    order=([rank] if rank is not None else [])+[P.published_at.desc().nulls_last(),P.id.desc()]
    with database.transaction() as s:
        source_total=s.scalar(select(func.count()).select_from(P).where(P.source_key==OFFICE_SOURCE_KEY))
        total=s.scalar(select(func.count()).select_from(statement.subquery()))
        rows=s.execute(statement.order_by(*order).offset((page_number-1)*20).limit(20)).all()
        items=[_item(row,snapshot) for row,snapshot in rows]
        for item in items:
            b=item['brief']
            item['priority_reason']='全校性公告' if b.get('campus_global') else '與所選校區相關' if any(b.get('campus_flags',{}).get(k) for k in campuses) else '校區待確認，仍保留顯示' if not item['campus_names'] else '其他校區公告'
        return dict(items=items,total=total,source_total=source_total,**_status(s))


def office_mail_detail(database,pid:int)->dict:
    with database.transaction() as s:
        found=s.execute(_query().where(P.id==pid)).first()
        if not found:raise LookupError('Office announcement not found')
        return dict(item=_item(*found),**_status(s))


def office_mail_history(database,pid:int,*,page_number=1)->dict:
    from app.services.source_views import version
    with database.transaction() as s:
        row=s.scalar(select(P).where(P.id==pid,P.source_key==OFFICE_SOURCE_KEY))
        if not row:raise LookupError('Office announcement not found')
        scope=(V.source_key==OFFICE_SOURCE_KEY,V.canonical_url==row.canonical_url)
        rows=s.scalars(select(V).where(*scope).order_by(V.id.desc()).offset((page_number-1)*20).limit(21)).all()
        items=[version(v,'public',s.scalar(select(V).where(*scope,V.id<v.id).order_by(V.id.desc()).limit(1))) for v in rows[:20]]
        return {'title':row.title,'private':False,'items':items,'page_number':page_number,'has_more':len(rows)>20,'back':f'/public/office-mail/{pid}'}
