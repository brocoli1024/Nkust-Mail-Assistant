"""Offline compilation is a readiness check, not a PostgreSQL execution test."""
from io import StringIO

from alembic import command
from sqlalchemy.dialects import postgresql

from app.api.user_announcements import owned, calendar, view_condition
from app.core.session import CurrentUser
from app.database.multi_user import validate_database_url
from tests.test_multi_user_database import configuration


def test_postgresql_upgrade_and_downgrade_sql():
    output = StringIO()
    config = configuration('postgresql+psycopg://test:unused@localhost/test', output)
    command.upgrade(config, 'head', sql=True)
    sql = output.getvalue()
    assert 'CREATE TABLE sync_leases' in sql
    assert 'ADD COLUMN category_rule_version' in sql
    assert 'TIMESTAMP WITH TIME ZONE' in sql
    assert 'SERIAL' in sql
    assert 'BOOLEAN' in sql and 'JSON' in sql
    output.seek(0)
    output.truncate(0)
    command.downgrade(config, '0005:base', sql=True)
    assert 'DROP TABLE users' in output.getvalue()


def test_dashboard_queries_compile_with_postgresql():
    for view in ('all', 'today', 'deadline', 'action'):
        statement = owned(CurrentUser(7, 'synthetic@example.invalid', None, 'google-synthetic')).where(view_condition(view, calendar()))
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert 'announcements.user_id =' in sql and 'emails.user_id =' in sql
        assert 'users.google_user_id =' in sql
        assert 'julianday' not in sql and 'strftime' not in sql


def test_url_preserves_ssl_and_encoded_password_without_printing_secrets():
    url = validate_database_url('postgresql://test:p%40ss%25word@localhost/test?sslmode=require')
    assert url.drivername == 'postgresql+psycopg'
    assert url.password == 'p@ss%word'
    assert url.query['sslmode'] == 'require'
    assert 'p@ss%word' not in repr(url)
