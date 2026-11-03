from dataclasses import replace
from datetime import timedelta
from bs4 import BeautifulSoup
from sqlalchemy import select,func,event
import pytest
from tests.test_sessions import web
from tests.test_auth import oauth
from tests.test_office_mail_sync import document,NOW
from app.services.office_mail_sync import import_office_mail
from app.models.public_announcements import PublicAnnouncement as P
from app.models.action_cards import PrivateActionSnapshot
from tests.test_public_pages import seed as rss_seed

def seed_office(db,count=1):
    urls=[f'https://officemail.nkust.edu.tw/Mail/MailView/{70000+i}' for i in range(count)]
    def source(url):
        i=int(url.rsplit('/',1)[1])-70000
        body='建工校區11/5西門施工，請改走東門。' if i==0 else '全校各校區均停電。' if i==1 else '尚未提供地點的活動。' if i==2 else '旗津校區11/6停水。'
        return replace(document(url,body),published_at=NOW+timedelta(minutes=i))
    for offset in range(0,len(urls),20):assert import_office_mail(db,urls[offset:offset+20],source=source).status=='success'
    with db.transaction() as s:return list(s.scalars(select(P.id).where(P.source_key=='nkust-office-mail').order_by(P.id)))

def ids(response):return [int(n['data-office-id']) for n in BeautifulSoup(response.text,'html.parser').select('[data-office-id]')]

def test_priority_is_global_before_pagination_and_never_hides_other_campuses(web):
    c,app,_,_=web;values=seed_office(app.state.database,24)
    a=c.get('/public/office-mail?campus=jiangong&mode=priority')
    assert a.status_code==200 and ids(a)[:3]==[values[1],values[0],values[2]] and len(ids(a))==20
    b=c.get('/public/office-mail?campus=jiangong&mode=priority&page=2')
    assert len(ids(b))==4 and not set(ids(a))&set(ids(b)) and set(ids(a)+ids(b))==set(values)
    all_rows=c.get('/public/office-mail?campus=jiangong&mode=all')
    assert ids(all_rows)==list(reversed(values))[:20]
    assert '共 24 則' in a.text and '推播' in a.text


def test_detail_and_history_are_public_only_and_preserve_return_conditions(web):
    c,app,_,_=web;rss_seed(app);pid=seed_office(app.state.database)[0]
    r=c.get(f'/public/office-mail/{pid}?q=施工&category=&campus=jiangong&campus=nanzih&mode=priority&page=2')
    assert r.status_code==200 and 'no-store' in r.headers['cache-control']
    soup=BeautifulSoup(r.text,'html.parser')
    assert not soup.select('[aria-label="公告行動資訊卡"]')
    assert soup.select_one('[aria-label="公務公告重點整理"]')
    assert soup.select_one('details.office-original') and not soup.select_one('details.office-original').has_attr('open')
    back=soup.select_one('[data-office-back]')['href']
    assert 'campus=jiangong' in back and 'campus=nanzih' in back and 'page=2' in back and back.endswith(f'#office-{pid}')
    assert c.get(f'/public/office-mail/{pid}/history').status_code==200
    assert c.get(f'/public/announcements/{pid}').status_code==404
    assert '建工校區11/5' not in c.get('/public/announcements').text


@pytest.mark.parametrize('query',['campus=invalid','mode=unknown','page=0','category=invalid'])
def test_invalid_filters_rejected(web,query):
    c,_,_,_=web
    assert c.get('/public/office-mail?'+query).status_code==422


def test_empty_state_no_private_queries_or_writes_and_no_network(web,monkeypatch):
    c,app,_,_=web
    def forbidden(*a,**kw):raise AssertionError('Public GET must not fetch')
    monkeypatch.setattr('app.services.office_mail_source.fetch_office_mail',forbidden)
    statements=[]
    def capture(conn,cursor,statement,params,context,many):statements.append(statement.lower())
    event.listen(app.state.database.engine,'before_cursor_execute',capture)
    try:r=c.get('/public/office-mail')
    finally:event.remove(app.state.database.engine,'before_cursor_execute',capture)
    assert r.status_code==200 and '尚無收錄的公務公告' in r.text
    assert not any(any(k in sql for k in [' emails',' users',' announcements ', 'private_','web_sessions']) for sql in statements)
    assert not any(sql.lstrip().startswith(('insert','update','delete')) for sql in statements)
    assert '/assets/office-mail-preferences.js' in r.text


def test_training_detail_shows_all_options_and_escapes_original(web):
    from tests.test_office_mail_briefs import TRAINING
    c,app,_,_=web
    doc=replace(document(body=TRAINING+'\n<script>PRIVATE-XSS</script>'),title='合成培訓')
    import_office_mail(app.state.database,[doc.url],source=lambda u:doc)
    with app.state.database.transaction() as s:pid=s.scalar(select(P.id))
    r=c.get(f'/public/office-mail/{pid}')
    assert r.status_code==200
    for v in ['合成AI整合實務班','合成數據人才班','合成永續培訓班','符合資格','最高16,000元']:assert v in r.text
    assert '<script>PRIVATE-XSS</script>' not in r.text
