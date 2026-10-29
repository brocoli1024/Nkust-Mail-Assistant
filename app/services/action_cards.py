"""Pure, network-free action cards. Never write legacy parsed fields."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from app.schemas.action_cards import SourceDocument, SourceSegment, CardField, ActionCard, Evidence
from app.services.action_card_rules import extract

PARSER_VERSION='action-card-v1'
TAIPEI=timezone(timedelta(hours=8))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def build_action_card(source, *, legacy=None, ai_references=()):
    fields,candidates,warnings=extract(source)
    content=next((s for s in source.segments if s.kind!='title' and s.text),None)
    content=content or next((s for s in source.segments if s.text),None)
    fields['summary']=CardField(value=(content.text[:160] if content else None),
        state='supported' if content else 'pending',origin='source_excerpt',
        warnings=('來源節錄，完整內容請核對原文',) if content else ())
    refs=[]
    for ref in ai_references:
        if isinstance(ref,dict):
            refs.append({'status':ref.get('status'),'version':ref.get('version'),
                'result':ref.get('result'),'warning':'既有 AI 結果，版本／來源一致性待確認'})
    payload=source.model_dump(mode='json')
    if source.anchor:
        anchor=source.anchor.replace(tzinfo=timezone.utc) if source.anchor.tzinfo is None else source.anchor
        payload['anchor']=anchor.astimezone(timezone.utc).isoformat()
    sh=digest(payload)
    bh=digest([sh,PARSER_VERSION,legacy or {},refs])
    deadline_text=' '.join(e.quote for e in fields['deadline'].evidence)
    kind=('registration' if '報名' in deadline_text else 'application' if '申請' in deadline_text else
          'submission' if re.search(r'繳件|繳交',deadline_text) else 'unknown')
    return ActionCard(source=source,source_hash=sh,baseline_hash=bh,parser_version=PARSER_VERSION,
        fields=fields,candidates=candidates,requires_action=True if fields['action'].value else None,
        deadline_kind=kind,legacy=legacy or {},ai_references=tuple(refs),warnings=warnings,
        time_status='unparsed' if any(re.search(r'\d{1,2}[:：]\d{2}|\d{1,2}時',s.text) for s in source.segments) else 'unknown')


def apply_patch(card, patch):
    fields=dict(card.fields)
    action=card.requires_action
    kind=card.deadline_kind
    for name,change in patch.fields.items():
        if change.mode=='inherit':
            continue
        ev=[]
        if change.quote:
            for i,s in enumerate(card.source.segments):
                at=s.text.find(change.quote)
                if at>=0:
                    ev.append(Evidence(segment=i,quote=change.quote,start=at,end=at+len(change.quote),role=name))
        fields[name]=CardField(value=change.value if change.mode=='value' else None,
            state='user_confirmed' if change.mode=='value' else 'pending',origin='user',evidence=tuple(ev),
            warnings=('個人補充，系統未驗證來源',) if change.quote and not ev else ())
        if name=='action':
            action={'yes':True,'no':False,'unknown':None}[patch.action_decision] if change.mode=='value' else None
        if name=='deadline':
            kind=patch.deadline_kind if change.mode=='value' else 'unknown'
    return card.model_copy(update={'fields':fields,'requires_action':action,'deadline_kind':kind})


def display_context(card, *, now):
    if now.tzinfo is None:
        raise ValueError('Aware display time required')
    today=now.astimezone(TAIPEI).date().isoformat()
    deadline=card.fields['deadline']
    return {'taipei_today':today,'deadline_passed':bool(deadline.value and deadline.state in ('supported','user_confirmed') and deadline.value<today)}


def public_source(row):
    from app.services.public_source import normalize_public_url, PublicSourceError
    try:
        url=normalize_public_url(row.canonical_url)
    except PublicSourceError:
        url=None
    return SourceDocument(kind='public',source_ref=json.dumps([row.source_key,url or row.canonical_url],ensure_ascii=False),title=row.title,
        segments=(SourceSegment(kind='title',text=row.title),SourceSegment(kind='excerpt',text=row.excerpt or '')),url=url)


def private_source(row, received_at, *, email_parser_version=None):
    anchor=received_at
    if anchor:
        anchor=(anchor.replace(tzinfo=timezone.utc) if anchor.tzinfo is None else anchor).astimezone(TAIPEI)
    url=None
    try:
        p=urlsplit(row.url or '')
        if p.scheme in ('http','https') and p.hostname and not p.username and not p.password and not any(c.isspace() or ord(c)<32 for c in row.url) and '\\' not in row.url:
            url=row.url
    except ValueError:
        pass
    return SourceDocument(kind='private',source_ref=json.dumps([row.email_id,row.source_index,row.source_fingerprint]),
        title=row.title,segments=(SourceSegment(kind='original',text=row.original_text),),url=url,anchor=anchor,
        metadata={'email_id':row.email_id,'source_index':row.source_index,'source_fingerprint':row.source_fingerprint,'email_parser_version':email_parser_version})


def demo_source(item):
    return SourceDocument(kind='demo',source_ref='demo:'+item.id,title=item.title,
        segments=(SourceSegment(kind='title',text=item.title),SourceSegment(kind='excerpt',text=item.excerpt)))
