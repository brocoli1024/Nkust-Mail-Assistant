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
    if not re.fullmatch(r'/p/(?:404|405|406)-[1-9][0-9]*-[1-9][0-9]*(?:,[A-Za-z0-9_-]+)?\.php',urlsplit(url).path):return None
    return url


def stamp(value):
    if isinstance(value,datetime):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
    return value.isoformat() if value is not None and hasattr(value,'isoformat') else value


def public_snapshot(row):
    if not isinstance(row,PublicAnnouncement):raise TypeError('Public announcement required')
    return {'source_kind':'public','url':row.canonical_url,'title':row.title,'text':row.excerpt or '', 'html':None,
        'metadata':{'source_key':row.source_key,'external_id':row.external_id,'published_at':stamp(row.published_at)},
        'card':build_action_card(public_source(row)).model_dump(mode='json')}


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
    parser_changed=(old.get('metadata',{}).get('source_parser_version')!=new.get('metadata',{}).get('source_parser_version') or old['card']['parser_version']!=new['card']['parser_version'])
    if parser_changed:changes.append('解析版本不同，不代表官方內容已更新。')
    for key,label in (('deadline','截止日期'),('event_date','活動日期')):
        a,b=old['card']['fields'][key],new['card']['fields'][key]
        if (a['value'],a['state'])!=(b['value'],b['state']):
            show=lambda f:f['value'] if f['state'] in ('supported','user_confirmed') and f['value'] else '待確認'
            changes.append(label+'：'+show(a)+' → '+show(b)+'；這是來源／解析差異，請核對原文。')
    return changes
