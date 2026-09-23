"""Read-only dashboard queries. Calendar calculations use Asia/Taipei (UTC+8)."""
from datetime import datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.database.database import CATEGORIES
from app.models.announcement import Announcement as A
from app.models.email import Email
from app.models.analysis import Analysis
from app.models.scrape import Scrape
from app.api.scrape import ERRORS

router = APIRouter(prefix='/api', tags=['announcements'])
TAIPEI = timezone(timedelta(hours=8))
View = Literal['all', 'today', 'deadline', 'action', 'jobs', 'tech']
FILTER_WORDS = {
    '課程': ('課程', '開課', '微學分'), '選課': ('選課',), '獎學金': ('獎學金', '獎助學金', '獎勵金'),
    '競賽': ('競賽', '比賽'), '講座': ('講座', '演講'), '活動': ('活動',),
    '證照': ('證照', '證輔導', '考證'), 'TOEIC': ('TOEIC', '多益'),
    '實習': ('實習',), '徵才': ('徵才', '徵聘'), '交換學生': ('交換學生',),
    '行政通知': ('行政通知',), '其他': ('其他',),
}


def calendar(request):
    today = request.app.state.now().astimezone(TAIPEI).date()
    start = datetime.combine(today, time.min, TAIPEI)
    return today, start, start + timedelta(days=1)


def conditions(request, view='all', category=None, q=None):
    today, start, end = calendar(request)
    clauses = []
    if view == 'today':
        clauses.extend([func.julianday(Email.received_at) >= func.julianday(start.isoformat()),
                        func.julianday(Email.received_at) < func.julianday(end.isoformat())])
    elif view == 'deadline':
        clauses.extend([A.deadline >= today.isoformat(), A.deadline <= (today + timedelta(days=6)).isoformat()])
    elif view == 'action':
        clauses.append(A.requires_action.is_(True))
    elif view == 'jobs':
        clauses.append(or_(A.category.in_(['實習', '徵才']),
                           A.title.contains('徵才'), A.title.contains('實習'), A.title.contains('就業')))
    elif view == 'tech':
        clauses.append(or_(A.title.ilike('%AI%'), A.title.contains('人工智慧'), A.title.contains('科技')))
    if category:
        # Until AI classification is added, include unclassified source/title keyword matches.
        # These are search matches only; never overwrite the persisted category.
        keywords = FILTER_WORDS[category]
        fallback = [column.contains(word) for word in keywords for column in (A.source_category, A.title)]
        clauses.append(or_(A.category == category, and_(A.category.is_(None), or_(*fallback))))
    if q:
        clauses.append(or_(A.title.contains(q, autoescape=True), A.department.contains(q, autoescape=True)))
    return clauses


def serialize(row, received_at):
    return {key: getattr(row, key) for key in (
        'id', 'department', 'source_category', 'category', 'title', 'summary',
        'url', 'event_date', 'deadline', 'requires_action', 'date_inferred',
        'analysis_status',
    )} | {'received_at': received_at}


@router.get('/announcements')
def announcements(request: Request, view: View = 'all', category: str | None = None,
                  q: str | None = Query(None, max_length=100),
                  page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    if category and category not in CATEGORIES:
        raise HTTPException(422, '未知的公告分類')
    clauses = conditions(request, view, category, q)
    with Session(request.app.state.database.engine) as session:
        base = select(A, Email.received_at).join(Email).where(*clauses)
        total = session.scalar(select(func.count()).select_from(A).join(Email).where(*clauses))
        if view == 'deadline':
            base = base.order_by(A.deadline, A.id.desc())
        else:
            base = base.order_by(func.julianday(Email.received_at).desc(), A.source_index, A.id.desc())
        rows = session.execute(base.offset((page - 1) * page_size).limit(page_size)).all()
        return {'items': [serialize(a, received) for a, received in rows], 'total': total,
                'page': page, 'page_size': page_size}


@router.get('/announcements/{announcement_id}')
def detail(announcement_id: int, request: Request):
    with Session(request.app.state.database.engine) as session:
        found = session.execute(select(A, Email.received_at).join(Email).where(A.id == announcement_id)).first()
        if not found:
            raise HTTPException(404, '找不到這則公告，可能已重新解析，請重新整理。')
        row, received = found
        scraped = session.get(Scrape, row.id)
        web = {'text': row.scraped_text, 'status': scraped.status,
               'url': scraped.final_url or scraped.source_url, 'fetched_at': scraped.fetched_at,
               'error': ERRORS.get(scraped.error, '擷取未完成，請稍後重試。') if scraped.error else None} if scraped else None
        latest = session.scalar(select(Analysis).where(Analysis.announcement_id == row.id).order_by(Analysis.id.desc()).limit(1))
        successful = session.scalar(select(Analysis).where(Analysis.announcement_id == row.id,
            Analysis.status == 'completed').order_by(Analysis.id.desc()).limit(1))
        analysis = None
        if latest:
            analysis = {'status': latest.status, 'model': latest.model, 'created_at': latest.created_at,
                        'warnings': latest.warnings, 'error': latest.error,
                        'result': successful.result if successful else None,
                        'result_model': successful.model if successful else None}
        return serialize(row, received) | {'original_text': row.original_text, 'date_evidence': row.date_evidence,
                                           'analysis': analysis, 'keywords': row.keywords, 'web': web,
                                           'source_index': row.source_index, 'source_fingerprint': row.source_fingerprint}


@router.get('/summary')
def summary(request: Request):
    today, _, _ = calendar(request)
    with Session(request.app.state.database.engine) as session:
        def count(*clauses):
            return session.scalar(select(func.count()).select_from(A).join(Email).where(*clauses))
        return {
            'today': today.isoformat(), 'today_received': count(*conditions(request, 'today')),
            'total': count(), 'upcoming_deadlines': count(*conditions(request, 'deadline')),
            'requires_action': count(A.requires_action.is_(True)),
            'action_unknown': count(A.requires_action.is_(None)),
            'last_processed_at': session.scalar(select(func.max(Email.processed_at))),
            'failed_emails': session.scalar(select(func.count()).select_from(Email).where(Email.last_error.is_not(None))),
        }
