import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import AISetupRequired
from test_analysis_service import FakeProvider
from test_api import populate

HEADERS = {'X-Requested-With': 'NKUST-Dashboard'}


@pytest.fixture
def setup(tmp_path):
    provider = FakeProvider()
    settings = Settings(database_path=tmp_path / 'api.db', ai_api_key='never-return-this', ai_model='test-model')
    app = create_app(settings, ai_factory=lambda _: provider)
    with TestClient(app) as client:
        populate(app)
        yield client, app, provider


def test_status_is_local_and_never_exposes_key(setup):
    client, _, provider = setup
    response = client.get('/api/ai/status')
    assert response.json()['configured'] is True
    assert response.json()['pending'] == 3
    assert 'never-return-this' not in response.text
    assert provider.calls == 0


def test_batch_detail_and_repeat(setup):
    client, _, provider = setup
    response = client.post('/api/ai/analyze', json={'limit': 1}, headers=HEADERS)
    assert response.status_code == 200 and response.json()['processed'] == 1
    detail = client.get('/api/announcements/1').json()
    assert detail['summary'] == '測試摘要'
    assert detail['analysis']['result_model'] == 'test-model'
    assert detail['original_text'] and detail['date_evidence']
    assert client.post('/api/ai/analyze', json={}, headers=HEADERS).json()['processed'] == 2
    assert client.post('/api/ai/analyze', json={}, headers=HEADERS).json()['processed'] == 0
    assert provider.calls == 3


def test_cross_origin_and_lock(setup):
    client, app, provider = setup
    assert client.post('/api/ai/analyze', json={}).status_code == 403
    assert client.post('/api/ai/analyze', json={}, headers=HEADERS | {'Origin': 'https://example.invalid'}).status_code == 403
    with app.state.sync_lock:
        assert client.post('/api/ai/analyze', json={}, headers=HEADERS).status_code == 409
    assert provider.calls == 0


@pytest.mark.parametrize('body', [{'limit': 21}, {'limit': 0}, {'limit': '5'}, {'retry_failed': 'yes'}])
def test_input_validation(setup, body):
    client, _, provider = setup
    assert client.post('/api/ai/analyze', json=body, headers=HEADERS).status_code == 422
    assert provider.calls == 0


def test_missing_key_releases_lock(setup):
    client, app, provider = setup
    def unavailable(_):
        raise AISetupRequired('AI_KEY_MISSING')
    app.state.ai_factory = unavailable
    assert client.post('/api/ai/analyze', json={}, headers=HEADERS).status_code == 503
    assert not app.state.sync_lock.locked()
    assert provider.calls == 0


def test_failed_batch_and_retry(setup):
    client, _, provider = setup
    provider.error = 'AI_TIMEOUT: secret-test-body'
    result = client.post('/api/ai/analyze', json={}, headers=HEADERS).json()
    assert result['failed'] == 1
    detail = client.get('/api/announcements/1')
    assert detail.json()['analysis']['error'] == 'AI_TIMEOUT'
    assert 'secret-test-body' not in detail.text
    provider.error = None
    assert client.post('/api/ai/analyze', json={'retry_failed': True}, headers=HEADERS).json()['processed'] == 1
