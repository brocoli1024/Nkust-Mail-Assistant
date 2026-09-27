"""Phase 2 authorization routes. No legacy data or logged-in session exposed."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.attempts import COOKIE, TTL_SECONDS
from app.auth.errors import AuthError

router = APIRouter()


def cookie_options(settings):
    return dict(httponly=True, secure=settings.secure_cookie, samesite='lax', path='/auth/google/callback')


@router.get('/login')
def login(request: Request):
    if getattr(request.app.state, 'sessions', None) is not None:
        from app.api.session import page
        sessions = request.app.state.sessions
        if sessions.resolve(request.cookies.get(sessions.cookie_name)):
            return RedirectResponse('/dashboard', status_code=303)
        response = page(request, 'login.html', logged_out=request.query_params.get('logged_out') == '1')
        sessions.clear_cookie(response)
        return response
    return RedirectResponse('/auth/google', status_code=303)


@router.get('/auth/google')
def authorize(request: Request):
    state = request.app.state
    value, browser, nonce, verifier = state.attempts.create()
    response = RedirectResponse(state.google.authorization_url(value, nonce, verifier), status_code=303)
    response.set_cookie(COOKIE, browser, max_age=TTL_SECONDS, **cookie_options(state.oauth_settings))
    return response


@router.get('/auth/google/callback')
def callback(request: Request):
    state = request.app.state
    try:
        params = request.query_params
        # Parse manually so FastAPI validation never echoes an authorization code.
        if any(len(params.getlist(k)) > 1 for k in ('state', 'code', 'error')):
            raise AuthError('OAUTH_CALLBACK_INVALID')
        context = state.attempts.consume(params.get('state'), request.cookies.get(COOKIE))
        if params.get('error'):
            raise AuthError('OAUTH_CANCELLED')
        code = params.get('code')
        if not code or len(code) > 4096:
            raise AuthError('OAUTH_CALLBACK_INVALID')
        tokens = state.google.exchange(code, context['verifier'])
        identity = state.google.verify_identity(tokens, context['nonce'])
        user_id = state.tokens.save_identity(identity, tokens)
        if getattr(state, 'sessions', None) is not None:
            value = state.sessions.create(user_id, request.cookies.get(state.sessions.cookie_name))
            response = RedirectResponse('/dashboard', status_code=303)
            state.sessions.set_cookie(response, value)
        else:
            # Explicit OAuth-only factory compatibility; never grants data access.
            response = RedirectResponse('/auth/complete', status_code=303)
    except AuthError as exc:
        response = JSONResponse({'error': str(exc), 'detail': '授權未完成，請重新開啟 /login。'}, status_code=400)
    response.delete_cookie(COOKIE, **cookie_options(state.oauth_settings))
    return response


@router.get('/auth/complete')
def complete(request: Request):
    if getattr(request.app.state, 'sessions', None) is not None:
        return RedirectResponse('/dashboard', status_code=303)
    # Static public notice, not proof that the requester is authenticated.
    return {'phase': 2, 'detail': 'OAuth 流程結束。此階段尚未建立網站登入 session；Dashboard 尚未開放。'}
