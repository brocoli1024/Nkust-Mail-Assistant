"""Conservative official identity and immutable original-source projections."""
import re
from datetime import datetime,timezone
from urllib.parse import urlsplit
from app.services.public_source import normalize_public_url,PublicSourceError
from app.services.action_cards import build_action_card,public_source,private_source
from app.models.public_announcements import PublicAnnouncement


def official_identity(value):
    try:url=normalize_public_url(value)
    except PublicSourceError:return None
    if urlsplit(url).hostname=='officemail.nkust.edu.tw':
        from app.services.office_mail_source import normalize_office_url
        try:return normalize_office_url(value)
        except PublicSourceError:return None
    if not re.fullmatch(r'/p/(?:404|405|406)-[1-9][0-9]*-[1-9][0-9]*(?:,[A-Za-z0-9_-]+)?\.php',urlsplit(url).path):return None
    return url


def stamp(value):
    if isinstance(value,datetime):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
    return value.isoformat() if value is not None and hasattr(value,'isoformat') else value


def public_snapshot(row, *, article=None, office=None):
    if not isinstance(row,PublicAnnouncement):raise TypeError('Public announcement required')
    return {'source_kind':'public','url':row.canonical_url,'title':row.title,'text':row.excerpt or '', 'html':None,
        'metadata':{'source_key':row.source_key,'external_id':row.external_id,'published_at':stamp(row.published_at), **({'article':article} if article else {}), **({'office':office} if office is not None else {})},
        'card':build_action_card(public_source(row,article=article)).model_dump(mode='json')}


def private_snapshot(row,email,parser_version=None):
    if row.user_id!=email.user_id:raise ValueError('Source owner mismatch')
    version=parser_version if parser_version is not None else email.parser_version
    legacy={k:stamp(getattr(row,k,None)) for k in ('event_date','deadline','date_evidence','source_category')}
    return {'source_kind':'private','url':row.url,'title':row.title,'text':row.original_text,'html':row.original_html,
        'metadata':{'source_parser_version':version,'received_at':stamp(email.received_at),'original_parse':legacy},
        'card':build_action_card(private_source(row,email.received_at,email_parser_version=version),legacy=legacy).model_dump(mode='json')}


def snapshot_changes(old,new):
    if old is None:return ['首次留存基準，不能據此還原更早的完整歷史。']
    changes=[]
    for key,label in (('title','來源標題'),('text','來源原文／摘要'),('html','原始HTML'),('url','來源網址')):
        if old.get(key)!=new.get(key):changes.append(label+'不同，請核對兩個版本。')
    if old.get('metadata',{}).get('article',{}).get('text')!=new.get('metadata',{}).get('article',{}).get('text'):
        changes.append('官方本文不同，請核對兩個版本。')
    def linked_content(snapshot):
        docs=(snapshot.get('metadata',{}).get('article') or {}).get('related',[])
        return sorted(({k:v for k,v in d.items() if k not in ('error','checked_at','fetched_at')} for d in docs),key=lambda d:d.get('url',''))
    if linked_content(old)!=linked_content(new):
        changes.append('報名表單或票券來源資訊不同，請依各自流程核對新舊版本。')
    parser_changed=(old.get('metadata',{}).get('source_parser_version')!=new.get('metadata',{}).get('source_parser_version') or old['card']['parser_version']!=new['card']['parser_version'])
    if parser_changed:changes.append('解析版本不同，不代表官方內容已更新。')
    for key,label in (('deadline','截止日期'),('event_date','活動日期')):
        a,b=old['card']['fields'][key],new['card']['fields'][key]
        if (a['value'],a['state'])!=(b['value'],b['state']):
            show=lambda f:f['value'] if f['state'] in ('supported','user_confirmed') and f['value'] else '待確認'
            changes.append(label+'：'+show(a)+' → '+show(b)+'；這是來源／解析差異，請核對原文。')
    return changes


def _digest(snapshot):
    import hashlib,json
    return hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def record_public_version(session,row,now,*,baseline=False,article=None,office=None):
    """Caller must hold the public source lease in the same transaction."""
    from sqlalchemy import select
    from app.models.source_history import PublicSourceVersion as V
    latest=session.scalar(select(V).where(V.source_key==row.source_key,V.canonical_url==row.canonical_url).order_by(V.id.desc()).limit(1))
    if article is None and latest:
        article=latest.snapshot.get('metadata',{}).get('article')
    if office is None and latest:
        office=latest.snapshot.get('metadata',{}).get('office')
    snapshot=public_snapshot(row,article=article,office=office)
    fingerprint=_digest(snapshot)
    if latest and latest.snapshot_hash==fingerprint:return
    session.add(V(source_key=row.source_key,canonical_url=row.canonical_url,snapshot_hash=fingerprint,
        snapshot=snapshot,captured_at=now,baseline=baseline and latest is None))
    session.flush()


def record_private_version(session,row,email,now,*,parser_version=None,baseline=False):
    """Caller must hold the owner's sync lease; fingerprint is not a dedup key."""
    from sqlalchemy import select
    from app.models.source_history import PrivateSourceVersion as V
    snapshot=private_snapshot(row,email,parser_version)
    latest=session.scalar(select(V).where(V.user_id==row.user_id,V.email_id==row.email_id,
        V.source_index==row.source_index).order_by(V.id.desc()).limit(1))
    fingerprint=_digest(snapshot)
    if latest and latest.snapshot_hash==fingerprint:return
    session.add(V(user_id=row.user_id,email_id=row.email_id,source_index=row.source_index,
        source_fingerprint=row.source_fingerprint,canonical_url=official_identity(row.url),snapshot_hash=fingerprint,
        snapshot=snapshot,captured_at=now,baseline=baseline and latest is None))
    session.flush()
