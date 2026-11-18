import json
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError
from tests.test_sessions import web
from tests.test_auth import oauth
from app.models.public_announcements import PublicSourceState, PublicSyncRun


def test_health_disconnect_and_recovery(web, monkeypatch):
    client, app, _, _ = web
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    with monkeypatch.context() as patch:
        def fail():
            raise OperationalError('PRIVATE-URL', {}, Exception('PRIVATE-PASSWORD'))
        patch.setattr(app.state.health_engine, 'connect', fail)
        response = client.get('/health/ready')
        assert response.status_code == 503
        assert 'PRIVATE' not in response.text
        assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200


def test_metrics_are_private_and_aggregate(web, monkeypatch):
    client, app, _, _ = web
    monkeypatch.delenv('MONITORING_TOKEN', raising=False)
    assert client.get('/health/status').status_code == 404
    monkeypatch.setenv('MONITORING_TOKEN', 'synthetic-monitoring-token-at-least-32')
    assert client.get('/health/status').status_code == 401
    now = datetime.now(timezone.utc)
    with app.state.database.transaction() as session:
        session.add(PublicSourceState(source_key='nkust-latest', last_success_at=now))
        session.add(PublicSyncRun(source_key='nkust-latest', mode='recent', status='failed', started_at=now, finished_at=now))
    headers = {'Authorization': 'Bearer synthetic-monitoring-token-at-least-32'}
    data = client.get('/health/status', headers=headers).json()
    assert data['sync']['runs']['failed'] == 1
    assert data['sync']['last_success_at']
    assert data['http']['requests'] >= 1


def test_request_logs_never_include_untrusted_values(web, caplog):
    client, _, _, _ = web
    with caplog.at_level(logging.INFO, logger='nkust.operations'):
        client.get('/unknown-PRIVATE-PATH?code=PRIVATE-CODE', headers={'Authorization': 'Bearer PRIVATE-TOKEN'})
    records = [json.loads(r.message) for r in caplog.records if r.name == 'nkust.operations']
    request = next(r for r in records if r['event'] == 'http_request')
    assert request['route'] == 'unmatched'
    assert request['status'] == 404
    assert 'PRIVATE' not in json.dumps(records)


def test_demo_disables_real_accounts(web, monkeypatch):
    client, _, _, _ = web
    monkeypatch.setenv('DEMO_MODE', '1')
    for path in ('/auth/google', '/auth/google/callback', '/sync', '/api/me'):
        assert client.get(path).status_code == 403
    assert client.get('/demo').status_code == 200
