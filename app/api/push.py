"""Anonymous device API. Never derives authority from Google sessions."""
from dataclasses import asdict
from datetime import datetime,timezone
import hmac,json,secrets
from uuid import UUID
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import Field,ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.push.contracts import PushModel,ReminderIntent
from app.push.models import PushReminder
from app.push.security import PushError,fingerprint
router=APIRouter()
COOKIE='nkust_push_device'
class SubscriptionBody(PushModel):subscription:dict
class SourceBody(PushModel):source_ref:str=Field(max_length=8192)
class IntentBody(PushModel):
    intent:ReminderIntent
    expected_revision:int|None=Field(default=None,strict=True,ge=0,le=2147483647)
class TestBody(PushModel):operation_id:UUID

def now():return datetime.now(timezone.utc)
def enabled(request):
    if not request.app.state.push_settings.enabled:raise HTTPException(404)
    return request.app.state.push_repo

def device(request):
    repo=enabled(request)
    return repo.authenticate(request.cookies.get(COOKIE),now())

async def body(request,model):
    origin=request.app.state.oauth_settings.base_url.rstrip('/')
    if request.headers.get('origin')!=origin:raise HTTPException(403,'PUSH_ORIGIN_REQUIRED')
    if request.headers.get('content-type','').split(';')[0]!='application/json':raise HTTPException(415,'PUSH_JSON_REQUIRED')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>16384:raise HTTPException(413,'PUSH_INPUT_TOO_LARGE')
    try:return model.model_validate_json(raw)
    except (ValidationError,ValueError):raise HTTPException(422,'PUSH_INPUT_INVALID') from None

def rate(request,scope,limit,identity=None):
    repo=enabled(request)
    peer=identity or (request.client.host if request.client else 'unknown')
    hour=now().strftime('%Y%m%d%H')
    # Never use arbitrary X-Forwarded-For or retain raw IP.
    key=scope+':'+hour+':'+fingerprint(repo.hash_key,peer)
    repo.consume_rate(key,limit,now())

@router.get('/api/push/config')
def config(request:Request):
    cfg=request.app.state.push_settings
    return {'enabled':cfg.enabled,'publicKey':cfg.vapid_public_key if cfg.enabled else None}

@router.post('/api/push/device')
async def register(request:Request):
    repo=enabled(request);data=await body(request,SubscriptionBody)
    old=request.cookies.get(COOKIE)
    if old:await run_in_threadpool(repo.authenticate,old,now())
    await run_in_threadpool(rate,request,'device-global',500,'global')
    await run_in_threadpool(rate,request,'device-peer',120)
    token=old or secrets.token_urlsafe(32)
    state=await run_in_threadpool(repo.register_device,token,data.subscription,now())
    response=JSONResponse(json.loads(json.dumps(asdict(state),default=str)))
    response.set_cookie(COOKIE,token,max_age=400*86400,path='/api/push',httponly=True,
        secure=request.app.state.oauth_settings.secure_cookie,samesite='strict')
    return response

@router.delete('/api/push/device')
async def disable(request:Request):
    repo=enabled(request);await body(request,PushModel)
    state=await run_in_threadpool(device,request)
    await run_in_threadpool(repo.disable,state.id,now())
    response=JSONResponse({'status':'disabled'})
    response.delete_cookie(COOKIE,path='/api/push',secure=request.app.state.oauth_settings.secure_cookie,httponly=True,samesite='strict')
    return response

@router.post('/api/push/source')
async def source(request:Request):
    repo=enabled(request);data=await body(request,SourceBody)
    from app.push.sources import resolve_public_ref
    def resolve():
        rate(request,'source-peer',120)
        with repo.db.transaction() as s:return asdict(resolve_public_ref(s,data.source_ref))
    return await run_in_threadpool(resolve)

@router.get('/api/push/reminders')
def reminders(request:Request):
    state=device(request);repo=enabled(request)
    with repo.db.transaction() as s:
        rows=s.scalars(select(PushReminder).where(PushReminder.device_id==str(state.id),PushReminder.source_ref!='__test__')).all()
        from app.push.repository import utc
        from app.push.sources import resolve_public_ref
        items=[]
        for row in rows:
            status=row.status
            if status in ('pending','retry'):
                try:
                    if resolve_public_ref(s,row.source_ref).version!=row.source_version:status='needs_review'
                except PushError:status='needs_review'
            items.append({'todo_id':row.todo_id,'source_ref':row.source_ref,'source_version':row.source_version,
                'server_revision':row.server_revision,'client_revision':row.client_revision,'status':status,
                'remind_at':utc(row.remind_at) if row.remind_at else None,'expires_at':utc(row.expires_at) if row.expires_at else None})
        return {'device':asdict(state),'items':items}


@router.put('/api/push/reminders/{todo_id}')
async def mutate(todo_id:UUID,request:Request):
    repo=enabled(request);data=await body(request,IntentBody)
    if todo_id!=data.intent.todo_id:raise HTTPException(422,'PUSH_TODO_MISMATCH')
    state=await run_in_threadpool(device,request)
    await run_in_threadpool(rate,request,'device-mutation',120,str(state.id))
    return asdict(await run_in_threadpool(repo.apply_intent,state.id,data.intent,data.expected_revision,now()))

@router.post('/api/push/test')
async def test_notification(request:Request):
    repo=enabled(request);data=await body(request,TestBody);state=await run_in_threadpool(device,request)
    await run_in_threadpool(repo.queue_test,state.id,data.operation_id,now())
    # Dispatcher is also lease-safe with cron. A busy runner leaves this durable test pending.
    await run_in_threadpool(request.app.state.push_runner)
    return JSONResponse({'status':'queued'},status_code=202)

@router.post('/internal/push/run')
async def trigger(request:Request):
    enabled(request);secret=request.app.state.push_settings.trigger_secret
    supplied=request.headers.get('authorization','')
    if not supplied.startswith('Bearer ') or len(supplied)>512 or not hmac.compare_digest(supplied[7:].encode(),secret.encode()):raise HTTPException(401,'PUSH_TRIGGER_UNAUTHORIZED')
    if request.url.query:raise HTTPException(422,'PUSH_TRIGGER_INPUT')
    async for chunk in request.stream():
        if chunk:raise HTTPException(422,'PUSH_TRIGGER_INPUT')
    return asdict(await run_in_threadpool(request.app.state.push_runner))

@router.post('/api/push/device/reset')
async def reset_cookie(request:Request):
    enabled(request);await body(request,PushModel)
    await run_in_threadpool(rate,request,'device-reset',30)
    # Only forget this cookie. Never authorize deletion/claim of the old device.
    response=JSONResponse({'status':'reset'})
    response.delete_cookie(COOKIE,path='/api/push',secure=request.app.state.oauth_settings.secure_cookie,httponly=True,samesite='strict')
    return response
