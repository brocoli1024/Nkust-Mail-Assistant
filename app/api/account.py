from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.api.auth import cookie_options
from app.api.session import page
from app.auth.attempts import COOKIE
from app.core.session import current_user
from app.database.user_mail import SyncBusy, SyncLeaseLost, UserAccountChanged
from app.services.account_service import delete_account

router = APIRouter()


@router.get('/privacy')
def privacy(request: Request):
    return page(request, 'privacy.html')


@router.post('/account/delete')
async def remove_account(request: Request, user=Depends(current_user)):
    state = request.app.state
    origin = request.headers.get('origin')
    if ((origin is not None and origin != state.oauth_settings.base_url.rstrip('/')) or
            request.headers.get('sec-fetch-site') == 'cross-site'):
        raise HTTPException(403, '請從本站刪除資料。')
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/x-www-form-urlencoded':
        raise HTTPException(415, '請使用帳號設定中的刪除表單。')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, '請求過大。')
    try:
        fields = parse_qs(raw.decode('ascii'), keep_blank_values=True, max_num_fields=3)
        if any(len(values) != 1 for values in fields.values()):
            raise ValueError()
        values = {key: values[0] for key, values in fields.items()}
    except (ValueError, UnicodeError):
        raise HTTPException(422, '刪除參數不正確。') from None
    sessions = state.sessions
    if not sessions.valid_csrf(request.cookies.get(sessions.cookie_name), values.pop('csrf_token', None)):
        raise HTTPException(403, '刪除驗證失敗，請重新整理頁面。')
    if values != {'confirm': 'DELETE'}:
        raise HTTPException(422, '請先確認刪除自己的資料。')
    # Run blocking token/network/database work in the worker pool, just as sync.
    from starlette.concurrency import run_in_threadpool
    try:
        disconnected = await run_in_threadpool(delete_account, state.database, state.tokens, user)
    except UserAccountChanged:
        raise HTTPException(401, '帳號已變更，請重新登入。') from None
    except (SyncBusy, SyncLeaseLost):
        response = page(request, 'account.html', user=user, title='帳號設定', settings=True,
                        csrf=sessions.csrf(request.cookies.get(sessions.cookie_name)),
                        account_error='同步仍在進行，請等同步結束後再刪除資料。')
        response.status_code = 409
        return response
    response = RedirectResponse('/login?deleted=1' + ('' if disconnected else '&disconnect=manual'), status_code=303)
    sessions.clear_cookie(response)
    response.delete_cookie(COOKIE, **cookie_options(state.oauth_settings))
    return response
