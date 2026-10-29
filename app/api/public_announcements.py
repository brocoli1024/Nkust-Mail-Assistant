"""Anonymous public-table views. Never resolve sessions or fetch external data."""
from typing import Literal
from app.services.action_cards import build_action_card, public_source
from app.api.action_card_corrections import card_context
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Query, HTTPException
from sqlalchemy import select, func, or_
from app.api.session import page
from app.models.public_announcements import PublicAnnouncement as P, PublicSourceState as S, PublicSyncRun as R
from app.services.category_rules import CATEGORIES
from app.services.public_source import SOURCE_KEY, LISTING_URL, normalize_public_url, PublicSourceError, TAIPEI
from app.services.public_sync import aware

router = APIRouter()


def display_time(value):
    return aware(value).astimezone(TAIPEI).strftime('%Y-%m-%d %H:%M') if value else '尚無紀錄'


def status_data(session):
    state = session.get(S, SOURCE_KEY)
    run = session.scalar(select(R).where(R.source_key == SOURCE_KEY).order_by(R.id.desc()).limit(1))
    return dict(last_success=display_time(state.last_success_at) if state and state.last_success_at else '尚無成功更新紀錄',
                oldest=display_time(state.oldest_seen_at if state else None),
                history_status=state.history_status if state else 'not_started',
                history_completed=display_time(state.history_completed_at if state else None),
                last_run_status=run.status if run else None)


def home(request: Request):
    with request.app.state.database.transaction() as session:
        total = session.scalar(select(func.count()).select_from(P).where(P.source_key == SOURCE_KEY))
        status = status_data(session)
    return page(request, 'public_home.html', total=total, source_url=LISTING_URL, **status)


def public_item(row):
    try:
        url = normalize_public_url(row.canonical_url)
    except PublicSourceError:
        url = None
    return dict(id=row.id, title=row.title, excerpt=row.excerpt, category=row.category,
                student_relevance=row.student_relevance, published=display_time(row.published_at)
                if row.published_at else '未知', url=url)


@router.get('/public/announcements')
def announcements(request: Request, q: str = Query('', max_length=200), category: str = '',
                  audience: Literal['all','student'] = 'all',
                  page_number: int = Query(1, alias='page', ge=1, le=1000000)):
    if category and category not in (*CATEGORIES, '未分類'):
        raise HTTPException(422, '未知的公告分類。')
    statement = select(P).where(P.source_key == SOURCE_KEY)
    if audience == 'student':
        statement = statement.where(P.student_relevance == 'relevant')
    if category:
        statement = statement.where(P.category.is_(None) if category == '未分類' else P.category == category)
    if q.strip():
        statement = statement.where(or_(P.title.contains(q.strip(), autoescape=True), P.excerpt.contains(q.strip(), autoescape=True)))
    with request.app.state.database.transaction() as session:
        source_total = session.scalar(select(func.count()).select_from(P).where(P.source_key == SOURCE_KEY))
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = session.scalars(statement.order_by(P.published_at.desc().nulls_last(), P.id.desc()).offset((page_number-1)*20).limit(20)).all()
        items = [public_item(row) for row in rows]
        status = status_data(session)
    def link(number):
        return '/public/announcements?' + urlencode(dict(q=q,category=category,audience=audience,page=number))
    return page(request, 'public_announcements.html', items=items,total=total,source_total=source_total,q=q,category=category,
                audience=audience,categories=CATEGORIES,page_number=page_number,source_url=LISTING_URL,
                previous=link(page_number-1) if page_number>1 else None,
                following=link(page_number+1) if page_number*20<total else None, **status)


@router.get('/public/announcements/{announcement_id}')
def detail(announcement_id: int, request: Request):
    with request.app.state.database.transaction() as session:
        row = session.scalar(select(P).where(P.id == announcement_id, P.source_key == SOURCE_KEY))
        if row is None:
            raise HTTPException(404, '找不到公開公告。')
        item = public_item(row)
        card = build_action_card(public_source(row))
        status = status_data(session)
    return page(request, 'public_announcement_detail.html', item=item, source_url=LISTING_URL, **status, **card_context(card,'public'))
