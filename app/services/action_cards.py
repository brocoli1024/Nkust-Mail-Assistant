"""Pure, network-free action cards. Never write legacy parsed fields."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from app.schemas.action_cards import SourceDocument, SourceSegment, CardField, ActionCard, Evidence
from app.services.action_card_rules import extract

PARSER_VERSION='action-card-v2'
TAIPEI=timezone(timedelta(hours=8))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def build_action_card(source, *, legacy=None, ai_references=()):
    fields,candidates,warnings=extract(source)
    if source.kind=='public' and source.metadata.get('article',{}).get('stale'):
        fields={key:field.model_copy(update={'state':'stale','warnings':(*field.warnings,'RSS內容已變更，本文尚待重新讀取。')}) for key,field in fields.items()}
    content=next((s for s in source.segments if s.kind=='official_text' and s.text),None)
    content=content or next((s for s in source.segments if s.kind!='title' and s.text),None)
    content=content or next((s for s in source.segments if s.text),None)
    fields['summary']=CardField(value=(content.text[:160] if content else None),
        state='supported' if content else 'pending',origin='source_excerpt',
        evidence=(Evidence(segment=source.segments.index(content),quote=content.text[:160],start=0,end=min(160,len(content.text)),role='summary'),) if content else (),
        warnings=('來源節錄，完整內容請核對原文',) if content else ())
    refs=[]
    from app.schemas.analysis import AnalysisOutput
    from pydantic import ValidationError
    for ref in ai_references:
        if not isinstance(ref,dict):
            continue
        result=None
        warning='既有 AI 結果，版本／來源一致性待確認'
        if ref.get('status')=='completed' and isinstance(ref.get('result'),dict):
            try:
                data={k:v for k,v in ref['result'].items() if k in AnalysisOutput.model_fields}
                result=AnalysisOutput.model_validate(data).model_dump()
                for role, evidence_key in (('event_date','event_evidence'),('deadline','deadline_evidence'),('requires_action','action_evidence')):
                    quote=result.get(evidence_key)
                    if quote and not any(quote in segment.text for segment in source.segments):
                        result[role]=None
                        result[evidence_key]=None
            except (ValidationError,ValueError,TypeError):
                warning='既有 AI 結果格式無法驗證；請核對原文'
        refs.append({'status':ref.get('status') if ref.get('status') in ('completed','failed','pending') else 'unknown',
            'version':str(ref.get('version') or '')[:255],'result':result,'warning':warning})
    payload=source.model_dump(mode='json')
    if source.kind=='public' and 'article' in payload['metadata']:
        payload['metadata']['article'].pop('error',None)  # Fetch failures do not invalidate edits to unchanged text.
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


def public_source(row, *, article=None):
    from app.services.public_source import normalize_public_url, PublicSourceError
    try:
        url=normalize_public_url(row.canonical_url)
    except PublicSourceError:
        url=None
    return SourceDocument(kind='public',source_ref=json.dumps([row.source_key,url or ("invalid:"+digest(row.canonical_url))],ensure_ascii=False),title=row.title,
        segments=(SourceSegment(kind='title',text=row.title),SourceSegment(kind='excerpt',text=row.excerpt or '')) +
            ((SourceSegment(kind='official_text',text=article['text']),) if article and article.get('text') else ()),
        url=url,metadata={'article':{'text':bool(article.get('text')),'error':article.get('error'),'stale':bool(article.get('rss_hash') and article['rss_hash']!=getattr(row,'content_hash',None))}} if article else {})


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


def field_display(card,key):
    field=card.fields[key]
    if field.state=='stale':return {'value':field.value or '資訊待重新核對','state':'RSS內容已變更，本文待更新；舊解析結果僅供參考。'}
    if field.value:return {'value':field.value,'state':'我的修正 · 使用者確認，非系統驗證' if field.origin=='user' else '來源規則辨識'}
    if field.origin=='user':return {'value':'待確認','state':'我的修正 · 保留待確認'}
    article=card.source.metadata.get('article') or {}
    if card.source.kind=='public' and not article.get('text'):
        return {'value':'尚待讀取完整原文','state':'本文讀取失敗，稍後重試；目前僅有來源摘要。' if article.get('error') else '目前僅有來源摘要，完整資訊尚未讀取。'}
    if field.evidence or key in ('deadline','event_date') and any(e.role is None and card.source.segments[e.segment].kind!='title' for e in card.candidates):
        return {'value':'資訊待核對','state':'日期年份、用途或多個候選資訊尚未能確定，請查看依據。'}
    labels={'deadline':'截止說明','event_date':'活動日期','materials':'材料說明','audience':'適用對象','action':'行動說明','summary':'摘要'}
    return {'value':'本文未找到'+labels[key],'state':'請核對完整公告、附件或報名頁；不代表沒有相關規定。'}
