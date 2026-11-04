"""Maintainer-only writes of anonymously verified official mail, never Gmail."""
from dataclasses import dataclass,field
import hashlib
import json
import time
from sqlalchemy import select,func
from app.models.public_announcements import PublicAnnouncement as P,PublicSyncRun as R
from app.models.source_history import PublicSourceVersion as V
from app.services.public_source import PublicSourceError
from app.services.public_sync import SourceLease,SyncResult,begin_run,finish_run,apply_classification,aware
from app.services.source_history import record_public_version
from app.services.office_mail_source import OFFICE_SOURCE_KEY,OfficeDocument,normalize_office_url,fetch_office_mail
from app.services.office_mail_briefs import build_office_brief

@dataclass
class OfficeSyncResult:
    added:int=0
    updated:int=0
    unchanged:int=0
    failed:int=0
    status:str='success'
    failures:list=field(default_factory=list)


def _safe_code(exc):
    # Fixed allowlist only; arbitrary provider/DB/URL errors never leave process.
    allowed={'OFFICE_MAIL_URL','OFFICE_MAIL_SIZE','OFFICE_MAIL_ENCODING','OFFICE_MAIL_NOT_PUBLIC',
             'OFFICE_MAIL_STRUCTURE','OFFICE_MAIL_BODY','OFFICE_MAIL_REDIRECT','OFFICE_MAIL_HTTP_404',
             'OFFICE_MAIL_RESPONSE','PUBLIC_SOURCE_UNAVAILABLE','PUBLIC_SOURCE_TIMEOUT','PUBLIC_SOURCE_ADDRESS',
             'PUBLIC_SOURCE_SIZE','PUBLIC_SOURCE_ENCODING','OFFICE_SYNC_BUDGET'}
    code=str(exc) if isinstance(exc,PublicSourceError) else None
    return code if code in allowed else 'OFFICE_MAIL_UNAVAILABLE'


def import_office_mail(database,urls:list[str],*,source=None,now=None,write_fence=None)->OfficeSyncResult:
    if not isinstance(urls,list) or not 1<=len(urls)<=20:raise PublicSourceError('OFFICE_MAIL_URL_LIST')
    urls=list(dict.fromkeys(normalize_office_url(u) for u in urls))
    lease=SourceLease(database,now=now,source_key=OFFICE_SOURCE_KEY);lease.acquire()
    run_id=None;result=OfficeSyncResult();deadline=time.monotonic()+90
    try:
        run_id=begin_run(database,lease,'recent')
        for url in urls:
            try:
                if time.monotonic()>=deadline:raise PublicSourceError('OFFICE_SYNC_BUDGET')
                doc=(source or fetch_office_mail)(url)
                if not isinstance(doc,OfficeDocument) or doc.url!=url or not doc.body or len(doc.body)>40000:raise PublicSourceError('OFFICE_MAIL_STRUCTURE')
                brief=dict(build_office_brief(doc),department=doc.department,fetch_error=None)
                stamp=doc.published_at.isoformat() if doc.published_at else None
                digest=hashlib.sha256(json.dumps([doc.title,doc.body,doc.department,stamp],ensure_ascii=False).encode()).hexdigest()
                with database.transaction() as s:
                    if write_fence is not None:write_fence(s)
                    state=lease.verify(s)
                    row=s.scalar(select(P).where(P.source_key==OFFICE_SOURCE_KEY,P.canonical_url==url))
                    if row is None:
                        row=P(source_key=OFFICE_SOURCE_KEY,canonical_url=url,first_seen_at=lease.clock())
                        s.add(row);result.added+=1
                    elif row.content_hash==digest:result.unchanged+=1
                    else:result.updated+=1
                    changed=row.content_hash!=digest
                    if changed:
                        row.title=doc.title;row.excerpt=doc.body;row.external_id=doc.external_id
                        row.published_at=doc.published_at;row.content_hash=digest;row.updated_at=lease.clock()
                        apply_classification(row)
                    row.last_seen_at=lease.clock();s.flush()
                    record_public_version(s,row,lease.clock(),office=brief)
                    if doc.published_at and (not state.oldest_seen_at or aware(state.oldest_seen_at)>doc.published_at):state.oldest_seen_at=doc.published_at
            except Exception as exc:
                code=_safe_code(exc);result.failed+=1
                result.failures.append({'announcement_id':url.rsplit('/',1)[1],'error_code':code})
                with database.transaction() as s:
                    if write_fence is not None:write_fence(s)
                    lease.verify(s)
                    row=s.scalar(select(P).where(P.source_key==OFFICE_SOURCE_KEY,P.canonical_url==url))
                    if row:
                        old=s.scalar(select(V).where(V.source_key==OFFICE_SOURCE_KEY,V.canonical_url==url).order_by(V.id.desc()).limit(1))
                        brief=dict((old.snapshot.get('metadata',{}).get('office') or {}) if old else {},fetch_error=code)
                        row.last_seen_at=lease.clock()
                        record_public_version(s,row,lease.clock(),office=brief)
        result.status='failed' if result.failed==len(urls) else 'partial' if result.failed else 'success'
        if result.status=='success':
            with database.transaction() as s:lease.verify(s).last_success_at=lease.clock()
    except Exception:
        result.status='failed'
        raise
    finally:
        try:
            if run_id is not None:
                finish_run(database,run_id,SyncResult(result.added,result.updated,result.unchanged,result.failed,result.status),
                           'OFFICE_MAIL_PARTIAL' if result.failed else None,now=lease.clock())
        finally:lease.release()
    return result


def refresh_office_mail(database,*,limit=8,source=None,now=None)->OfficeSyncResult:
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=20:raise ValueError('limit must be 1..20')
    with database.transaction() as s:
        urls=list(s.scalars(select(P.canonical_url).where(P.source_key==OFFICE_SOURCE_KEY).order_by(P.last_seen_at.asc(),P.id.asc()).limit(limit)))
    if not urls:return OfficeSyncResult()
    return import_office_mail(database,urls,source=source,now=now)
