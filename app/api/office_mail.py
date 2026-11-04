"""Anonymous office mail pages: no user/session resolution or network fetch."""
from typing import Literal
from urllib.parse import urlencode
from fastapi import APIRouter,Request,Query,HTTPException
from app.api.session import page
from app.services.category_rules import CATEGORIES
from app.services.office_mail_briefs import CAMPUS_LABELS,parse_campuses
from app.services.office_mail_views import list_office_mail,office_mail_detail,office_mail_history
router=APIRouter()


def _filters(q,category,campus,mode,page_number):
    if category and category not in (*CATEGORIES,'未分類'):raise HTTPException(422,'未知的公告分類。')
    try:campuses=parse_campuses(campus)
    except ValueError:raise HTTPException(422,'未知或過多的校區設定。') from None
    return dict(q=q,category=category,campuses=campuses,mode=mode,page_number=page_number)


def _link(f,*,page_number=None,mode=None):
    pairs=[('q',f['q']),('category',f['category']),('mode',mode or f['mode']),('page',page_number or f['page_number'])]
    pairs.extend(('campus',c) for c in f['campuses'])
    return '/public/office-mail?'+urlencode(pairs)


@router.get('/public/office-mail')
def listing(request:Request,q:str=Query('',max_length=200),category:str='',campus:list[str]=Query(default=[]),
            mode:Literal['all','priority']='all',page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    f=_filters(q,category,campus,mode,page_number)
    data=list_office_mail(request.app.state.database,**f)
    query=_link(f).split('?',1)[1]
    for item in data['items']:item['detail_url']=f"/public/office-mail/{item['id']}?{query}"
    return page(request,'office_mail_list.html',**data,**f,discovery_enabled=request.app.state.discovery_settings.enabled,campus_labels=CAMPUS_LABELS,categories=CATEGORIES,
                previous=_link(f,page_number=page_number-1) if page_number>1 else None,
                following=_link(f,page_number=page_number+1) if page_number*20<data['total'] else None,
                all_url=_link(f,page_number=1,mode='all'),priority_url=_link(f,page_number=1,mode='priority'))


@router.get('/public/office-mail/{pid}')
def detail(pid:int,request:Request,q:str=Query('',max_length=200),category:str='',campus:list[str]=Query(default=[]),
           mode:Literal['all','priority']='all',page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    f=_filters(q,category,campus,mode,page_number)
    try:data=office_mail_detail(request.app.state.database,pid)
    except LookupError:raise HTTPException(404,'找不到公務公告。') from None
    return page(request,'office_mail_detail.html',**data,discovery_enabled=request.app.state.discovery_settings.enabled,back_url=_link(f)+f'#office-{pid}')


@router.get('/public/office-mail/{pid}/history')
def history(pid:int,request:Request,page_number:int=Query(1,alias='page',ge=1,le=1000000)):
    try:data=office_mail_history(request.app.state.database,pid,page_number=page_number)
    except LookupError:raise HTTPException(404,'找不到公務公告。') from None
    return page(request,'source_history.html',data=data,active_page='office')
