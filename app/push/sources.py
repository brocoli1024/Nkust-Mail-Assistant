"""Exact public identity resolution, no network and no private source traversal."""
import hashlib,json
from sqlalchemy import select
from app.models.public_announcements import PublicAnnouncement
from app.models.source_history import PublicSourceVersion
from app.services.source_history import official_identity
from .contracts import PublicRef
from .security import PushError

def parse_public_ref(source_ref):
    try:
        key,url=json.loads(source_ref)
        if key not in ('nkust-latest','nkust-office-mail') or not isinstance(url,str):raise ValueError()
        canonical=official_identity(url)
        if canonical!=url:raise ValueError()
    except Exception:raise PushError('PUSH_SOURCE_NOT_FOUND') from None
    return key,canonical

def resolve_public_ref(session,source_ref):
    key,canonical=parse_public_ref(source_ref)
    row=session.scalar(select(PublicAnnouncement).where(PublicAnnouncement.source_key==key,PublicAnnouncement.canonical_url==canonical))
    if row is None:raise PushError('PUSH_SOURCE_NOT_FOUND')
    latest=session.scalar(select(PublicSourceVersion).where(PublicSourceVersion.source_key==key,PublicSourceVersion.canonical_url==canonical).order_by(PublicSourceVersion.id.desc()).limit(1))
    article=((latest.snapshot.get('metadata') or {}).get('article') or {}) if latest else {}
    related=sorted(({k:v for k,v in doc.items() if k not in ('error','checked_at','fetched_at')} for doc in article.get('related',[])),key=lambda doc:doc.get('url',''))
    semantic={'title':row.title,'text':row.excerpt,'url':canonical,'article':article.get('text'),'related':related}
    version=hashlib.sha256(json.dumps(semantic,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    prefix='/public/office-mail/' if key=='nkust-office-mail' else '/public/announcements/'
    return PublicRef(row.id,json.dumps([key,canonical],ensure_ascii=False),row.title,prefix+str(row.id),version)
