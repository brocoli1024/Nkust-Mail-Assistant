from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.database import Database
from app.models.email import Email
from app.models.announcement import Announcement
from app.services.email_parser import DecodedEmail
from app.services.announcement_parser import parse_email


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / 'mail.db')
    yield database
    database.close()


def sample(message_id='sample'):
    html = (Path(__file__).parent / 'fixtures/nkust_mail_sample.html').read_text(encoding='utf-8')
    return DecodedEmail(message_id, 'synthetic@example.invalid', 'sample',
                        datetime(2026, 9, 19, tzinfo=timezone.utc), html, None)


def test_roundtrip_and_duplicate(db):
    email = sample()
    assert db.save_processed(email, parse_email(email), 'v1')
    assert not db.save_processed(email, parse_email(email), 'v1')
    assert db.counts() == {'emails': 1, 'announcements': 3, 'failed_emails': 0}
    with Session(db.engine) as session:
        saved = session.scalar(select(Email))
        assert saved.html_body == email.html_body
        assert saved.processed_at and saved.parser_version == 'v1'
        a = session.scalar(select(Announcement).where(Announcement.source_index == 0))
        assert a.deadline == '2026-10-08'
        assert a.source_category == a.category == '獎學金'
        assert a.original_text and a.date_evidence
        assert a.requires_action is None


def test_failed_insert_rolls_back_entire_email(db):
    email = sample()
    result = parse_email(email)
    result.announcements[1].source_index = 0
    with pytest.raises(IntegrityError):
        db.save_processed(email, result, 'v1')
    assert db.counts()['emails'] == db.counts()['announcements'] == 0


def test_failed_replacement_keeps_old_data(db):
    email = sample()
    db.save_processed(email, parse_email(email), 'v1')
    broken = parse_email(email)
    broken.announcements[1].source_index = 0
    with pytest.raises(IntegrityError):
        db.save_processed(email, broken, 'v2')
    db.record_failure(email.gmail_message_id, 'synthetic failure')
    assert db.is_processed(email.gmail_message_id, 'v1')
    assert db.counts()['announcements'] == 3


def test_failed_email_can_be_retried(db):
    email = sample()
    db.record_failure(email.gmail_message_id, 'synthetic failure', email)
    assert not db.is_processed(email.gmail_message_id, 'v1')
    assert db.counts()['failed_emails'] == 1
    db.save_processed(email, parse_email(email), 'v1')
    assert db.counts()['failed_emails'] == 0
    with Session(db.engine) as session:
        assert session.scalar(select(Email)).last_error is None


def test_new_version_replaces_and_different_emails_remain(db):
    email = sample()
    db.save_processed(email, parse_email(email), 'v1')
    result = parse_email(email)
    result.announcements.pop()
    db.save_processed(email, result, 'v2')
    other = sample('other')
    db.save_processed(other, parse_email(other), 'v2')
    assert db.counts()['announcements'] == 5
    assert db.is_processed('sample', 'v2')


def test_foreign_key_enforced(db):
    with pytest.raises(IntegrityError), db.transaction() as session:
        session.add(Announcement(email_id=999, source_index=0, source_fingerprint='x',
                                 department='x', source_category='x', title='x', original_text='x',
                                 date_inferred=False, created_at='2026-09-20', updated_at='2026-09-20'))
