import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.announcement import Announcement
from app.models.scrape import Scrape
from app.services.scraper import ScrapeError


class ScrapeService:
    def __init__(self, scraper, database):
        self.scraper, self.database = scraper, database

    def run(self, announcement_id, *, refresh=False):
        with Session(self.database.engine) as session:
            row = session.get(Announcement, announcement_id)
            if row is None:
                raise ScrapeError('SCRAPE_NOT_FOUND')
            if not row.url:
                raise ScrapeError('SCRAPE_NO_URL')
            previous = session.get(Scrape, row.id)
            if previous and previous.status == 'completed' and previous.source_url == row.url and not refresh:
                return {'status': 'cached', 'changed': False}
            snapshot = (row.url, row.original_text, row.created_at, row.updated_at)
        content, error = None, None
        try:
            content = self.scraper.scrape(snapshot[0])
        except ScrapeError as exc:
            error = str(exc)
        with self.database.transaction() as session:
            row = session.get(Announcement, announcement_id)
            if row is None or (row.url, row.original_text, row.created_at, row.updated_at) != snapshot:
                raise ScrapeError('SCRAPE_STALE')
            record = session.get(Scrape, announcement_id)
            if record is None:
                record = Scrape(announcement_id=announcement_id)
                session.add(record)
            now = datetime.now(timezone.utc).isoformat()
            record.attempted_at, record.error = now, error
            record.status = 'failed' if error else 'completed'
            changed = content is not None and content != row.scraped_text
            if content is not None:
                record.source_url, record.fetched_at = row.url, now
                final_url = getattr(self.scraper, 'last_url', None)
                record.final_url = final_url if isinstance(final_url, str) else row.url
                record.content_hash = hashlib.sha256(content.encode()).hexdigest()
                row.scraped_text = content
                if changed:
                    row.analysis_status = 'pending'
                    # Dates derived from an older webpage must not survive as current facts.
                    for evidence in row.date_evidence:
                        role = evidence.get('role')
                        if evidence.get('source_url') and role in ('event_date', 'deadline'):
                            if getattr(row, role) == evidence.get('iso_date'):
                                setattr(row, role, None)
                    row.date_evidence = [e for e in row.date_evidence if not e.get('source_url')]
                    row.date_inferred = any(e.get('year_inferred') for e in row.date_evidence)
                row.updated_at = now
        return {'status': 'failed' if error else 'completed', 'changed': changed, 'error': error}
