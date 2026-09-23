from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.models.announcement import Announcement as A
from app.models.scrape import Scrape
from app.providers.base import AIError
from app.services.scraper import ScrapeError
from app.services.scrape_service import ScrapeService
from app.services.analysis_service import AnalysisService
from test_analysis_service import setup as base_setup


@pytest.fixture
def setup(base_setup):
    db, _, _ = base_setup
    with db.transaction() as session:
        session.get(A, 1).url = 'https://officemail.nkust.edu.tw/Mail/View/1'
    return base_setup


def test_saved_content_cached_and_marks_pending(setup):
    db, provider, _ = setup
    AnalysisService(provider, db).run(1)
    scrape = Mock()
    scrape.scrape.return_value = '補充網頁內容，報名至115年10月08日截止。'
    service = ScrapeService(scrape, db)
    assert service.run(1)['changed']
    assert service.run(1)['status'] == 'cached'
    assert scrape.scrape.call_count == 1
    with Session(db.engine) as s:
        row = s.get(A, 1)
        assert row.analysis_status == 'pending' and row.summary == '測試摘要'
        assert row.scraped_text == scrape.scrape.return_value
        assert '補充網頁' not in row.original_text
        assert s.get(Scrape, 1).content_hash
    captured = []
    original = provider.generate
    def generate(system, payload, schema):
        captured.append(payload)
        return original(system, payload, schema)
    provider.generate = generate
    assert AnalysisService(provider, db).run(1).processed == 1
    assert captured[0]['supplemental_text'] == scrape.scrape.return_value


def test_refresh_failure_preserves_content(setup):
    db, _, _ = setup
    scrape = Mock()
    scrape.scrape.return_value = '先前成功的正文'
    service = ScrapeService(scrape, db)
    service.run(1)
    scrape.scrape.side_effect = ScrapeError('SCRAPE_CONNECTION_FAILED')
    assert service.run(1, refresh=True)['status'] == 'failed'
    with Session(db.engine) as s:
        assert s.get(A, 1).scraped_text == '先前成功的正文'
        assert s.get(Scrape, 1).fetched_at is not None


def test_concurrent_update_rejected(setup):
    db, _, _ = setup
    def fetch(url):
        with db.transaction() as s:
            s.get(A, 1).original_text = 'modified'
        return 'outdated webpage'
    with pytest.raises(ScrapeError, match='STALE'):
        ScrapeService(Mock(scrape=fetch), db).run(1)
    with Session(db.engine) as s:
        assert s.get(A, 1).scraped_text is None


def test_missing_url_does_not_fetch(setup):
    db, _, _ = setup
    with db.transaction() as s:
        s.get(A, 1).url = None
    scraper = Mock()
    with pytest.raises(ScrapeError, match='NO_URL'):
        ScrapeService(scraper, db).run(1)
    scraper.scrape.assert_not_called()


def test_new_content_invalidates_only_old_web_dates(setup):
    db, _, _ = setup
    with db.transaction() as s:
        row = s.get(A, 1)
        row.event_date = '2026-11-01'
        row.date_evidence = [*row.date_evidence, {'role': 'event_date', 'iso_date': '2026-11-01',
                                                'source_url': row.url, 'year_inferred': False}]
    ScrapeService(Mock(scrape=Mock(return_value='更新的網頁')), db).run(1)
    with Session(db.engine) as s:
        assert s.get(A, 1).event_date is None
        assert s.get(A, 1).deadline == '2026-10-08'
