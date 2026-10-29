"""Authenticated HTML correction forms; public edits have no server write route."""
import re
from urllib.parse import parse_qs,urlsplit
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from app.api.session import page
from app.core.session import current_user,current_page_user
from app.schemas.action_cards import CorrectionPatch
from app.services.action_cards import display_context
from app.services.action_card_corrections import (load_private_view,save_private_correction,load_private_history,CorrectionNotFound,CorrectionConflict,CorrectionUnavailable)

router=APIRouter()
LABELS={'summary':'摘要','action':'需要採取的行動','audience':'適用對象','materials':'所需材料','deadline':'報名／申請／繳件截止','event_date':'活動日期'}


def card_context(card,scope):
    context={'card':card,'scope':scope,'labels':LABELS,'card_context':display_context(card,now=datetime.now(timezone.utc))}
    host=urlsplit(card.source.url or '').hostname or ''
    context['link_unverified']=bool(card.source.url and not (host=='nkust.edu.tw' or host.endswith('.nkust.edu.tw')))
    if scope!='private':
        context['payload']={'schema_version':1,'scope':scope,'base_card':card.model_dump(mode='json'),
            'expected_revision':0,'taipei_today':context['card_context']['taipei_today']}
    return context


def render_private(request,user,aid,*,error=None,status=200,submitted=None):
    try:v=load_private_view(request.app.state.database,user,aid)
    except CorrectionNotFound:raise HTTPException(404,'找不到公告。') from None
    except CorrectionUnavailable as exc:
        r=page(request,'action_card_error.html',user=user,source=exc.source,title='暫時無法讀取修正資料',detail='修正歷史讀取不完整，請稍後重新載入；尚未覆寫任何修正。')
        r.status_code=503;return r
    values={}
    if v.patch:
        for key,change in v.patch.fields.items():
            values.update({key+'.mode':change.mode,key+'.value':change.value or '',key+'.quote':change.quote or '',key+'.confirmed':'on' if change.confirmed else ''})
        values.update(action_decision=v.patch.action_decision,deadline_kind=v.patch.deadline_kind)
    if submitted is not None:values=submitted
    sessions=request.app.state.sessions
    r=page(request,'announcement_detail.html',user=user,item=v.item,view=v,error=error,form_values=values,
        csrf=sessions.csrf(request.cookies.get(sessions.cookie_name)),**card_context(v.effective,'private'))
    r.status_code=status;return r


@router.post('/announcements/{announcement_id}/action-card/corrections')
async def correct(announcement_id:int,request:Request,user=Depends(current_user)):
    state=request.app.state
    if request.headers.get('origin') not in (None,state.oauth_settings.base_url.rstrip('/')) or request.headers.get('sec-fetch-site')=='cross-site':
        raise HTTPException(403,'請從本站儲存修正。')
    if request.headers.get('content-type','').split(';')[0].strip()!='application/x-www-form-urlencoded':
        raise HTTPException(415,'請使用公告修正表單。')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>128*1024:raise HTTPException(413,'表單過大，請縮短內容。')
    try:
        encoded=raw.decode('ascii')
        if re.search(r'%(?![0-9a-fA-F]{2})',encoded):raise ValueError()
        fields=parse_qs(encoded,keep_blank_values=True,max_num_fields=32,encoding='utf-8',errors='strict')
        if any(len(v)!=1 for v in fields.values()):raise ValueError()
        values={k:v[0] for k,v in fields.items()}
    except (ValueError,UnicodeError):raise HTTPException(422,'表單編碼或欄位不正確。') from None
    if not state.sessions.valid_csrf(request.cookies.get(state.sessions.cookie_name),values.get('csrf_token')):
        raise HTTPException(403,'驗證失敗，請重新整理後重試。')
    allowed={'csrf_token','operation','baseline_hash','expected_revision','action_decision','deadline_kind'}|{k+'.'+p for k in LABELS for p in ('mode','value','quote','confirmed')}
    try:
        if set(values)-allowed:raise ValueError()
        if not re.fullmatch(r'[0-9]+',values.get('expected_revision','')):raise ValueError()
        if not re.fullmatch(r'[0-9a-f]{64}',values.get('baseline_hash','')):raise ValueError()
        operation=values.get('operation')
        if operation not in ('save','reset'):raise ValueError()
        patch=None
        if operation=='save':
            changes={}
            for key in LABELS:
                mode=values.get(key+'.mode','inherit')
                changes[key]={'mode':mode}
                if mode=='value':
                    changes[key].update(value=values.get(key+'.value'),quote=values.get(key+'.quote') or None,confirmed=values.get(key+'.confirmed')=='on')
            patch=CorrectionPatch.model_validate({'fields':changes,'action_decision':values.get('action_decision','unknown'),'deadline_kind':values.get('deadline_kind','unknown')})
        save_private_correction(state.database,user,announcement_id,expected_revision=int(values['expected_revision']),
            baseline_hash=values['baseline_hash'],operation=operation,patch=patch)
    except (ValueError,ValidationError):
        return render_private(request,user,announcement_id,error='修正尚未儲存：請檢查欄位長度、日期與原文確認。',status=422,submitted=values)
    except CorrectionNotFound:raise HTTPException(404,'找不到公告。') from None
    except CorrectionConflict:
        return render_private(request,user,announcement_id,error='來源或修正版本已變更；本次未儲存，請核對目前資訊後重試。',status=409,submitted=values)
    except CorrectionUnavailable:
        return render_private(request,user,announcement_id,error='暫時無法儲存，本次沒有確認成功；請重新載入後檢查。',status=503,submitted=values)
    return RedirectResponse(f'/announcements/{announcement_id}',status_code=303)


@router.get('/action-cards/history/{snapshot_id}')
def history(snapshot_id:int,request:Request,user=Depends(current_page_user),page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    try:data=load_private_history(request.app.state.database,user,snapshot_id,page_number=page_number)
    except CorrectionNotFound:raise HTTPException(404,'找不到修正歷史。') from None
    except CorrectionUnavailable as exc:
        r=page(request,'action_card_error.html',user=user,source=exc.source,title='暫時無法讀取修正歷史',detail='資料讀取失敗，請稍後重試。');r.status_code=503;return r
    return page(request,'action_card_history.html',user=user,data=data)


@router.get('/action-cards/sources/{announcement_id}')
def snapshot_list(announcement_id:int,request:Request,user=Depends(current_page_user),page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    from app.services.action_card_corrections import load_private_snapshots
    try:data=load_private_snapshots(request.app.state.database,user,announcement_id,page_number=page_number)
    except CorrectionNotFound:raise HTTPException(404,'找不到公告。') from None
    except CorrectionUnavailable:
        r=page(request,'action_card_error.html',user=user,title='暫時無法讀取修正歷史',detail='資料讀取失敗，請稍後重試。');r.status_code=503;return r
    return page(request,'action_card_snapshots.html',user=user,data=data)
