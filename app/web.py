"""New web entry point. Never mounts any unauthenticated legacy routes."""
from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.auth import router
from app.auth.attempts import OAuthAttempts
from app.auth.config import OAuthSettings
from app.auth.errors import AuthError
from app.auth.google_oauth import GoogleOAuth
from app.auth.token_service import TokenService
from app.config import Settings, ROOT
from app.core.session import SessionService, load_session_secret
from app.database.multi_user import MultiUserDatabase
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
               session_enabled=False, session_secret=None):
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
                if revision != '0005':
                    raise ValueError()
            except Exception:
                raise RuntimeError('Run alembic upgrade head on the NEW database before starting app.web') from None
            app.state.oauth_settings = oauth
            app.state.database = database
            app.state.google = google_factory(oauth)
            app.state.tokens = TokenService(database, oauth.encryption_key, app.state.google)
            app.state.gmail_for_user = UserGmailFactory(config, app.state.tokens)
            app.state.sync_service = UserSyncService(database, app.state.gmail_for_user)
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
        app.include_router(session_router)
        app.include_router(sync_router)
        app.include_router(announcements_router)
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
            sessions = request.app.state.sessions
            if sessions.resolve(request.cookies.get(sessions.cookie_name)):
                return RedirectResponse('/dashboard', status_code=303)
        return RedirectResponse('/login', status_code=303)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Framework defaults echo input values; keep arbitrary request data private.
        return JSONResponse({'error': 'INVALID_REQUEST', 'detail': '請求參數不正確，請檢查後重試。'}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({'error': 'DATABASE_UNAVAILABLE', 'detail': '請稍後重新開始登入。'}, status_code=503)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse({'error': str(exc)}, status_code=400)

    @app.middleware('http')
    async def safe_responses(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # Do not let the ASGI server log provider exceptions or SQL parameters.
            response = JSONResponse({'error': 'REQUEST_FAILED'}, status_code=500)
        response.headers['Cache-Control'] = 'no-store'
        # no-referrer makes browsers send Origin:null on HTML form POSTs,
        # which correctly fail our CSRF origin check. Account pages must retain
        # same-origin form metadata; OAuth URLs must never disclose their code.
        response.headers['Referrer-Policy'] = (
            'same-origin' if request.url.path in ('/dashboard', '/settings') else 'no-referrer'
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
