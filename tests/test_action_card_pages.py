from urllib.parse import urlencode
from bs4 import BeautifulSoup
import pytest
from sqlalchemy import select,func
from tests.test_sessions import web,login,csrf
from tests.test_auth import oauth
from tests.test_public_pages import seed as public_seed
from tests.test_action_card_corrections import seed
from app.models.action_cards import PrivateActionRevision as R


def test_three_detail_cards_and_no_get_writes(web):
    client,app,_,_=web
    public_seed(app)
    for path in ('/public/announcements/1','/demo/announcements/demo-event'):
        r=client.get(path)
        assert r.status_code==200
        card=BeautifulSoup(r.text,'html.parser').select_one('[aria-label="公告行動資訊卡"]')
        assert card and '活動日期' in card.text and '截止' in card.text and '待確認' in card.text
        assert '不代表你已符合資格' in card.text
    login(client);aid=seed(app.state.database)
    r=client.get('/announcements/'+str(aid))
    assert r.status_code==200 and '依目前登入帳號保存至本站' in r.text
    assert '/assets/action-card-store.js' not in r.text and 'data-card-payload' not in r.text
    assert r.headers['referrer-policy']=='same-origin'
    with app.state.database.transaction() as s:assert s.scalar(select(func.count()).select_from(R))==0


def form(client,aid):
    r=client.get('/announcements/'+str(aid))
    soup=BeautifulSoup(r.text,'html.parser')
    return {'csrf_token':csrf(client),'operation':'save','baseline_hash':soup.select_one('[name="baseline_hash"]')['value'],
        'expected_revision':soup.select_one('[name="expected_revision"]')['value'],
        'materials.mode':'value','materials.value':'我的材料<script>x</script>'}


def test_private_post_and_history(web):
    client,app,_,_=web;login(client);aid=seed(app.state.database)
    payload=form(client,aid)
    r=client.post(f'/announcements/{aid}/action-card/corrections',data=payload,headers={'origin':'http://localhost'})
    assert r.status_code==303
    r=client.get(r.headers['location'])
    assert '我的材料&lt;script&gt;' in r.text and '<script>x</script>' not in r.text
    with app.state.database.transaction() as s:sid=s.scalar(select(R.snapshot_id))
    assert client.get(f'/action-cards/history/{sid}').status_code==200
    assert client.post(f'/announcements/{aid}/action-card/corrections',data=payload).status_code==409


@pytest.mark.parametrize('update,headers,code',[
    ({'csrf_token':'wrong'},{},403),({}, {'origin':'null'},403),({}, {'origin':'https://other.invalid'},403),
    ({'owner':'2'},{},422),({'expected_revision':'-1'},{},422),
    ({'deadline.mode':'value','deadline.value':'2026-02-30','deadline.confirmed':'on'},{},422)])
def test_bad_correction_cannot_write(web,update,headers,code):
    client,app,_,_=web;login(client);aid=seed(app.state.database)
    payload=form(client,aid);payload.update(update)
    assert client.post(f'/announcements/{aid}/action-card/corrections',data=payload,headers=headers).status_code==code
    with app.state.database.transaction() as s:assert s.scalar(select(func.count()).select_from(R))==0


def test_private_save_timestamp_and_error_contracts(web,monkeypatch):
    from app.services import action_card_corrections as service
    from app.models.action_cards import PrivateActionSnapshot
    client,app,google,_=web;login(client);aid=seed(app.state.database)
    payload=form(client,aid);path=f'/announcements/{aid}/action-card/corrections'
    assert client.post(path,data=payload).status_code==303
    assert '保存時間（台灣）' in client.get(f'/announcements/{aid}').text
    assert client.post(path,content=b'x'* (128*1024+1),headers={'content-type':'application/x-www-form-urlencoded'}).status_code==413
    assert client.post(path,json=payload).status_code==415
    assert client.post(path,content='csrf_token=a&csrf_token=b',headers={'content-type':'application/x-www-form-urlencoded'}).status_code==422
    with app.state.database.transaction() as s:sid=s.scalar(select(PrivateActionSnapshot.id))
    client.post('/logout',data={'csrf_token':csrf(client)})
    assert client.post(path,data=payload).status_code==401
    google.claims={'sub':'google-b','email':'b@example.invalid','name':'B'};login(client)
    assert client.get(f'/action-cards/history/{sid}').status_code==404
    payload['csrf_token']=csrf(client)
    assert client.post(path,data=payload).status_code==404


def test_corrupt_saved_patch_is_not_treated_as_empty(web):
    client,app,_,_=web;login(client);aid=seed(app.state.database)
    payload=form(client,aid)
    client.post(f'/announcements/{aid}/action-card/corrections',data=payload)
    with app.state.database.transaction() as s:s.scalar(select(R)).overrides={'fields':{'owner':{'mode':'value','value':'wrong'}}}
    r=client.get(f'/announcements/{aid}')
    assert r.status_code==503 and '修正歷史讀取不完整' in r.text
    assert 'wrong' not in r.text


def test_corrupt_revision_keeps_owned_source_readable(web):
    client,app,_,_=web;login(client);aid=seed(app.state.database)
    payload=form(client,aid)
    client.post(f'/announcements/{aid}/action-card/corrections',data=payload)
    with app.state.database.transaction() as s:s.scalar(select(R)).overrides={'fields':{'owner':{'mode':'value','value':'wrong'}}}
    r=client.get(f'/announcements/{aid}')
    assert r.status_code==503 and '合成本文' in r.text
    assert '尚未覆寫' in r.text


def test_snapshot_list_is_linked_and_owner_scoped(web):
    client,app,google,_=web;login(client);aid=seed(app.state.database)
    client.post(f'/announcements/{aid}/action-card/corrections',data=form(client,aid))
    assert f'/action-cards/sources/{aid}' in client.get(f'/announcements/{aid}').text
    r=client.get(f'/action-cards/sources/{aid}')
    assert r.status_code==200 and '/action-cards/history/' in r.text
    client.post('/logout',data={'csrf_token':csrf(client)})
    google.claims={'sub':'google-b','email':'b@example.invalid','name':'B'};login(client)
    assert client.get(f'/action-cards/sources/{aid}').status_code==404


def test_history_read_failure_keeps_owned_snapshot(web,monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import SQLAlchemyError
    client,app,_,_=web;login(client);aid=seed(app.state.database)
    client.post(f'/announcements/{aid}/action-card/corrections',data=form(client,aid))
    with app.state.database.transaction() as s:sid=s.scalar(select(R.snapshot_id))
    original=Session.scalars
    def fail_revision_read(self,statement,*args,**kwargs):
        if 'private_action_revisions' in str(statement):raise SQLAlchemyError('synthetic read failure')
        return original(self,statement,*args,**kwargs)
    monkeypatch.setattr(Session,'scalars',fail_revision_read)
    r=client.get(f'/action-cards/history/{sid}')
    assert r.status_code==503 and '合成本文' in r.text
    assert 'synthetic read failure' not in r.text
