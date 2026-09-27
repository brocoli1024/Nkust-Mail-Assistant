from sqlalchemy import select,func
import pytest

from app.database.user_mail import UserSyncLease
from app.models.multi_user import Email
from app.services.user_sync_service import UserSyncService
from app.services.user_gmail_service import GmailReauthorizationRequired
from tests.test_sessions import web, login, csrf
from tests.test_auth import oauth
from tests.test_api import mail
from tests.test_sync_multi_user import FakeMailbox


def setup_sync(web):
    client, app, _, _ = web
    calls=[]
    def factory(user):
        calls.append(user.id)
        return FakeMailbox({'sample':mail('sample')})
    app.state.sync_service=UserSyncService(app.state.database,factory)
    return client,app,calls


def test_anonymous_sync_rejected_before_gmail(web):
    client,app,calls=setup_sync(web)
    assert client.post('/sync',json={'limit':5}).status_code==401
    assert calls==[]


def test_sync_authenticated_json_and_repeat(web):
    client,app,calls=setup_sync(web)
    login(client)
    header={'x-csrf-token':csrf(client)}
    result=client.post('/sync',json={'limit':5},headers=header)
    assert result.status_code==200 and result.json()['announcements_created']==3
    assert client.post('/sync',json={'limit':5},headers=header).json()['emails_skipped']==1
    assert calls==[client.get('/api/me').json()['id']]*2


@pytest.mark.parametrize('body',[{'user_id':2},{'limit':True},{'limit':101},{'force':True},[]])
def test_cannot_select_other_user_or_supply_invalid_options(web,body):
    client,app,calls=setup_sync(web)
    login(client)
    response=client.post('/sync',json=body,headers={'x-csrf-token':csrf(client)})
    assert response.status_code==422 and calls==[]


def test_missing_csrf_cross_origin_and_get_never_sync(web):
    client,app,calls=setup_sync(web)
    login(client)
    assert client.post('/sync',json={}).status_code==403
    assert client.post('/sync',json={},headers={'x-csrf-token':csrf(client),'origin':'https://evil.invalid'}).status_code==403
    assert client.get('/sync').status_code==405
    assert calls==[]


def test_two_logged_in_accounts_only_sync_their_own_mail(web):
    client,app,calls=setup_sync(web)
    login(client)
    first=client.get('/api/me').json()['id']
    client.post('/sync',json={},headers={'x-csrf-token':csrf(client)})
    client.cookies.clear()
    web[2].claims={'sub':'google-b','email':'b@example.invalid'}
    login(client)
    second=client.get('/api/me').json()['id']
    result=client.post('/sync',json={},headers={'x-csrf-token':csrf(client)}).json()
    assert result['database_counts']['emails']==1 and calls==[first,second]
    with app.state.database.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Email))==2


def test_busy_and_reauthorization_statuses(web):
    client,app,calls=setup_sync(web)
    login(client)
    headers={'x-csrf-token':csrf(client)}
    uid=client.get('/api/me').json()['id']
    lease=UserSyncLease(app.state.database,uid)
    lease.acquire()
    try:
        assert client.post('/sync',json={},headers=headers).status_code==409
        assert calls==[]
    finally:
        lease.release()
    def fail(user):
        raise GmailReauthorizationRequired('GMAIL_REAUTHORIZE')
    app.state.sync_service=UserSyncService(app.state.database,fail)
    response=client.post('/sync',json={},headers=headers)
    assert response.status_code==401 and response.json()['error']=='GMAIL_REAUTHORIZE'


def test_form_returns_readable_counts_without_mail_body(web):
    client,app,calls=setup_sync(web)
    login(client)
    response=client.post('/sync',data={'limit':'5','csrf_token':csrf(client)})
    assert response.status_code==200 and '本次同步完成' in response.text
    assert '合成公告' not in response.text
    assert len(calls)==1


def test_form_policy_preserves_origin_and_null_origin_stays_blocked(web):
    client,app,calls=setup_sync(web)
    login(client)
    dashboard=client.get('/dashboard')
    assert dashboard.headers['referrer-policy']=='same-origin'
    assert client.get('/settings').headers['referrer-policy']=='same-origin'
    data={'limit':'5','csrf_token':csrf(client)}
    # Browser form submissions from no-referrer documents send Origin:null.
    assert client.post('/sync',data=data,headers={'origin':'null'}).status_code==403
    assert calls==[]
    response=client.post('/sync',data=data,headers={'origin':'http://localhost','sec-fetch-site':'same-origin'})
    assert response.status_code==200 and len(calls)==1
    assert client.get('/auth/google/callback').headers['referrer-policy']=='no-referrer'
