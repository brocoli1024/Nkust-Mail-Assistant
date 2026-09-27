"""Only an explicit CSRF-protected request can start the current user's sync."""
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.session import page
from app.core.session import current_user
from app.database.user_mail import SyncBusy, SyncLeaseLost
from app.services.gmail_service import GmailError
from app.services.user_gmail_service import GmailReauthorizationRequired, GmailCredentialsUnavailable

router = APIRouter()


class SyncInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    limit: int = Field(default=5, ge=1, le=100)


async def sync_input(request: Request, user=Depends(current_user)):
    state = request.app.state
    origin = request.headers.get('origin')
    if ((origin is not None and origin != state.oauth_settings.base_url.rstrip('/')) or
            request.headers.get('sec-fetch-site') == 'cross-site'):
        raise HTTPException(403, '請從本站啟動同步。')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, '請求過大。')
    mime = request.headers.get('content-type', '').split(';')[0].strip()
    csrf = request.headers.get('x-csrf-token')
    try:
        if mime == 'application/json':
            values = json.loads(raw)
        elif mime == 'application/x-www-form-urlencoded':
            fields = parse_qs(raw.decode('ascii'), keep_blank_values=True, max_num_fields=4)
            if any(len(v) != 1 for v in fields.values()):
                raise ValueError()
            values = {k: v[0] for k, v in fields.items()}
            form_csrf = values.pop('csrf_token', None)
            csrf = csrf or form_csrf
            if 'limit' in values:
                if not values['limit'].isascii() or not values['limit'].isdigit():
                    raise ValueError()
                values['limit'] = int(values['limit'])
        else:
            raise HTTPException(415, '請使用 JSON 或表單。')
        payload = SyncInput.model_validate(values)
    except (ValueError, UnicodeError, ValidationError):
        raise HTTPException(422, '同步參數不正確；只能指定 1–100 封。') from None
    if not state.sessions.valid_csrf(request.cookies.get(state.sessions.cookie_name), csrf):
        raise HTTPException(403, '同步驗證失敗，請重新整理頁面。')
    return payload


@router.post('/sync')
def sync(request: Request, payload=Depends(sync_input), user=Depends(current_user)):
    result = None
    error = None
    status = 200
    try:
        result = request.app.state.sync_service.sync_gmail_for_user(user, payload.limit)
    except (SyncBusy, SyncLeaseLost):
        error, status = 'SYNC_BUSY', 409
    except GmailReauthorizationRequired:
        error, status = 'GMAIL_REAUTHORIZE', 401
    except GmailCredentialsUnavailable:
        error, status = 'GMAIL_CREDENTIALS_UNAVAILABLE', 503
    except GmailError:
        error, status = 'GMAIL_UNAVAILABLE', 502
    if request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded'):
        response = page(request, 'sync_result.html', result=result, error=error)
        response.status_code = status
        return response
    return JSONResponse(result if result is not None else {'error': error}, status_code=status)
