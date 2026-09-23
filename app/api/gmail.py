"""Explicit user-triggered sync. One sync at a time per local app instance."""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.gmail_service import GmailError, GmailService
from app.services.sync_service import SyncService

router = APIRouter(prefix='/api/gmail', tags=['gmail'])


class SyncInput(BaseModel):
    limit: int = Field(default=5, ge=1, le=100)


@router.post('/sync')
def sync(body: SyncInput, request: Request):
    # A custom header prevents another website from causing an unprompted local sync.
    origin = request.headers.get('origin')
    expected_origin = str(request.base_url).rstrip('/')
    if request.headers.get('x-requested-with') != 'NKUST-Dashboard' or (origin and origin != expected_origin):
        raise HTTPException(403, '請從本機 Dashboard 啟動同步。')
    state = request.app.state
    if not state.sync_lock.acquire(blocking=False):
        raise HTTPException(409, '已有同步或分析作業進行中，請稍候。')
    try:
        # Gmail connection is injected in tests; production uses the existing readonly service.
        gmail = state.gmail_factory(state.settings)
        return asdict(SyncService(gmail, state.database).sync(body.limit))
    except GmailError:
        raise HTTPException(502, 'Gmail 連線或授權失敗，請檢查網路及本機 OAuth 設定後重試。') from None
    finally:
        state.sync_lock.release()
