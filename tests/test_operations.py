import pytest

from app.container_start import configure_demo
from scripts.check_health import evaluate


def test_demo_rejects_external_database_and_real_credentials():
    env = {'DATABASE_URL': 'postgresql://someone:secret@production.invalid/live'}
    with pytest.raises(ValueError):
        configure_demo(env)
    env = {'DATABASE_URL': 'postgresql+psycopg://demo:synthetic@db:5432/nkust_demo',
           'GOOGLE_CLIENT_ID': 'real-credential'}
    configure_demo(env)
    assert env['GOOGLE_CLIENT_ID'] == 'synthetic-demo'
    assert env['GMAIL_TOKEN_PATH'] == '/nonexistent/token.json'
    assert len(env['MONITORING_TOKEN']) >= 32


def test_demo_defaults_to_ephemeral_sqlite():
    env = {}
    configure_demo(env)
    assert env['DATABASE_URL'] == 'sqlite:////app/data/demo.db'
    assert env['APP_BASE_URL'] == 'http://localhost'


@pytest.mark.parametrize('suffix', ['?host=production.invalid', '?dbname=live', '?user=real', '#fragment'])
def test_demo_rejects_database_option_overrides(suffix):
    with pytest.raises(ValueError):
        configure_demo({'DATABASE_URL': 'postgresql+psycopg://demo:synthetic@db:5432/nkust_demo' + suffix})


@pytest.mark.parametrize('age, expected', [(None, ['SYNC_NEVER_SUCCEEDED']), (10801, ['SYNC_STALE']), (10, [])])
def test_alert_freshness(age, expected):
    assert evaluate({'sync': {'age_seconds': age}, 'http': {'requests': 0, 'error_rate': 0}}, 10800) == expected


def test_alert_server_error_rate():
    assert evaluate({'sync': {'age_seconds': 1}, 'http': {'requests': 30, 'error_rate': 0.5}}, 10800) == ['HTTP_ERROR_RATE']
