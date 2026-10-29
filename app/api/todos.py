"""Authenticated todo HTML routes. Public todos never have a server write API."""
import re
from urllib.parse import parse_qs
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import RedirectResponse
from app.api.session import page
from app.core.session import current_user,current_page_user
from app.services.todos import list_private_todos,add_private_todo,update_private_todo,next_snooze,clock
from app.services.action_card_corrections import CorrectionNotFound,CorrectionConflict,CorrectionUnavailable

router=APIRouter()

def error(request,user,code,text):
    response=page(request,'action_card_error.html',user=user,title='待辦尚未更新',detail=text)
    response.status_code=code;return response

async def form(request,allowed):
    state=request.app.state
    if request.headers.get('origin') not in (None,state.oauth_settings.base_url.rstrip('/')) or request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'請從本站操作待辦。')
    if request.headers.get('content-type','').split(';')[0].strip()!='application/x-www-form-urlencoded':raise HTTPException(415,'請使用待辦表單。')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>4096:raise HTTPException(413,'表單過大。')
    try:
        text=raw.decode('ascii')
        if re.search(r'%(?![0-9a-fA-F]{2})',text):raise ValueError()
        values=parse_qs(text,keep_blank_values=True,max_num_fields=8,encoding='utf-8',errors='strict')
        if any(len(v)!=1 for v in values.values()) or set(values)-allowed:raise ValueError()
        values={k:v[0] for k,v in values.items()}
    except (ValueError,UnicodeError):raise HTTPException(422,'表單欄位不正確。') from None
    if not state.sessions.valid_csrf(request.cookies.get(state.sessions.cookie_name),values.get('csrf_token')):raise HTTPException(403,'驗證失敗，請重新整理頁面。')
    if not re.fullmatch(r'[0-9]{1,12}',values.get('expected_revision','')):raise HTTPException(422,'版本不正確。')
    return values

@router.get('/my/todos')
def private_todos(request:Request,user=Depends(current_page_user),view:str='active'):
    if view not in ('active','snoozed','done'):raise HTTPException(422,'未知的待辦狀態。')
    try:items=list_private_todos(request.app.state.database,user)
    except CorrectionNotFound:raise HTTPException(404,'找不到帳號。') from None
    except CorrectionUnavailable:return error(request,user,503,'待辦讀取失敗，請稍後重試；並非沒有待辦。')
    sessions=request.app.state.sessions
    return page(request,'private_todos.html',user=user,items=items,view=view,
        csrf=sessions.csrf(request.cookies.get(sessions.cookie_name)))

@router.post('/announcements/{announcement_id}/todos')
async def add(announcement_id:int,request:Request,user=Depends(current_user)):
    v=await form(request,{'csrf_token','expected_revision','baseline_hash','card_revision'})
    if not re.fullmatch(r'[0-9a-f]{64}',v.get('baseline_hash','')) or not re.fullmatch(r'[0-9]{1,12}',v.get('card_revision','')):raise HTTPException(422,'來源版本不正確。')
    try:add_private_todo(request.app.state.database,user,announcement_id,expected_revision=int(v['expected_revision']),baseline_hash=v['baseline_hash'],card_revision=int(v['card_revision']))
    except CorrectionNotFound:raise HTTPException(404,'找不到公告。') from None
    except CorrectionConflict:return error(request,user,409,'來源、修正或待辦版本已變更；本次未加入，請返回公告重新核對。')
    except CorrectionUnavailable:return error(request,user,503,'暫時無法確認加入結果，請重新讀取我的待辦後再試。')
    return RedirectResponse('/my/todos',status_code=303)

@router.post('/my/todos/{todo_id}')
async def change(todo_id:int,request:Request,user=Depends(current_user)):
    v=await form(request,{'csrf_token','expected_revision','operation','snooze_until'})
    if v.get('operation') not in ('complete','reopen','snooze','remove') or int(v['expected_revision'])<1:raise HTTPException(422,'待辦操作不正確。')
    if v['operation']=='snooze' and not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\+00:00)',v.get('snooze_until','')):raise HTTPException(422,'請重新讀取並確認稍後時間。')
    try:update_private_todo(request.app.state.database,user,todo_id,operation=v['operation'],expected_revision=int(v['expected_revision']),snooze_until=v.get('snooze_until'))
    except ValueError:raise HTTPException(422,'稍後時間不正確，請重新讀取。') from None
    except CorrectionNotFound:raise HTTPException(404,'找不到待辦。') from None
    except CorrectionConflict:return error(request,user,409,'待辦版本或顯示的稍後日期已變更，本次未覆寫；請重新讀取並確認時間。')
    except CorrectionUnavailable:return error(request,user,503,'暫時無法確認更新結果，請重新讀取我的待辦後再試。')
    return RedirectResponse('/my/todos',status_code=303)

@router.get('/todos')
def device_todos(request:Request):
    return page(request,'public_todos.html')
