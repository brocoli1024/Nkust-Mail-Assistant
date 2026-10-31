import json
from bs4 import BeautifulSoup
from sqlalchemy import select,func
from tests.test_sessions import web,login
from tests.test_auth import oauth
from tests.test_public_pages import seed as public_seed
from tests.test_action_card_corrections import seed
from app.models.multi_user import Announcement
from app.models.todos import PrivateTodo
from app.models.action_cards import PrivateActionSnapshot,PrivateActionRevision
from tests.test_todo_pages import add_form


def payload(response):
    node=BeautifulSoup(response.text,'html.parser').select_one('[data-calendar-payload]')
    assert node is not None
    return node,json.loads(node['data-calendar-payload'])


def test_public_and_demo_calendar_controls_are_anonymous_and_wait_for_saved_card(web,monkeypatch):
    c,app,_,_=web;public_seed(app)
    def deny(*a,**kw):raise AssertionError('anonymous must not read session')
    monkeypatch.setattr(app.state.sessions,'resolve',deny)
    for path,kind in [('/public/announcements/1','public'),('/demo/announcements/demo-event','demo')]:
        r=c.get(path);assert r.status_code==200
        node,p=payload(r)
        assert p['source']['kind']==kind and p['context']=='current'
        assert node.has_attr('data-calendar-wait')
        assert 'calendar-controls.js' in r.text and 'calendar-ics.js' in r.text
        assert '啟動下載' in r.text and '不代表已加入' in r.text


def test_private_calendar_payload_is_minimal_escaped_owned_and_read_only(web):
    c,app,google,_=web;login(c);aid=seed(app.state.database)
    with app.state.database.transaction() as s:
        row=s.get(Announcement,aid);row.title='<img src=x onerror=alert(1)>'
        row.original_text='私有摘要'+('字'*1000)+'SECRET ORIGINAL TAIL'
    with app.state.database.transaction() as s:before=[s.scalar(select(func.count()).select_from(model)) for model in (PrivateTodo,PrivateActionSnapshot,PrivateActionRevision)]
    r=c.get(f'/announcements/{aid}');node,p=payload(r)
    assert not node.has_attr('data-calendar-wait') and p['source']['kind']=='private'
    assert 'SECRET ORIGINAL TAIL' not in json.dumps(p)
    assert '<img src=x' not in r.text and p['source']['title'].startswith('<img')
    assert 'action-card-store.js' not in r.text and 'todo-store.js' not in r.text
    assert '私人' in node.get_text() and '純文字' in node.get_text()
    with app.state.database.transaction() as s:assert before==[s.scalar(select(func.count()).select_from(model)) for model in (PrivateTodo,PrivateActionSnapshot,PrivateActionRevision)]
    c.cookies.clear();google.claims={'sub':'google-b','email':'b@example.invalid'};login(c)
    assert c.get(f'/announcements/{aid}').status_code==404
    assert 'SECRET ORIGINAL TAIL' not in c.get('/my/todos').text


def test_private_todo_calendar_uses_joined_snapshot_not_new_source(web):
    c,app,_,_=web;login(c);aid=seed(app.state.database)
    with app.state.database.transaction() as s:s.get(Announcement,aid).original_text='活動日期：2026年11月20日'
    assert c.post(f'/announcements/{aid}/todos',data=add_form(c,aid)).status_code==303
    with app.state.database.transaction() as s:s.get(Announcement,aid).original_text='活動日期：2026年11月21日'
    r=c.get('/my/todos');node,p=payload(r)
    assert p['context']=='snapshot' and p['dates']['event_date']['value']=='2026-11-20'
    assert 'calendar-controls.js' in r.text and '加入時快照' in node.get_text()
    assert 'data-calendar-dirty' not in str(node)
    assert payload(c.get(f'/announcements/{aid}'))[1]['dates']['event_date']['value']=='2026-11-21'


def test_device_todo_pages_load_only_shared_calendar_modules(web):
    c,_,_,_=web
    for path in ('/todos',):
        r=c.get(path);assert r.status_code==200
        assert 'calendar-ics.js' in r.text and 'calendar-controls.js' in r.text
