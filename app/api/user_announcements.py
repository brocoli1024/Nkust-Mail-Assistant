"""Session-owned, read-only announcement pages; never mount the legacy router."""
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select

from app.api.session import page
from app.core.session import current_page_user
from app.models.multi_user import Announcement as A, Email

router = APIRouter()
TAIPEI = timezone(timedelta(hours=8))
CATEGORIES = ('課程', '選課', '獎學金', '競賽', '講座', '活動', '證照', 'TOEIC',
              '實習', '徵才', '交換學生', '行政通知', '其他')
FILTER_WORDS = {
    '課程': ('課程', '開課', '微學分'), '選課': ('選課',), '獎學金': ('獎學金', '獎助學金', '獎勵金'),
    '競賽': ('競賽', '比賽'), '講座': ('講座', '演講'), '活動': ('活動',),
    '證照': ('證照', '證輔導', '考證'), 'TOEIC': ('TOEIC', '多益'),
    '實習': ('實習',), '徵才': ('徵才', '徵聘'), '交換學生': ('交換學生',),
    '行政通知': ('行政通知',), '其他': ('其他',),
}
View = Literal['all', 'today', 'deadline', 'action']


def calendar(now=None):
    today = (now or datetime.now(timezone.utc)).astimezone(TAIPEI).date()
    start = datetime.combine(today, time.min, TAIPEI).astimezone(timezone.utc)
    return today, start, start + timedelta(days=1)


def owned(user_id):
    return select(A, Email.received_at).join(Email, and_(
        A.email_id == Email.id, A.user_id == Email.user_id)).where(
        A.user_id == user_id, Email.user_id == user_id)


def view_condition(view, dates):
    today, start, end = dates
    return {
        'all': True,
        'today': and_(Email.received_at >= start, Email.received_at < end),
        'deadline': and_(A.deadline >= today, A.deadline <= today + timedelta(days=6)),
        'action': A.requires_action.is_(True),
    }[view]


def dashboard_counts(database, user_id):
    dates = calendar()
    with database.transaction() as session:
        return {view: session.scalar(select(func.count()).select_from(
            owned(user_id).where(view_condition(view, dates)).subquery()))
            for view in ('all', 'today', 'deadline', 'action')}


def safe_url(value):
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def item_data(row, received_at, *, detail=False):
    result = {key: getattr(row, key) for key in (
        'id', 'department', 'source_category', 'category', 'title', 'summary',
        'event_date', 'deadline', 'requires_action', 'date_inferred')}
    # SQLite returns naive UTC while PostgreSQL retains timezone information.
    result['received_at'] = ((received_at.replace(tzinfo=timezone.utc) if received_at.tzinfo is None
                              else received_at).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M')
                             if received_at else '未知')
    if detail:
        result.update(original_text=row.original_text, url=safe_url(row.url))
    return result


@router.get('/announcements')
def announcements(request: Request, user=Depends(current_page_user), view: View = 'all',
                  category: str = '', page_number: int = Query(1, alias='page', ge=1, le=1000000)):
    if category and category not in CATEGORIES and category != '未分類':
        raise HTTPException(422, '未知的公告分類。')
    statement = owned(user.id).where(view_condition(view, calendar()))
    if category:
        if category == '未分類':
            statement = statement.where(A.category.is_(None))
        else:
            fallback = or_(*(column.contains(word, autoescape=True)
                             for word in FILTER_WORDS[category]
                             for column in (A.source_category, A.title)))
            statement = statement.where(or_(A.category == category,
                                            and_(A.category.is_(None), fallback)))
    ordering = (Email.received_at.desc().nulls_last(), A.id.desc())
    if view == 'deadline':
        ordering = (A.deadline.asc(), *ordering)
    with request.app.state.database.transaction() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = session.execute(statement.order_by(*ordering)
                               .offset((page_number - 1) * 20).limit(20)).all()
        items = [item_data(row, received_at) for row, received_at in rows]
    def link(number):
        return '/announcements?' + urlencode({'view': view, 'category': category, 'page': number})
    return page(request, 'announcements.html', user=user, items=items, total=total,
                categories=CATEGORIES, category=category, view=view, page_number=page_number,
                previous=link(page_number - 1) if page_number > 1 else None,
                following=link(page_number + 1) if page_number * 20 < total else None)


@router.get('/announcements/{announcement_id}')
def announcement_detail(announcement_id: int, request: Request, user=Depends(current_page_user)):
    with request.app.state.database.transaction() as session:
        result = session.execute(owned(user.id).where(A.id == announcement_id)).first()
        if result is None:
            raise HTTPException(404, '找不到公告。')
        item = item_data(*result, detail=True)
    return page(request, 'announcement_detail.html', user=user, item=item)
