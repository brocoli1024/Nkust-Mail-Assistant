"""Read-only synthetic demo; never resolves sessions or reads the database."""
from app.services.action_cards import build_action_card, demo_source
from app.api.action_card_corrections import card_context
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.session import page
from app.services.category_rules import CATEGORIES
from app.services.demo_announcements import get_demo_announcement, list_demo_announcements

router = APIRouter()


@router.get('/demo')
def announcements(request: Request, q: str = Query('', max_length=200), category: str = ''):
    if category and category not in CATEGORIES:
        raise HTTPException(422, '未知的公告分類。')
    return page(request, 'demo_announcements.html', items=list_demo_announcements(q, category),
                q=q, category=category, categories=CATEGORIES)


@router.get('/demo/announcements/{demo_id}')
def detail(demo_id: str, request: Request):
    item = get_demo_announcement(demo_id)
    if item is None:
        raise HTTPException(404, '找不到合成示範公告。')
    return page(request, 'demo_announcement_detail.html', item=item, **card_context(build_action_card(demo_source(item)),'demo'))
