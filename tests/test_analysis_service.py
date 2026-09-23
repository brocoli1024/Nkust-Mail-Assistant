import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import Database
from app.models.announcement import Announcement as A
from app.models.analysis import Analysis
from app.providers.base import AIError
from app.services.analysis_service import AnalysisService
from app.services.announcement_parser import parse_email
from app.services.email_parser import DecodedEmail


class FakeProvider:
    name, model = 'iai', 'test-model'
    def __init__(self):
        self.calls = 0
        self.hook = None
        self.error = None

    def generate(self, system, payload, schema):
        self.calls += 1
        if self.hook:
            self.hook()
        if self.error:
            raise AIError(self.error)
        return json.dumps(dict(summary='測試摘要', category='其他', keywords=['測試'],
                               requires_action=None, action_evidence=None,
                               event_date=None, deadline=None,
                               event_evidence=None, deadline_evidence=None))


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / 'analysis.db')
    email = DecodedEmail('test', 'test@example.invalid', 'test', datetime(2026, 9, 21, tzinfo=timezone.utc),
        (Path(__file__).parent / 'fixtures/nkust_mail_sample.html').read_text(encoding='utf-8'), None)
    db.save_processed(email, parse_email(email), 'parser-test')
    provider = FakeProvider()
    yield db, provider, email
    db.close()


def test_batch_preserves_original_and_dates_and_is_idempotent(setup):
    db, provider, _ = setup
    with Session(db.engine) as s:
        before = [(a.original_text, a.deadline, a.event_date, a.source_category, a.source_fingerprint)
                  for a in s.scalars(select(A).order_by(A.id))]
    service = AnalysisService(provider, db)
    assert service.run(2).processed == 2
    assert service.run(2).processed == 1
    assert service.run(2).processed == 0
    assert provider.calls == 3
    with Session(db.engine) as s:
        rows = s.scalars(select(A).order_by(A.id)).all()
        assert [(a.original_text, a.deadline, a.event_date, a.source_category, a.source_fingerprint) for a in rows] == before
        assert all(a.summary == '測試摘要' and a.analysis_status == 'completed' for a in rows)
        records = s.scalars(select(Analysis)).all()
        assert len(records) == 3 and all(len(r.input_hash) == 64 for r in records)


def test_failed_batch_requires_explicit_retry_and_sanitizes_error(setup):
    db, provider, _ = setup
    provider.error = 'AI_HTTP_ERROR: sensitive provider response'
    service = AnalysisService(provider, db)
    assert service.run(5).failed == 1  # Stop after a connection/service error.
    with Session(db.engine) as s:
        assert s.scalar(select(Analysis)).error == 'AI_HTTP_ERROR'
        assert s.get(A, 1).summary is None
    provider.error = None
    assert service.run(5).processed == 2  # Failed item is not retried implicitly.
    assert service.run(5, retry_failed=True).processed == 1


def test_concurrent_reparse_does_not_apply_stale_analysis(setup):
    db, provider, email = setup
    provider.hook = lambda: db.save_processed(email, parse_email(email), 'new-parser', force=True)
    result = AnalysisService(provider, db).run(1)
    assert result.skipped == 1 and result.processed == 0
    with Session(db.engine) as s:
        assert s.get(A, 1).summary is None
        assert s.scalar(select(Analysis)) is None


def test_failed_model_change_preserves_successful_output(setup):
    db, provider, _ = setup
    assert AnalysisService(provider, db).run(1).processed == 1
    provider.model = 'different-model'
    provider.error = 'AI_OUTPUT_INVALID: malformed'
    assert AnalysisService(provider, db).run(1).failed == 1
    with Session(db.engine) as s:
        assert s.get(A, 1).summary == '測試摘要'
        assert s.get(A, 1).analysis_status == 'failed'
        assert len(s.scalars(select(Analysis)).all()) == 2


@pytest.mark.parametrize('limit', [0, 21])
def test_batch_bound(setup, limit):
    db, provider, _ = setup
    with pytest.raises(ValueError):
        AnalysisService(provider, db).run(limit)
    assert provider.calls == 0


def test_year_is_taipei_received_year(setup):
    db, provider, email = setup
    email = replace(email, received_at=datetime(2025, 12, 31, 16, 30, tzinfo=timezone.utc))
    db.save_processed(email, parse_email(email), 'new', force=True)
    original = provider.generate
    def generate(system, payload, schema):
        assert payload['received_year'] == 2026
        return original(system, payload, schema)
    provider.generate = generate
    assert AnalysisService(provider, db).run(1).processed == 1
