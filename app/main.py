"""Local-only FastAPI dashboard. Start with uvicorn app.main:app --host 127.0.0.1."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import announcements, gmail, ai, scrape
from app.config import Settings
from app.database.database import Database
from app.services.gmail_service import GmailService
from app.providers.iai import IAIProvider
from app.services.scraper import Scraper

APP_DIR = Path(__file__).resolve().parent


def create_app(settings=None, *, gmail_factory=GmailService.connect, ai_factory=IAIProvider, scraper_factory=Scraper, now=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.load()
        app.state.database = Database(app.state.settings.database_path)
        app.state.gmail_factory = gmail_factory
        app.state.ai_factory = ai_factory
        app.state.scraper_factory = scraper_factory
        app.state.now = now or (lambda: datetime.now(timezone.utc))
        app.state.sync_lock = Lock()
        try:
            yield
        finally:
            app.state.database.close()

    application = FastAPI(title='NKUST 校園郵件助手', lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    application.include_router(announcements.router)
    application.include_router(gmail.router)
    application.include_router(ai.router)
    application.include_router(scrape.router)
    application.mount('/static', StaticFiles(directory=APP_DIR / 'static'), name='static')

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        return JSONResponse(status_code=503, content={'detail': '資料庫暫時無法存取，請稍後重試。'})

    @application.middleware('http')
    async def local_headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path == '/':
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @application.get('/', include_in_schema=False)
    def index():
        return FileResponse(APP_DIR / 'templates/index.html')

    return application


app = create_app()
