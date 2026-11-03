from datetime import datetime,timezone
from bs4 import BeautifulSoup
from tests.test_sessions import web
from tests.test_auth import oauth
from tests.test_public_pages import seed
from tests.test_action_cards import source
from app.services.action_cards import build_action_card


def test_dates_respect_taipei_boundary_and_do_not_guess_end_time():
    from app.services.reading_dates import reading_dates
    card=build_action_card(source('報名截止：2026年11月2日；活動日期：2026年11月1日'))
    before=reading_dates(card,now=datetime(2026,11,1,15,59,tzinfo=timezone.utc))
    after=reading_dates(card,now=datetime(2026,11,1,16,tzinfo=timezone.utc))
    assert before['notices']==[]
    assert after['notices']==['今日截止，確切時間請核對原文。','活動日期已過，是否仍可辦理請核對來源。']
    assert '結束' not in str(after)
    stale=card.model_copy(update={'fields':{k:f.model_copy(update={'state':'stale'}) for k,f in card.fields.items()}})
    assert reading_dates(stale,now=datetime(2026,11,3,tzinfo=timezone.utc))['dates']==[]
    ambiguous=build_action_card(source('報名截止：11月2日；活動日期：2026年11月1日至2026年11月4日'))
    assert reading_dates(ambiguous,now=datetime(2026,11,3,tzinfo=timezone.utc))['notices']==[]


def test_focus_page_hides_advanced_tools_and_sources_but_keeps_failures_visible(web):
    c,app,_,_=web;seed(app)
    soup=BeautifulSoup(c.get('/public/announcements/1').text,'html.parser')
    tools=soup.select_one('[data-reading-tools]')
    assert tools and not tools.has_attr('open')
    assert tools.select_one('[data-local-editor]') and tools.select_one('.calendar-export')
    assert tools.find('summary',string='原始解析與候選日期')
    sources=soup.select_one('details.reading-originals')
    assert sources and not sources.has_attr('open') and '來源摘要' in sources.get_text()
    summary=soup.select_one('[data-card-field="summary"]')
    assert summary.find_parent('details') and not summary.find_parent('details').has_attr('open')
    assert soup.select_one('[data-card-field="action"]').find_parent('details') is None


def test_public_list_has_immediate_filters_keyword_search_and_student_shortcut(web):
    c,app,_,_=web;seed(app)
    soup=BeautifulSoup(c.get('/public/announcements?q=PUBLIC&category=獎學金').text,'html.parser')
    form=soup.select_one('#announcement-filters')
    assert not form.has_attr('data-explicit-submit')
    assert '選單變更後立即更新' in soup.select_one('#public-filter-help').get_text()
    assert form.select_one('button[type="submit"]').find_parent('noscript') is None
    assert form.select_one('button[type="submit"]').get_text(strip=True)=='搜尋'
    shortcut=soup.select_one('[data-student-shortcut]')
    from urllib.parse import parse_qs,urlsplit
    assert parse_qs(urlsplit(shortcut['href']).query)=={'q':['PUBLIC'],'category':['獎學金'],'audience':['student'],'page':['1']}
    status=soup.select_one('[aria-label="公告來源與更新狀態"]')
    assert 'compact-source-status' in status['class']
    assert status.select_one('[role="status"]') and not status.select_one('[role="status"]').find_parent('details')
    assert status.select_one('details')


def test_list_dates_match_verified_card_not_ticket_sale_or_unknown_year(web):
    from app.models.public_announcements import PublicAnnouncement as P
    from app.services.source_history import record_public_version
    c,app,_,_=web;seed(app)
    with app.state.database.transaction() as s:
        row=s.get(P,1);row.excerpt='報名截止：2026年11月10日；活動日期：2026年11月20日'
        record_public_version(s,row,datetime.now(timezone.utc))
    soup=BeautifulSoup(c.get('/public/announcements').text,'html.parser')
    item=soup.select_one('#announcement-1')
    assert '截止：2026-11-10' in item.get_text() and '活動：2026-11-20' in item.get_text()
    assert item.select_one('[data-list-todo-ref]')
    with app.state.database.transaction() as s:
        s.get(P,1).excerpt='報名截止：11月10日；活動日期：11月20日'
    item=BeautifulSoup(c.get('/public/announcements').text,'html.parser').select_one('#announcement-1')
    assert '2026-11-10' not in item.get_text()
    assert '日期待確認' in item.get_text()


def test_list_batches_source_versions_and_excludes_stale_article_dates(web):
    from sqlalchemy import event
    from app.models.public_announcements import PublicAnnouncement as P
    from app.services.source_history import record_public_version
    c,app,_,_=web;seed(app)
    with app.state.database.transaction() as s:
        row=s.get(P,1)
        record_public_version(s,row,datetime.now(timezone.utc),article={'text':'報名截止：2026年11月10日','rss_hash':row.content_hash})
        row.content_hash='changed-source'
        for i in range(4,25):s.add(P(id=i,source_key='nkust-latest',canonical_url=f'https://osa.nkust.edu.tw/synthetic-{i}',title=f'合成公告{i}',excerpt='',content_hash=str(i)))
    statements=[]
    def query(conn,cursor,statement,parameters,context,many):
        if 'public_source_versions' in statement:statements.append(statement)
    event.listen(app.state.database.engine,'before_cursor_execute',query)
    try:r=c.get('/public/announcements')
    finally:event.remove(app.state.database.engine,'before_cursor_execute',query)
    assert r.status_code==200 and len(statements)==1
    item=BeautifulSoup(c.get('/public/announcements?q=PUBLIC-STUDENT').text,'html.parser').select_one('#announcement-1')
    assert '截止：2026-11-10' not in item.get_text() and '來源待更新' in item.get_text()
