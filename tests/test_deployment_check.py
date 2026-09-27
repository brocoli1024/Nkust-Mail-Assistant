from dataclasses import replace

from app.config import Settings
from app.deployment_check import check_settings, check_database
from tests.test_auth import oauth
from tests.test_multi_user_database import database


def test_production_settings(oauth):
    production = replace(oauth, base_url='https://mail.example.invalid',
                         redirect_uri='https://mail.example.invalid/auth/google/callback')
    settings = Settings(database_url='postgresql+psycopg://test:unused@localhost/test')
    assert check_settings(settings, production, 's' * 40) == []


def test_local_configuration_is_not_production(oauth):
    errors = check_settings(Settings(database_url='sqlite:///:memory:'), oauth, '')
    assert set(errors) == {'PUBLIC_HTTPS_REQUIRED', 'POSTGRESQL_REQUIRED', 'SESSION_SECRET_INVALID'}


def test_bad_credentials_are_not_returned(oauth):
    broken = replace(oauth, encryption_key='PRIVATE-MARKER')
    errors = check_settings(Settings(database_url='invalid'), broken, 's' * 40)
    assert 'OAUTH_SETTINGS_INVALID' in errors and 'DATABASE_URL_INVALID' in errors
    assert 'PRIVATE-MARKER' not in repr(errors)


def test_database_check_reads_migration(database):
    db, _ = database
    assert check_database(Settings(database_url=db.engine.url)) == []


def test_database_check_failure_is_sanitized(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE-MARKER')
    monkeypatch.setattr('app.deployment_check.MultiUserDatabase', fail)
    assert check_database(Settings()) == ['DATABASE_CHECK_FAILED']
