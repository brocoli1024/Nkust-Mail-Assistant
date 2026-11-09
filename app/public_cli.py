"""Public source maintenance only; never imports legacy Gmail or AI CLI."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from sqlalchemy import text

from app.config import Settings
from app.database.multi_user import MultiUserDatabase
from app.database.schema import PUBLIC_MAINTENANCE_REVISIONS
from app.services.public_source import SOURCE_KEY, fetch_feed, PublicSourceError
from app.services.public_sync import sync_recent, reclassify, backfill_history


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='維護公開校園公告；不存取 Gmail')
    subs = parser.add_subparsers(dest='command', required=True)
    sync = subs.add_parser('sync', help='同步官方 RSS 近期公告')
    sync.add_argument('--source', choices=[SOURCE_KEY], default=SOURCE_KEY)
    rules = subs.add_parser('reclassify', help='離線重算公開公告分類與學生相關提示')
    rules.add_argument('--source', choices=[SOURCE_KEY], default=SOURCE_KEY)
    history = subs.add_parser('backfill', help='分批補收歷史清單；失敗可續跑')
    history.add_argument('--source', choices=[SOURCE_KEY], default=SOURCE_KEY)
    history.add_argument('--max-pages', type=int, choices=range(1,21), default=5)
    articles = subs.add_parser('articles', help='分批更新官方公告本文（不抓附件）')
    articles.add_argument('--limit',type=int,choices=range(1,21),default=8)
    articles.add_argument('--announcement-id',type=int,help='只重讀一則公開公告（略過快取）')
    office=subs.add_parser('office-import',help='導入明確提供的官方公務網址；不查Gmail')
    office.add_argument('--urls-file',required=True)
    refresh=subs.add_parser('office-refresh',help='只重讀已收錄公務公告，不發現新郵件')
    refresh.add_argument('--limit',type=int,choices=range(1,21),default=8)
    args = parser.parse_args(argv)
    database = None
    try:
        config = Settings.load()
        database = MultiUserDatabase(config.database_url, legacy_path=config.database_path)
        with database.engine.connect() as connection:
            revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
        if revision not in PUBLIC_MAINTENANCE_REVISIONS:
            raise PublicSourceError('PUBLIC_MIGRATION_REQUIRED')
        if args.command in ('office-import','office-refresh'):
            from app.services.office_mail_sync import import_office_mail,refresh_office_mail
            if args.command=='office-import':
                path=Path(args.urls_file)
                if path.stat().st_size>100000:raise PublicSourceError('OFFICE_MAIL_URL_LIST')
                urls=[line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
                result=import_office_mail(database,urls)
            else:result=refresh_office_mail(database,limit=args.limit)
        elif args.command == 'sync':
            result = sync_recent(database, source=fetch_feed)
        elif args.command == 'articles':
            from app.services.public_articles import refresh_articles
            result = refresh_articles(database,limit=args.limit,announcement_id=args.announcement_id)
        elif args.command == 'backfill':
            result = backfill_history(database,max_pages=args.max_pages)
        else:
            result = reclassify(database)
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
