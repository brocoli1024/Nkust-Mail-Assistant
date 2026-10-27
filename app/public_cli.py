"""Public source maintenance only; never imports legacy Gmail or AI CLI."""
import argparse
from dataclasses import asdict
import json
from sqlalchemy import text

from app.config import Settings
from app.database.multi_user import MultiUserDatabase
from app.database.schema import REQUIRED_REVISION
from app.services.public_source import SOURCE_KEY, fetch_feed, PublicSourceError
from app.services.public_sync import sync_recent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='維護公開校園公告；不存取 Gmail')
    subs = parser.add_subparsers(dest='command', required=True)
    sync = subs.add_parser('sync', help='同步官方 RSS 近期公告')
    sync.add_argument('--source', choices=[SOURCE_KEY], default=SOURCE_KEY)
    args = parser.parse_args(argv)
    database = None
    try:
        config = Settings.load()
        database = MultiUserDatabase(config.database_url, legacy_path=config.database_path)
        with database.engine.connect() as connection:
            revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
        if revision != REQUIRED_REVISION:
            raise PublicSourceError('PUBLIC_MIGRATION_REQUIRED')
        result = sync_recent(database, source=fetch_feed)
        print(json.dumps(asdict(result)))
        return 0 if result.status == 'success' else 1
    except Exception as exc:
        code = str(exc) if isinstance(exc, PublicSourceError) else 'PUBLIC_MAINTENANCE_FAILED'
        print(json.dumps({'status': 'failed', 'error_code': code}))
        return 1
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    raise SystemExit(main())
