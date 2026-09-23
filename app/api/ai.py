"""User-triggered iAI analysis, sharing the Gmail mutation lock."""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.announcement import Announcement as A
from app.providers.base import AIError, AISetupRequired
from app.providers.iai import IAIProvider
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix='/api/ai', tags=['ai'])


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    limit: int = Field(default=5, ge=1, le=20)
    retry_failed: bool = False
    announcement_id: int | None = Field(default=None, ge=1)


@router.get('/status')
def status(request: Request):
    state = request.app.state
    configured = True
    try:
        IAIProvider(state.settings)  # Validate locally; do not call iAI on page load.
    except AISetupRequired:
        configured = False
    with Session(state.database.engine) as session:
        counts = dict(session.execute(select(A.analysis_status, func.count()).group_by(A.analysis_status)).all())
    return {'configured': configured, 'provider': state.settings.ai_provider,
            'model': state.settings.ai_model,
            'completed': counts.get('completed', 0), 'pending': counts.get('pending', 0),
            'failed': counts.get('failed', 0), 'busy': state.sync_lock.locked()}


@router.post('/analyze')
def analyze_batch(body: AnalyzeInput, request: Request):
    origin = request.headers.get('origin')
    if request.headers.get('x-requested-with') != 'NKUST-Dashboard' or (
        origin and origin != str(request.base_url).rstrip('/')):
        raise HTTPException(403, '請從本機 Dashboard 啟動分析。')
    state = request.app.state
    if not state.sync_lock.acquire(blocking=False):
        raise HTTPException(409, '已有同步或分析作業進行中，請稍候。')
    try:
        provider = state.ai_factory(state.settings)
        return asdict(AnalysisService(provider, state.database).run(body.limit, retry_failed=body.retry_failed,
                                                                  announcement_id=body.announcement_id))
    except AISetupRequired:
        raise HTTPException(503, '請先在本機 .env 設定 iAI 金鑰與模型，並重新啟動服務。') from None
    except AIError:
        raise HTTPException(502, 'iAI 連線或分析失敗，請檢查服務與額度後重試。') from None
    finally:
        state.sync_lock.release()
