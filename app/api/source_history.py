"""GET-only source history; public routes never resolve a private session."""
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from app.api.session import page
from app.core.session import current_page_user
from app.services.source_views import public_history,private_history,private_version,related_sources
from app.services.action_card_corrections import CorrectionNotFound,CorrectionUnavailable
router=APIRouter()


def render(request,template,loader,*args,user=None):
    context={} if user is None else {'user':user}
    try:data=loader(request.app.state.database,*args)
    except CorrectionNotFound:raise HTTPException(404,'找不到來源紀錄。') from None
    except CorrectionUnavailable:
        response=page(request,'action_card_error.html',title='來源紀錄暫時無法讀取',detail='讀取失敗，並非沒有紀錄；請稍後重新整理。',**context)
        response.status_code=503;return response
    return page(request,template,data=data,**context)

@router.get('/public/announcements/{pid}/history')
def public(pid:int,request:Request,page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    return render(request,'source_history.html',public_history,pid,page_number)

@router.get('/announcements/{aid}/sources')
def sources(aid:int,request:Request,user=Depends(current_page_user),page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    return render(request,'source_group.html',related_sources,user,aid,page_number,user=user)

@router.get('/my/source-history')
def history(request:Request,user=Depends(current_page_user),page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    return render(request,'source_history.html',private_history,user,page_number,user=user)

@router.get('/my/source-history/{vid}')
def detail(vid:int,request:Request,user=Depends(current_page_user)):
    return render(request,'source_version_detail.html',private_version,user,vid,user=user)
