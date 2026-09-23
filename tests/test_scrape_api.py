from unittest.mock import Mock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models.announcement import Announcement as A
from test_api import populate
from test_analysis_service import FakeProvider


def test_user_triggered_scrape_then_targeted_analysis(tmp_path):
    scraper = Mock()
    scraper.scrape.return_value = '活動補充內容：測試公告歡迎同學參加。報名至115年10月08日截止。'
    provider = FakeProvider()
    app = create_app(Settings(database_path=tmp_path / 'test.db'),
                     scraper_factory=lambda _: scraper, ai_factory=lambda _: provider)
    headers = {'X-Requested-With': 'NKUST-Dashboard'}
    with TestClient(app) as client:
        populate(app)
        with app.state.database.transaction() as s:
            s.get(A, 1).url = 'https://officemail.nkust.edu.tw/Mail/View/1'
        assert client.post('/api/announcements/1/scrape', json={}).status_code == 403
        with app.state.sync_lock:
            assert client.post('/api/announcements/1/scrape', json={}, headers=headers).status_code == 409
        assert client.get('/api/announcements/1').json()['web'] is None
        scraper.scrape.assert_not_called()
        assert client.post('/api/announcements/1/scrape', json={}, headers=headers).json()['changed']
        assert client.get('/api/announcements/1').json()['web']['text'] == scraper.scrape.return_value
        assert provider.calls == 0
        result = client.post('/api/ai/analyze', json={'announcement_id': 1}, headers=headers).json()
        assert result['processed'] == 1 and provider.calls == 1
        assert client.get('/api/announcements/1').json()['analysis']['result']['used_web_content']
        assert client.post('/api/announcements/9999/scrape', json={}, headers=headers).status_code == 404
