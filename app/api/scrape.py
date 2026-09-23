from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services.scraper import ScrapeError
from app.services.scrape_service import ScrapeService

router = APIRouter(prefix='/api/announcements', tags=['scrape'])

ERRORS = {
    'SCRAPE_URL_BLOCKED': '此網址不在允許擷取的網站清單中。',
    'SCRAPE_ADDRESS_BLOCKED': '目的位址不允許擷取。',
    'SCRAPE_NO_URL': '這則公告沒有可擷取的網址。',
    'SCRAPE_NOT_FOUND': '找不到這則公告。',
    'SCRAPE_LOGIN_REQUIRED': '網頁需要登入，請自行開啟公告查看。',
    'SCRAPE_ACCESS_DENIED': '網站拒絕存取，請自行開啟公告查看。',
    'SCRAPE_CONTENT_NOT_FOUND': '找不到公告正文，此網頁版型尚不支援。',
    'SCRAPE_CONTENT_TOO_SHORT': '網頁內容不足，未視為成功。',
    'SCRAPE_CONTENT_TOO_LONG': '正文超過處理上限，請直接查看公告。',
    'SCRAPE_HTML_REQUIRED': '此連結不是 HTML 網頁，暫不處理 PDF 或附件。',
    'SCRAPE_REDIRECT_BLOCKED': '網頁轉址異常或超過次數限制。',
    'SCRAPE_TLS_ERROR': '網站憑證驗證失敗，未下載內容。',
    'SCRAPE_PAGE_TOO_LARGE': '網頁超過下載大小限制。',
    'SCRAPE_STALE': '公告已變更，請重新開啟後再試。',
}


class ScrapeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    refresh: bool = False


@router.post('/{announcement_id}/scrape')
def scrape(announcement_id: int, body: ScrapeInput, request: Request):
    origin = request.headers.get('origin')
    if request.headers.get('x-requested-with') != 'NKUST-Dashboard' or (origin and origin != str(request.base_url).rstrip('/')):
        raise HTTPException(403, '請從本機 Dashboard 啟動擷取。')
    state = request.app.state
    if not state.sync_lock.acquire(blocking=False):
        raise HTTPException(409, '已有同步、分析或擷取進行中，請稍候。')
    try:
        result = ScrapeService(state.scraper_factory(state.settings), state.database).run(announcement_id, refresh=body.refresh)
        if result.get('error'):
            result['message'] = ERRORS.get(result['error'], '網頁連線失敗或暫時無法使用，請稍後重試。')
        return result
    except ScrapeError as exc:
        raise HTTPException(404 if str(exc) == 'SCRAPE_NOT_FOUND' else 409,
                            ERRORS.get(str(exc), '無法擷取此公告。')) from None
    finally:
        state.sync_lock.release()
