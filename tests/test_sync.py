from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import Database
from app.models.email import Email
from app.services.announcement_parser import parse_email
from app.services.email_parser import DecodedEmail
from app.services.gmail_service import GmailError
from app.services.sync_service import SyncService


def email(message_id, html=None):
    if html is None:
        html = (Path(__file__).parent / 'fixtures/nkust_mail_sample.html').read_text(encoding='utf-8')
    return DecodedEmail(message_id, 'synthetic@example.invalid', 'sample',
                        datetime(2026, 9, 19, tzinfo=timezone.utc), html, None)


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / 'mail.db')
    gmail = Mock()
    gmail.list_message_ids.return_value = ['a', 'b']
    gmail.read_message.side_effect = email
    yield db, gmail, SyncService(gmail, db)
    db.close()


def test_repeat_sync_skips_download(setup):
    db, gmail, sync = setup
    first = sync.sync()
    gmail.read_message.reset_mock()
    second = sync.sync()
    assert (first.processed, first.announcements_written) == (2, 6)
    assert (second.processed, second.skipped) == (0, 2)
    assert first.database_counts == second.database_counts
    gmail.read_message.assert_not_called()


def test_failure_continues_and_retry_recovers(setup):
    db, gmail, sync = setup
    gmail.read_message.side_effect = lambda message_id: email(message_id, '<p>unknown</p>') if message_id == 'a' else email(message_id)
    first = sync.sync()
    assert (first.processed, first.failed) == (1, 1)
    with Session(db.engine) as session:
        failed = session.scalar(select(Email).where(Email.gmail_message_id == 'a'))
        assert failed.html_body == '<p>unknown</p>'
        assert failed.processed_at is None
    gmail.read_message.side_effect = email
    second = sync.sync()
    assert (second.processed, second.skipped, second.failed) == (1, 1, 0)
    assert db.counts() == {'emails': 2, 'announcements': 6, 'failed_emails': 0}


def test_network_failure_can_retry(setup):
    db, gmail, sync = setup
    gmail.read_message.side_effect = GmailError('GMAIL_REQUEST_FAILED')
    assert sync.sync().failed == 2
    gmail.read_message.side_effect = email
    assert sync.sync().processed == 2


def test_failed_force_reparse_preserves_success(setup):
    db, gmail, sync = setup
    sync.sync()
    gmail.read_message.side_effect = lambda mid: email(mid, '<p>bad</p>')
    assert sync.sync(force=True).failed == 2
    assert db.counts()['announcements'] == 6
    gmail.read_message.side_effect = email
    assert sync.sync(force=True).processed == 2
    assert db.counts()['announcements'] == 6


def test_write_failure_rolls_back_and_records_retryable_status(setup):
    db, gmail, sync = setup
    def broken(mail):
        parsed = parse_email(mail)
        parsed.announcements[1].source_index = 0
        return parsed
    sync.parser = broken
    result = sync.sync()
    assert result.failed == 2
    assert db.counts() == {'emails': 2, 'announcements': 0, 'failed_emails': 2}
    assert all(e['error'] == 'DATABASE_WRITE_FAILED: transaction rolled back' for e in result.errors)
    sync.parser = parse_email
    assert sync.sync().processed == 2


def test_parser_version_triggers_reparse(setup):
    db, gmail, sync = setup
    sync.sync()
    sync.parser_version = 'v2'
    result = sync.sync()
    assert result.processed == 2
    assert result.database_counts['announcements'] == 6


def test_concurrent_writes_and_restart(tmp_path):
    path = tmp_path / 'mail.db'
    first, second = Database(path), Database(path)
    mail = email('same')
    parsed = parse_email(mail)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(db.save_processed, mail, parsed, 'v1') for db in (first, second)]
            assert sorted(job.result() for job in jobs) == [False, True]
    finally:
        first.close()
        second.close()
    restarted = Database(path)
    try:
        assert restarted.is_processed('same', 'v1')
        assert restarted.counts()['announcements'] == 3
    finally:
        restarted.close()
