from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.attempts import COOKIE
from app.api.auth import cookie_options
from app.config import ROOT
from app.core.session import current_user, current_page_user

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / 'app/templates/web')


def page(request, template, **context):
    return templates.TemplateResponse(request=request, name=template, context=context)


@router.get('/dashboard')
def dashboard(request: Request, user=Depends(current_page_user)):
    from app.api.user_announcements import dashboard_counts
    sessions = request.app.state.sessions
    return page(request, 'account.html', user=user, title='校園公告', settings=False,
                counts=dashboard_counts(request.app.state.database, user),
                csrf=sessions.csrf(request.cookies.get(sessions.cookie_name)))


@router.get('/settings')
def settings(request: Request, user=Depends(current_page_user)):
    sessions = request.app.state.sessions
    return page(request, 'account.html', user=user, title='帳號設定', settings=True,
                csrf=sessions.csrf(request.cookies.get(sessions.cookie_name)))


@router.get('/api/me')
def me(user=Depends(current_user)):
    return {'id': user.id, 'email': user.email, 'display_name': user.display_name}


@router.post('/logout')
async def logout(request: Request, user=Depends(current_user)):
    sessions = request.app.state.sessions
    value = request.cookies.get(sessions.cookie_name)
    origin = request.headers.get('origin')
    expected = request.app.state.oauth_settings.base_url.rstrip('/')
    if (origin is not None and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '請從本站登出。')
    supplied = request.headers.get('x-csrf-token')
    if supplied is None:
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/x-www-form-urlencoded':
            raise HTTPException(403, '登出驗證失敗，請重新整理頁面。')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, '請求過大。')
        try:
            values = parse_qs(body.decode('ascii'), max_num_fields=4).get('csrf_token', [])
            supplied = values[0] if len(values) == 1 else None
        except (ValueError, UnicodeError):
            supplied = None
    if not sessions.valid_csrf(value, supplied):
        raise HTTPException(403, '登出驗證失敗，請重新整理頁面。')
    sessions.revoke(value)
    response = RedirectResponse('/login?logged_out=1', status_code=303)
    sessions.clear_cookie(response)
    response.delete_cookie(COOKIE, **cookie_options(request.app.state.oauth_settings))
    return response
