from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models.announcement import Announcement
from app.services.announcement_parser import parse_email
from app.services.email_parser import DecodedEmail
from app.services.gmail_service import GmailError

NOW = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)
HEADERS = {'X-Requested-With': 'NKUST-Dashboard'}


def mail(mid='sample', received=None):
    return DecodedEmail(mid, 'sender@example.invalid', 'sample', received or NOW,
        (Path(__file__).parent / 'fixtures/nkust_mail_sample.html').read_text(encoding='utf-8'), None)


@pytest.fixture
def setup(tmp_path):
    gmail = Mock()
    gmail.list_message_ids.return_value = ['sample']
    gmail.read_message.side_effect = mail
    app = create_app(Settings(database_path=tmp_path / 'api.db'), gmail_factory=lambda _: gmail, now=lambda: NOW)
    with TestClient(app) as client:
        yield client, app, gmail


def populate(app, email=None):
    email = email or mail()
    app.state.database.save_processed(email, parse_email(email), 'nkust-table-v1')


def test_empty_dashboard_and_assets(setup):
    client, app, gmail = setup
    assert client.get('/').status_code == 200
    assert client.get('/static/css/dashboard.css').status_code == 200
    assert client.get('/api/summary').json()['total'] == 0
    assert client.get('/api/announcements').json()['items'] == []
    gmail.read_message.assert_not_called()


def test_queries_pagination_details(setup):
    client, app, _ = setup
    populate(app)
    page = client.get('/api/announcements?page_size=2').json()
    assert page['total'] == 3 and len(page['items']) == 2
    assert len(client.get('/api/announcements?page_size=2&page=2').json()['items']) == 1
    assert client.get('/api/announcements?category=獎學金').json()['total'] == 1
    assert client.get('/api/announcements?q=校友').json()['total'] == 1
    assert client.get('/api/announcements?q=%25').json()['total'] == 0
    assert client.get('/api/announcements?view=jobs').json()['total'] == 1
    detail = client.get('/api/announcements/' + str(page['items'][0]['id'])).json()
    assert detail['original_text'] and detail['date_evidence']
    assert 'original_html' not in detail
    assert client.get('/api/announcements/9999').status_code == 404


def test_taipei_day_and_deadline_boundaries(setup):
    client, app, _ = setup
    populate(app, mail('a', datetime(2026, 10, 7, 16, tzinfo=timezone.utc)))
    populate(app, mail('b', datetime(2026, 10, 7, 15, 59, tzinfo=timezone.utc)))
    populate(app, mail('c', datetime(2026, 10, 8, 16, tzinfo=timezone.utc)))
    with Session(app.state.database.engine) as session, session.begin():
        rows = session.scalars(select(Announcement).order_by(Announcement.id)).all()
        for row in rows:
            row.deadline = None
        rows[0].deadline = '2026-10-07'
        rows[1].deadline = '2026-10-08'
        rows[2].deadline = '2026-10-14'
        rows[3].deadline = '2026-10-15'
        rows[0].requires_action = True
    summary = client.get('/api/summary').json()
    assert summary['today_received'] == 3
    assert summary['upcoming_deadlines'] == 2
    assert summary['requires_action'] == 1
    assert summary['action_unknown'] == 8
    assert client.get('/api/announcements?view=deadline').json()['total'] == 2
    assert client.get('/api/announcements?view=action').json()['total'] == 1


@pytest.mark.parametrize('query', ['page=0', 'page_size=101', 'view=invalid', 'category=invalid'])
def test_query_validation(setup, query):
    assert setup[0].get('/api/announcements?' + query).status_code == 422


def test_sync_endpoint_is_idempotent(setup):
    client, app, gmail = setup
    first = client.post('/api/gmail/sync', json={'limit': 5}, headers=HEADERS)
    assert first.status_code == 200
    assert first.json()['processed'] == 1
    second = client.post('/api/gmail/sync', json={'limit': 5}, headers=HEADERS)
    assert second.json()['skipped'] == 1
    assert second.json()['database_counts']['announcements'] == 3


def test_sync_busy_errors_and_recovery(setup):
    client, app, gmail = setup
    app.state.sync_lock.acquire()
    try:
        assert client.post('/api/gmail/sync', json={}, headers=HEADERS).status_code == 409
    finally:
        app.state.sync_lock.release()
    gmail.list_message_ids.side_effect = GmailError('private response')
    response = client.post('/api/gmail/sync', json={}, headers=HEADERS)
    assert response.status_code == 502 and 'private' not in response.text
    gmail.list_message_ids.side_effect = None
    assert client.post('/api/gmail/sync', json={}, headers=HEADERS).status_code == 200


def test_sync_partial_failure_and_origin_check(setup):
    client, app, gmail = setup
    gmail.read_message.side_effect = GmailError('GMAIL_REQUEST_FAILED')
    response = client.post('/api/gmail/sync', json={}, headers=HEADERS)
    assert response.json()['failed'] == 1
    assert client.post('/api/gmail/sync', json={}).status_code == 403
    assert client.post('/api/gmail/sync', json={}, headers={**HEADERS, 'Origin': 'https://example.invalid'}).status_code == 403
    assert client.post('/api/gmail/sync', json={'limit': 101}, headers=HEADERS).status_code == 422


def test_unclassified_keyword_filter_does_not_overwrite_category(setup):
    client, app, _ = setup
    populate(app)
    with Session(app.state.database.engine) as session, session.begin():
        row = session.scalar(select(Announcement).where(Announcement.source_index == 2))
        row.category = None
        row.source_category = '競賽通知'
        row.title = 'AI 創意挑戰'
    result = client.get('/api/announcements?category=競賽').json()
    assert result['total'] == 1
    assert result['items'][0]['category'] is None
    assert client.get('/api/announcements?view=tech').json()['total'] == 1
