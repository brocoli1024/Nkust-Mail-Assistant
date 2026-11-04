"""Fixed-purpose trigger and identity-bound owner controls."""
import hmac
from urllib.parse import parse_qs
from fastapi import APIRouter,Request,HTTPException,Depends
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.core.session import current_page_user
from app.api.session import page
from app.database.office_discovery import DiscoveryRepository
router=APIRouter()
def _owner(request,user):
 cfg=request.app.state.discovery_settings
 if not cfg.enabled:raise HTTPException(404)
 if user.google_user_id!=cfg.owner_sub:raise HTTPException(403,'此頁只供指定的公告來源管理者。')
 return cfg

def _status(result):
 if result.status=='busy':return 429 if result.error_code=='OFFICE_DISCOVERY_COOLDOWN' else 409
 if result.status=='failed' or result.status=='partial' and result.error_code!='OFFICE_DISCOVERY_PENDING':return 503
 return 200

@router.post('/internal/office-discovery/run')
async def trigger(request:Request):
 cfg=request.app.state.discovery_settings
 if not cfg.enabled:raise HTTPException(404)
 supplied=request.headers.get('authorization','')
 if not supplied.startswith('Bearer ') or len(supplied)>512 or not hmac.compare_digest(supplied[7:].encode(),cfg.trigger_secret.encode()):raise HTTPException(401,'OFFICE_DISCOVERY_UNAUTHORIZED')
 raw=bytearray()
 async for chunk in request.stream():
  raw.extend(chunk)
  if len(raw)>1024:raise HTTPException(413,'OFFICE_DISCOVERY_INPUT')
 if raw or request.url.query:raise HTTPException(422,'OFFICE_DISCOVERY_INPUT')
 result=await run_in_threadpool(request.app.state.discovery_runner)
 return JSONResponse(result.to_public_dict(),status_code=_status(result),headers={'Retry-After':'300'} if result.status=='busy' else None)

def _render(request,user,result=None):
 repo=DiscoveryRepository(request.app.state.database,user)
 from app.services.office_mail_views import _time
 state=repo.state();last_complete=_time(state.get('last_complete_scan_at'))
 return page(request,'office_discovery_settings.html',user=user,title='公務公告來源管理',state=state,last_complete=last_complete,counts=repo.counts(),rejections=repo.rejections(),result=result,csrf=request.app.state.sessions.csrf(request.cookies.get(request.app.state.sessions.cookie_name)))

@router.get('/settings/office-discovery')
def settings(request:Request,user=Depends(current_page_user)):
 _owner(request,user);return _render(request,user)

@router.post('/settings/office-discovery/run')
async def manual(request:Request,user=Depends(current_page_user)):
 _owner(request,user)
 if request.headers.get('origin') not in (None,request.app.state.oauth_settings.base_url.rstrip('/')) or request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403)
 if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':raise HTTPException(415)
 raw=bytearray()
 async for chunk in request.stream():
  raw.extend(chunk)
  if len(raw)>1024:raise HTTPException(413)
 try:
  fields=parse_qs(raw.decode('ascii'),keep_blank_values=True,max_num_fields=1)
  supplied=fields.get('csrf_token',[])
  if set(fields)!={'csrf_token'} or len(supplied)!=1:raise ValueError()
 except (ValueError,UnicodeError):raise HTTPException(422) from None
 if not request.app.state.sessions.valid_csrf(request.cookies.get(request.app.state.sessions.cookie_name),supplied[0]):raise HTTPException(403)
 result=await run_in_threadpool(request.app.state.discovery_runner)
 return await run_in_threadpool(_render,request,user,result)
