"""Read-only production preflight: python -m app.deployment_check."""
from urllib.parse import urlsplit

from sqlalchemy import text

from app.auth.config import OAuthSettings
from app.config import Settings
from app.core.session import load_session_secret
from app.database.multi_user import MultiUserDatabase, validate_database_url


def check_settings(settings, oauth, session_secret):
    errors = []
    try:
        oauth.validate()
    except Exception:
        errors.append('OAUTH_SETTINGS_INVALID')
    try:
        parsed = urlsplit(oauth.base_url)
        if parsed.scheme != 'https' or parsed.hostname in ('localhost', '127.0.0.1', '::1'):
            errors.append('PUBLIC_HTTPS_REQUIRED')
    except ValueError:
        errors.append('PUBLIC_HTTPS_REQUIRED')
    if not isinstance(session_secret, str) or len(session_secret.encode()) < 32:
        errors.append('SESSION_SECRET_INVALID')
    try:
        url = validate_database_url(settings.database_url, legacy_path=settings.database_path)
        if url.drivername != 'postgresql+psycopg':
            errors.append('POSTGRESQL_REQUIRED')
    except Exception:
        errors.append('DATABASE_URL_INVALID')
    return errors


def check_database(settings):
    try:
        db = MultiUserDatabase(settings.database_url, legacy_path=settings.database_path)
        try:
            with db.engine.connect() as connection:
                revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
            return [] if revision == '0005' else ['DATABASE_MIGRATION_REQUIRED']
        finally:
            db.close()
    except Exception:
        # No exception strings: drivers may include hosts, users and parameters.
        return ['DATABASE_CHECK_FAILED']


def main():
    try:
        settings = Settings.load()
        errors = check_settings(settings, OAuthSettings.load(), load_session_secret())
        if not errors:
            errors = check_database(settings)
    except Exception:
        errors = ['CONFIGURATION_LOAD_FAILED']
    if errors:
        for error in errors:
            print(error)
        return 1
    print('PREFLIGHT_OK: settings and schema only; complete deployment acceptance before launch.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
