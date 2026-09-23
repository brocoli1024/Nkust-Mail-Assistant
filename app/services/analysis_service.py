"""Bounded, explicit batches. Network calls never hold a database transaction."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.announcement import Announcement as A
from app.models.analysis import Analysis
from app.models.email import Email
from app.providers.base import AIError
from app.services.ai_analyzer import PROMPT_VERSION, analyze
from app.services.date_parser import parse_dates

TAIPEI = timezone(timedelta(hours=8))


def snapshot(row, received_at):
    return {key: getattr(row, key) for key in (
        'department', 'source_category', 'title', 'original_text', 'source_fingerprint',
        'created_at', 'updated_at', 'event_date', 'deadline',
        'scraped_text', 'url',
    )} | {'received_at': received_at}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass
class BatchResult:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    warnings: list = field(default_factory=list)


class AnalysisService:
    def __init__(self, provider, database):
        self.provider, self.database = provider, database
        self.version = PROMPT_VERSION + ':' + digest([
            provider.name, provider.model, getattr(provider, 'base_url', ''),
        ])[:16]

    def run(self, limit=5, *, retry_failed=False, announcement_id=None):
        if not 1 <= limit <= 20:
            raise ValueError('Analysis limit must be between 1 and 20')
        with Session(self.database.engine) as session:
            query = select(A, Email.received_at).join(Email)
            if announcement_id is not None:
                query = query.where(A.id == announcement_id)
            if retry_failed:
                query = query.where(A.analysis_status == 'failed')
            else:
                query = query.where(A.analysis_status != 'failed', or_(
                    A.analysis_status != 'completed', A.analysis_version.is_(None),
                    A.analysis_version != self.version))
            selected = [(a.id, snapshot(a, received)) for a, received in
                        session.execute(query.order_by(A.id).limit(limit))]
        batch = BatchResult()
        for announcement_id, source in selected:
            # Recheck immediately before the outbound call; another batch may have finished it.
            if not self._current(announcement_id, source):
                batch.skipped += 1
                continue
            result, error = None, None
            try:
                received = datetime.fromisoformat(source['received_at'])
                if received.tzinfo is None:
                    received = received.replace(tzinfo=TAIPEI)
                result = analyze(self.provider, **{key: source[key] for key in (
                    'department', 'source_category', 'title', 'original_text')},
                    received_at=received.astimezone(TAIPEI),
                    supplemental_text=source['scraped_text'], source_url=source['url'])
            except AIError as exc:
                # Only a fixed diagnostic code is stored; never provider bodies or credentials.
                code = str(exc).split(':', 1)[0]
                error = code if code.startswith('AI_') and code.replace('_', '').isalnum() else 'AI_FAILED'
            if not self._save(announcement_id, source, result, error):
                batch.skipped += 1
                continue
            if error:
                batch.failed += 1
                if error in {'AI_HTTP_ERROR', 'AI_TIMEOUT', 'AI_CONNECTION_FAILED'}:
                    break
            else:
                batch.processed += 1
                batch.warnings.extend({'id': announcement_id, 'warning': w} for w in result.warnings)
        return batch

    def _current(self, announcement_id, source):
        with Session(self.database.engine) as session:
            found = session.execute(select(A, Email.received_at).join(Email).where(A.id == announcement_id)).first()
            return bool(found and snapshot(*found) == source)

    def _save(self, announcement_id, source, result, error):
        with self.database.transaction() as session:
            found = session.execute(select(A, Email.received_at).join(Email).where(A.id == announcement_id)).first()
            if not found or snapshot(*found) != source:
                return False
            row = found[0]
            now = datetime.now(timezone.utc).isoformat()
            status = 'failed' if error else 'completed'
            session.add(Analysis(announcement_id=row.id, input_hash=digest(source),
                                 provider=self.provider.name, model=self.provider.model,
                                 version=self.version, status=status, error=error,
                                 result=(result.output.model_dump() | {
                                     'used_web_content': bool(source['scraped_text']),
                                     'source_url': source['url'] if source['scraped_text'] else None,
                                 }) if result else None,
                                 warnings=result.warnings if result else [], created_at=now))
            if result:
                output = result.output
                row.summary, row.category = output.summary, output.category
                row.keywords, row.requires_action = output.keywords, output.requires_action
                # Rule-derived dates take precedence, including when AI returned null.
                row.event_date = row.event_date or output.event_date
                row.deadline = row.deadline or output.deadline
                for role, field in (('event_date', 'event_evidence'), ('deadline', 'deadline_evidence')):
                    if source[role] is None and getattr(output, role) and source['scraped_text']:
                        quote = getattr(output, field)
                        quote_dates = parse_dates(quote or '', datetime.fromisoformat(source['received_at']).astimezone(TAIPEI))
                        inferred = any(e.year_inferred for e in quote_dates.evidence)
                        row.date_evidence = [*row.date_evidence, {
                            'original_text': quote, 'iso_date': getattr(output, role),
                            'role': role, 'year_inferred': inferred, 'source_url': source['url'],
                        }]
                        row.date_inferred = row.date_inferred or inferred
                row.analysis_version = self.version
            row.analysis_status = status
            row.updated_at = now
            return True
