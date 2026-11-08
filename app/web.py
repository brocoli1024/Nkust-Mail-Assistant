"""New web entry point. Never mounts any unauthenticated legacy routes."""
from contextlib import asynccontextmanager
import logging
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router
from app.auth.attempts import OAuthAttempts
from app.auth.config import OAuthSettings
from app.auth.errors import AuthError
from app.auth.google_oauth import GoogleOAuth
from app.auth.token_service import TokenService
from app.config import Settings, ROOT
from app.core.session import SessionService, load_session_secret
from app.database.multi_user import MultiUserDatabase
from app.database.schema import REQUIRED_REVISION
from app.services.user_gmail_service import UserGmailFactory
from app.services.user_sync_service import UserSyncService


class RedactQuery(logging.Filter):
    """Uvicorn normally logs the entire callback URL, including the code."""
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str):
                args[2] = args[2].split('?', 1)[0]
            record.args = tuple(args)
        return True


def create_app(settings=None, oauth_settings=None, *, google_factory=GoogleOAuth,
               session_enabled=False, session_secret=None, demo_enabled=False, discovery_settings=None, push_settings=None):
    """OAuth-only default preserves Phase 2 callers; app below enables sessions."""
    @asynccontextmanager
    async def lifespan(app):
        config = settings or Settings.load()
        oauth = (oauth_settings or OAuthSettings.load()).validate()
        database = MultiUserDatabase(config.database_url, legacy_path=config.database_path)
        try:
            try:
                with database.engine.connect() as connection:
                    revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
                if revision != REQUIRED_REVISION:
                    raise ValueError()
            except Exception:
                raise RuntimeError('Run alembic upgrade head on the NEW database before starting app.web') from None
            app.state.oauth_settings = oauth
            app.state.database = database
            app.state.google = google_factory(oauth)
            app.state.tokens = TokenService(database, oauth.encryption_key, app.state.google)
            app.state.gmail_for_user = UserGmailFactory(config, app.state.tokens)
            app.state.sync_service = UserSyncService(database, app.state.gmail_for_user)
            from app.core.office_discovery import DiscoverySettings
            from app.services.office_mail_discovery import run_office_discovery
            app.state.discovery_settings = discovery_settings or DiscoverySettings.load()
            app.state.discovery_runner = lambda: run_office_discovery(database, app.state.discovery_settings, app.state.gmail_for_user)
            from app.push.config import PushSettings
            from app.push.security import PushCipher
            from app.push.repository import PushRepository
            from app.push.transport import PushSender
            from app.push.dispatcher import run_due
            from datetime import datetime, timezone
            app.state.push_settings = (push_settings or PushSettings.from_env()).validate()
            push_cipher = PushCipher(oauth.encryption_key)
            app.state.push_repo = PushRepository(database, push_cipher, app.state.push_settings.rate_hash_key.encode(), app.state.push_settings)
            push_sender = PushSender(app.state.push_settings, push_cipher)
            app.state.push_runner = lambda: run_due(database, push_sender, datetime.now(timezone.utc))
            app.state.attempts = OAuthAttempts(database, app.state.tokens)
            if session_enabled:
                app.state.sessions = SessionService(database,
                    load_session_secret() if session_secret is None else session_secret,
                    secure=oauth.secure_cookie)
            yield
        finally:
            database.close()

    app = FastAPI(title='NKUST Web OAuth', lifespan=lifespan, debug=False,
                  docs_url=None, redoc_url=None, openapi_url=None)
    # Resolve allowed host at construction without reading or emitting secrets.
    configured = oauth_settings or OAuthSettings.load()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(configured.base_url).hostname or 'localhost'])
    app.include_router(router)
    if session_enabled:
        from app.api.session import router as session_router
        from app.api.sync import router as sync_router
        from app.api.user_announcements import router as announcements_router
        from app.api.account import router as account_router
        app.include_router(session_router)
        app.include_router(sync_router)
        app.include_router(announcements_router)
        app.include_router(account_router)
        from app.api.public_announcements import router as public_router
        from app.api.demo import router as demo_router
        app.include_router(public_router)
        from app.api.office_mail import router as office_router
        app.include_router(office_router)
        from app.api.office_discovery import router as discovery_router
        app.include_router(discovery_router)
        from app.api.push import router as push_router
        app.include_router(push_router)
        if demo_enabled:
            app.include_router(demo_router)
        else:
            @app.get('/demo')
            @app.get('/demo/announcements/{demo_id}')
            def legacy_demo_redirect(demo_id: str = ''):
                return RedirectResponse('/public/announcements',status_code=303)
        from app.api.action_card_corrections import router as correction_router
        app.include_router(correction_router)
        from app.api.todos import router as todo_router
        app.include_router(todo_router)
        from app.api.source_history import router as source_history_router
        app.include_router(source_history_router)
        app.mount('/assets', StaticFiles(directory=ROOT / 'app/static/web'), name='web-assets')

        @app.get('/manifest.webmanifest', include_in_schema=False)
        def web_manifest():
            return FileResponse(ROOT / 'app/static/web/manifest.webmanifest',
                                media_type='application/manifest+json')

        @app.get('/sw.js', include_in_schema=False)
        def service_worker():
            return FileResponse(ROOT / 'app/static/web/sw.js', media_type='application/javascript')

        @app.get('/offline', include_in_schema=False)
        def offline_notice():
            return FileResponse(ROOT / 'app/static/web/offline.html', media_type='text/html')

    @app.get('/')
    def root(request: Request):
        if session_enabled:
            target='/public/announcements'
            if request.url.query:target+='?'+request.url.query
            return RedirectResponse(target,status_code=303)
        return RedirectResponse('/login', status_code=303)

    def is_public_page(request):
        path = request.url.path
        return session_enabled and request.method == 'GET' and (
            path in ('/', '/public/announcements', '/public/office-mail', '/demo', '/todos')
            or path.startswith('/public/office-mail/')
            or path.startswith('/public/announcements/')
            or path.startswith('/demo/announcements/'))

    def public_error(request, status_code):
        from app.api.session import page
        demo = request.url.path == '/demo' or request.url.path.startswith('/demo/')
        messages = {
            404: ('找不到這則公告', '公告可能不存在，請返回清單重新選擇。'),
            422: ('請檢查搜尋與篩選條件', '請回到清單，縮短關鍵字或重新選擇分類。'),
            503: ('暫時無法讀取公告', '目前無法連接資料服務，請稍後重試；現有資料不會因此清除。'),
            500: ('暫時無法顯示這個頁面', '請稍後重試，或返回公告清單。'),
        }
        title, detail = messages[status_code]
        office=request.url.path=='/public/office-mail' or request.url.path.startswith('/public/office-mail/')
        return_url='/demo' if demo else '/public/office-mail' if office else '/public/announcements'
        if status_code >= 500:
            # Relative origin-local URL; encode decoded path delimiters and backslashes.
            from urllib.parse import quote
            path=quote(request.url.path,safe='/')
            if path.startswith('/') and not path.startswith('//'):
                return_url=path+('?' + request.url.query if request.url.query else '')
        response = page(request, 'public_error.html', title=title, detail=detail,
                        demo=demo, office=office, return_url=return_url,
                        retry=status_code >= 500)
        response.status_code = status_code
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        if is_public_page(request) and exc.status_code in (404, 422):
            return public_error(request, exc.status_code)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Framework defaults echo input values; keep arbitrary request data private.
        if is_public_page(request):
            return public_error(request, 422)
        return JSONResponse({'error': 'INVALID_REQUEST', 'detail': '請求參數不正確，請檢查後重試。'}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        if is_public_page(request):
            return public_error(request, 503)
        return JSONResponse({'error': 'DATABASE_UNAVAILABLE', 'detail': '請稍後重新開始登入。'}, status_code=503)

    from app.push.security import PushError
    @app.exception_handler(PushError)
    async def push_error(request, exc):
        code = str(exc)
        status = 401 if code == 'PUSH_DEVICE_UNAUTHORIZED' else 429 if code in ('PUSH_RATE_LIMITED','PUSH_CAPACITY_REACHED') else 409 if code in ('PUSH_REVISION_CONFLICT','PUSH_OPERATION_CONFLICT','PUSH_SOURCE_CHANGED','PUSH_SUBSCRIPTION_IN_USE') else 422
        return JSONResponse({'error':code}, status_code=status)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse({'error': str(exc)}, status_code=400)

    @app.middleware('http')
    async def safe_responses(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # Do not let the ASGI server log provider exceptions or SQL parameters.
            response = (public_error(request, 500) if is_public_page(request)
                        else JSONResponse({'error': 'REQUEST_FAILED'}, status_code=500))
        response.headers['Cache-Control'] = 'no-store'
        # no-referrer makes browsers send Origin:null on HTML form POSTs,
        # which correctly fail our CSRF origin check. Account pages must retain
        # same-origin form metadata; OAuth URLs must never disclose their code.
        response.headers['Referrer-Policy'] = (
            'same-origin' if (request.url.path.startswith(('/public/','/api/push','/settings/office-discovery')) or request.url.path == '/todos' or request.url.path in ('/dashboard', '/settings', '/account/delete', '/my/todos') or re.fullmatch(r'/my/todos/[0-9]+', request.url.path) or re.fullmatch(r'/announcements/[0-9]+(?:/action-card/corrections|/todos)?', request.url.path)) else 'no-referrer'
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; "
            "manifest-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    access_logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, RedactQuery) for f in access_logger.filters):
        access_logger.addFilter(RedactQuery())
    return app


app = create_app(session_enabled=True)
