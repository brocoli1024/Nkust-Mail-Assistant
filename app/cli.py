"""Local parsing, read-only Gmail preview and transactional SQLite sync."""
import argparse
import json
import sys
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.services.announcement_parser import AnnouncementParseError, parse_announcements, parse_email
from app.services.email_parser import EmailParseError
from app.services.gmail_service import GmailError, GmailService
from app.database.database import Database
from app.services.sync_service import SyncService
from app.providers.iai import IAIProvider
from app.providers.base import AIError
from app.services.ai_analyzer import analyze


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('limit must be positive')
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='NKUST mail assistant')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('ai-models', help='List iAI model IDs using the local key; no email content is sent')
    commands.add_parser('ai-check', help='Analyze one synthetic announcement through iAI; no mail or database access')
    local = commands.add_parser('parse', help='Parse a UTF-8 HTML or labelled text file offline')
    local.add_argument('file', type=Path)
    local.add_argument('--received-at', type=datetime.fromisoformat, help='ISO date or datetime; used for missing years')
    gmail = commands.add_parser('gmail', help='Authorize readonly Gmail and preview matching messages; no database writes')
    gmail.add_argument('--limit', type=_positive, default=5, help='Maximum emails to read (default: 5)')
    sync = commands.add_parser('sync', help='Read Gmail into local SQLite, skipping completed messages')
    sync.add_argument('--limit', type=_positive, default=5, help='Maximum matching emails to examine (including already processed)')
    sync.add_argument('--reparse', action='store_true', help='Atomically replace stored announcements for selected emails')
    args = parser.parse_args(argv)
    try:
        if args.command == 'ai-models':
            provider = IAIProvider(Settings.load(), require_model=False)
            output = {'provider': provider.name, 'models': provider.list_models()}
            exit_code = 0
        elif args.command == 'ai-check':
            provider = IAIProvider(Settings.load())
            result = analyze(provider, department='測試單位', source_category='獎學金',
                             title='測試獎勵金申請',
                             original_text='測試獎勵金即日起受理申請至115年10月08日止。請繳交申請表。',
                             received_at=datetime(2026, 9, 21))
            output = {'provider': provider.name, 'model': provider.model,
                      'result': result.output.model_dump(), 'warnings': result.warnings}
            exit_code = 0
        elif args.command == 'parse':
            suffix = args.file.suffix.lower()
            if suffix not in ('.html', '.htm', '.txt'):
                raise ValueError('Only .html, .htm and .txt files are supported')
            text = args.file.read_text(encoding='utf-8')
            result = parse_announcements(html=text if suffix != '.txt' else None,
                                        plain_text=text if suffix == '.txt' else None,
                                        received_at=args.received_at)
            output = asdict(result)
            exit_code = 0
        elif args.command == 'sync':
            settings = Settings.load()
            database = Database(settings.database_path)
            try:
                with redirect_stdout(sys.stderr):
                    service = GmailService.connect(settings)
                result = SyncService(service, database).sync(args.limit, force=args.reparse)
                output = asdict(result)
                exit_code = 1 if result.failed else 0
            finally:
                database.close()
        else:
            # Keep OAuth browser instructions out of the JSON output stream.
            with redirect_stdout(sys.stderr):
                service = GmailService.connect(Settings.load())
            output = {'emails': [], 'errors': []}
            for message_id in service.list_message_ids(args.limit):
                try:
                    email = service.read_message(message_id)
                    result = parse_email(email)
                    output['emails'].append({
                        'gmail_message_id': email.gmail_message_id,
                        'sender': email.sender, 'subject': email.subject,
                        'received_at': email.received_at.isoformat(), **asdict(result),
                    })
                except (GmailError, EmailParseError, AnnouncementParseError) as exc:
                    output['errors'].append({'gmail_message_id': message_id, 'error': str(exc)})
            exit_code = 1 if output['errors'] else 0
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return exit_code
    except SQLAlchemyError:
        print('DATABASE_ERROR: check database path, permissions and available disk space', file=sys.stderr)
        return 1
    except (AIError, GmailError, EmailParseError, AnnouncementParseError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
