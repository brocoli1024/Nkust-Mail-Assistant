from urllib.parse import urlsplit, parse_qs
from bs4 import BeautifulSoup
from tests.test_sessions import web
from tests.test_auth import oauth
from tests.test_public_pages import seed


def test_reading_return_keeps_search_page_and_row_without_open_redirect(web):
    c,app,_,_=web;seed(app)
    soup=BeautifulSoup(c.get('/public/announcements?q=PUBLIC&category=獎學金&audience=student&page=1').text,'html.parser')
    link=soup.select_one('.announcement h2 a')
    assert parse_qs(urlsplit(link['href']).query)['q']==['PUBLIC']
    detail=BeautifulSoup(c.get(link['href']).text,'html.parser')
    back=detail.select_one('[data-public-back]')
    assert back and back.get_text(strip=True)=='← 返回搜尋結果'
    target=urlsplit(back['href'])
    assert target.path=='/public/announcements' and target.fragment=='announcement-1'
    assert parse_qs(target.query)=={'q':['PUBLIC'],'category':['獎學金'],'audience':['student'],'page':['1']}
    assert soup.select_one('#announcement-1')
    assert back.find_parent('nav')
    bad=BeautifulSoup(c.get('/public/announcements/1?return_to=https://evil.invalid').text,'html.parser')
    assert bad.select_one('[data-public-back]')['href']=='/public/announcements#announcement-1'
    assert c.get('/public/announcements/1?audience=bad').status_code==422


def test_primary_actions_precede_fields_and_editor_is_secondary(web):
    c,app,_,_=web;seed(app)
    soup=BeautifulSoup(c.get('/public/announcements/1').text,'html.parser')
    card=soup.select_one('.action-card')
    toolbar=card.select_one('[aria-label="公告主要操作"]')
    assert toolbar and toolbar.select_one('[data-device-todo][data-compact]')
    assert '學校原文' in toolbar.get_text()
    assert str(card).index('公告主要操作')<str(card).index('data-card-field=')
    assert len(card.select('[data-device-todo]'))==1
    editor=card.select_one('[data-local-editor]')
    assert editor.summary.get_text(strip=True)=='補充或修正這則公告'
    assert not editor.has_attr('open')
    assert '不修改官方公告' in editor.get_text()
    fields=editor.select('details.correction-field')
    assert len(fields)==6 and all(not x.has_attr('open') for x in fields)
    assert all(x.select_one('fieldset') for x in fields)
    assert card.select_one('[data-refresh]').find_parent('details')==editor
    assert '修正我的資訊' not in soup.get_text()


def test_direct_detail_has_safe_back_and_no_invented_registration_button(web):
    c,app,_,_=web;seed(app)
    soup=BeautifulSoup(c.get('/public/announcements/1').text,'html.parser')
    assert soup.select_one('[data-public-back]').get_text(strip=True)=='← 返回公告清單'
    links=soup.select('[data-registration-action]')
    assert links==[]


def test_top_registration_links_keep_independent_workflows(web):
    from tests.test_linked_registration import FORM,FORM_HTML,TICKETS,tickets,BASE,NOW,parse_form,parse_tickets
    from app.services.source_history import record_public_version
    from app.models.public_announcements import PublicAnnouncement as P
    c,app,_,_=web;seed(app)
    form=parse_form(FORM_HTML,FORM);form['title']='合成2026教育推廣票券兌換'
    with app.state.database.transaction() as s:
        row=s.get(P,1)
        record_public_version(s,row,NOW,article={'text':'活動日期：2026年10月31日','rss_hash':row.content_hash,'related':[form,parse_tickets(tickets().encode(),TICKETS)]})
    soup=BeautifulSoup(c.get('/public/announcements/1').text,'html.parser')
    links=soup.select('[aria-label="公告主要操作"] [data-registration-action]')
    assert {(a.get_text(strip=True),a['href']) for a in links}=={('開啟兌換表單',FORM),('開啟票券頁',TICKETS)}
    assert all(a['target']=='_blank' and 'noopener' in a['rel'] for a in links)
