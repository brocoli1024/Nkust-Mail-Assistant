from bs4 import BeautifulSoup
import pytest
from sqlalchemy import select,func
from tests.test_sessions import web,login,csrf
from tests.test_auth import oauth
from tests.test_action_card_corrections import seed
from app.models.todos import PrivateTodo

def add_form(client,aid):
    s=BeautifulSoup(client.get(f'/announcements/{aid}').text,'html.parser')
    f=s.select_one('[data-private-add-todo]')
    assert f is not None
    return {i['name']:i.get('value','') for i in f.select('input[name]')}

def test_private_todo_flow_and_home_priority(web):
    c,app,_,_=web;login(c);aid=seed(app.state.database)
    payload=add_form(c,aid);path=f'/announcements/{aid}/todos'
    r=c.post(path,data=payload,headers={'origin':'http://localhost'})
    assert r.status_code==303 and c.post(path,data=payload).status_code==409
    with app.state.database.transaction() as s:tid=s.scalar(select(PrivateTodo.id))
    text=c.get('/my/todos').text
    assert '合成公告' in text and '明天' in text and '09:00' in text
    assert c.get('/dashboard').text.index('我的待辦')<c.get('/dashboard').text.index('校園公告</h2>')
    assert c.post(f'/my/todos/{tid}',data={'csrf_token':csrf(c),'expected_revision':'1','operation':'complete'}).status_code==303
    assert '合成公告' in c.get('/my/todos?view=done').text
    assert '合成公告' not in c.get('/my/todos?view=active').text

@pytest.mark.parametrize('changes,headers,code', [({'csrf_token':'bad'},{},403),({}, {'origin':'null'},403),
    ({},{'origin':'https://other.invalid'},403),({'owner':'2'},{},422),({'expected_revision':'-1'},{},422)])
def test_invalid_todo_form_no_write(web,changes,headers,code):
    c,app,_,_=web;login(c);aid=seed(app.state.database);p=add_form(c,aid);p.update(changes)
    assert c.post(f'/announcements/{aid}/todos',data=p,headers=headers).status_code==code
    with app.state.database.transaction() as s:assert s.scalar(select(func.count()).select_from(PrivateTodo))==0

def test_todo_account_isolation_and_errors(web,monkeypatch):
    c,app,google,_=web;login(c);aid=seed(app.state.database);p=add_form(c,aid)
    c.post(f'/announcements/{aid}/todos',data=p)
    with app.state.database.transaction() as s:tid=s.scalar(select(PrivateTodo.id))
    assert c.post(f'/my/todos/{tid}',json={}).status_code==415
    assert c.post(f'/my/todos/{tid}',content='x'*4097,headers={'content-type':'application/x-www-form-urlencoded'}).status_code==413
    c.post('/logout',data={'csrf_token':csrf(c)})
    assert c.post(f'/my/todos/{tid}',data={}).status_code==401
    google.claims={'sub':'google-b','email':'b@example.invalid'};login(c)
    assert '合成公告' not in c.get('/my/todos').text
    assert c.post(f'/my/todos/{tid}',data={'csrf_token':csrf(c),'expected_revision':'1','operation':'remove'}).status_code==404
    import app.api.todos as api
    from app.services.action_card_corrections import CorrectionUnavailable
    def fail(*args,**kw):raise CorrectionUnavailable()
    monkeypatch.setattr(api,'list_private_todos',fail)
    r=c.get('/my/todos')
    assert r.status_code==503 and '讀取失敗' in r.text and '尚無待辦' not in r.text


def test_anonymous_todos_and_no_private_device_payload(web,monkeypatch):
    c,app,_,_=web
    import app.core.session as sessions
    def deny(*a,**kw):raise AssertionError('anonymous device page must not resolve sessions')
    monkeypatch.setattr(sessions.SessionService,'resolve',deny)
    r=c.get('/todos')
    assert r.status_code==200 and '此裝置' in r.text and 'todo-store.js' in r.text
    assert 'data-todo-list' in c.get('/').text
    assert 'data-device-todo' in c.get('/demo/announcements/demo-event').text


def test_snooze_across_midnight_rejects_stale_displayed_target(web,monkeypatch):
    from datetime import datetime,timezone
    import app.services.todos as service
    c,app,_,_=web;login(c);aid=seed(app.state.database)
    c.post(f'/announcements/{aid}/todos',data=add_form(c,aid))
    before=datetime(2026,10,29,15,59,tzinfo=timezone.utc)
    real_clock=service.clock
    monkeypatch.setattr(service,'clock',lambda now=None: real_clock(now or before))
    soup=BeautifulSoup(c.get('/my/todos').text,'html.parser')
    f=next(f for f in soup.select('form') if f.select_one('[name="operation"][value="snooze"]'))
    payload={i['name']:i.get('value','') for i in f.select('input[name]')}
    target=f.select_one('[name="snooze_until"]')
    assert target and target['value']=='2026-10-30T01:00:00+00:00'
    monkeypatch.setattr(service,'clock',lambda now=None:real_clock(now or datetime(2026,10,29,16,1,tzinfo=timezone.utc)))
    r=c.post(f['action'],data=payload)
    assert r.status_code==409
    with app.state.database.transaction() as s:
        row=s.scalar(select(PrivateTodo));assert row.status=='active' and row.revision==1


def test_private_snooze_html_has_utc_offset_and_target(web):
    c,app,_,_=web;login(c);aid=seed(app.state.database);c.post(f'/announcements/{aid}/todos',data=add_form(c,aid))
    soup=BeautifulSoup(c.get('/my/todos').text,'html.parser');f=next(f for f in soup.select('form') if f.select_one('[name="operation"][value="snooze"]'))
    payload={i['name']:i.get('value','') for i in f.select('input[name]')}
    assert c.post(f['action'],data=payload).status_code==303
    soup=BeautifulSoup(c.get('/my/todos?view=snoozed').text,'html.parser')
    markers=soup.select('[data-snoozed-until]')
    assert markers and all(n['data-snoozed-until'].endswith('+00:00') for n in markers if n['data-snoozed-until'])
