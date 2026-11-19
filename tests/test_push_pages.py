from bs4 import BeautifulSoup
from tests.test_sessions import web
from tests.test_auth import oauth
from tests.test_office_mail_pages import seed_office

def test_office_compact_todo_without_action_card(web):
    client,app,_,_=web;pid=seed_office(app.state.database)[0]
    r=client.get(f'/public/office-mail/{pid}');assert r.status_code==200
    soup=BeautifulSoup(r.text,'html.parser')
    assert soup.select_one('[data-office-todo-card]')
    assert not soup.select_one('[aria-label="公告行動資訊卡"]')
    assert soup.select_one('[aria-label="公務公告重點整理"]')
    assert soup.select_one('script[src*="todo-store.js"]')

def test_device_controls_are_opt_in_and_public(web,monkeypatch):
    client,app,_,_=web
    monkeypatch.setattr(app.state.sessions,'resolve',lambda *a:(_ for _ in ()).throw(AssertionError('private read')))
    r=client.get('/todos');assert r.status_code==200
    assert '此裝置提醒設定' in r.text and '自行開啟' in r.text
    assert 'push-client.js' in r.text and 'push-ui.js' in r.text
    assert r.headers['referrer-policy']=='same-origin'
