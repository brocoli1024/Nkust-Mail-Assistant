from dataclasses import replace
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from tests.test_sessions import web
from tests.test_auth import oauth
from tests.test_push_devices import repository,subscription,NOW
from tests.test_push_intents import seeded,intent
from app.push.config import PushSettings
from app.push.dispatcher import RunSummary

ORIGIN='https://testserver'
def enable(app):
    app.state.push_settings=PushSettings(enabled=True,trigger_secret='s'*48)
    app.state.push_repo=repository(app.state.database)
    app.state.push_runner=lambda:RunSummary()
def register(client):return client.post('/api/push/device',json={'subscription':subscription()},headers={'Origin':str(client.base_url).rstrip('/')})
def test_disabled_routes_and_redacted_errors(web):
    client,app,_,_=web
    assert client.get('/api/push/config').json()=={'enabled':False,'publicKey':None}
    assert register(client).status_code==404
    enable(app)
    result=register(client);assert result.status_code==200
    assert 'endpoint' not in result.text and 'keys' not in result.text
    assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']
def test_cross_origin_and_google_identity_cannot_authorize(web):
    client,app,_,_=web;enable(app)
    for headers in [{},{'Origin':'https://evil.invalid'},{'Origin':'null'}]:
        assert client.post('/api/push/device',json={'subscription':subscription()},headers=headers).status_code==403
    assert client.get('/api/push/reminders').status_code==401
    assert register(client).status_code==200
    assert client.get('/api/push/reminders').json()['items']==[]
    assert client.put('/api/push/reminders/invalid',json={},headers={'Origin':str(client.base_url).rstrip('/')}).status_code==422

def test_stale_cancel_create_http_order(web):
    from uuid import uuid4
    client,app,_,_=web;enable(app);assert register(client).status_code==200
    ref=seeded(app.state.database);todo=uuid4();headers={'Origin':str(client.base_url).rstrip('/')}
    cancel=intent(ref,todo,2,False)
    response=client.put('/api/push/reminders/'+str(todo),json={'intent':cancel.model_dump(mode='json'),'expected_revision':None},headers=headers)
    assert response.status_code==200
    create=intent(ref,todo,1)
    assert client.put('/api/push/reminders/'+str(todo),json={'intent':create.model_dump(mode='json'),'expected_revision':None},headers=headers).status_code==409

def test_limits_survive_restart(web):
    client,app,_,_=web;enable(app);assert register(client).status_code==200
    headers={'Origin':str(client.base_url).rstrip('/')}
    from uuid import uuid4
    for _ in range(3):assert client.post('/api/push/test',json={'operation_id':str(uuid4())},headers=headers).status_code==202
    assert client.post('/api/push/test',json={'operation_id':str(uuid4())},headers=headers).status_code==429
    assert client.post('/internal/push/run',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.post('/internal/push/run',headers={'Authorization':'Bearer '+'s'*48}).status_code==200
    assert client.post('/internal/push/run',json={},headers={'Authorization':'Bearer '+'s'*48}).status_code==422

def test_json_unknown_private_fields_are_rejected(web):
    client,app,_,_=web;enable(app)
    r=client.post('/api/push/device',json={'subscription':subscription(),'email':'PRIVATE_MARKER'},headers={'Origin':str(client.base_url).rstrip('/')})
    assert r.status_code==422 and 'PRIVATE_MARKER' not in r.text

def test_updated_source_is_reported_before_due_time(web):
    from tests.test_push_intents import seeded,intent
    from sqlalchemy import select
    from app.models.public_announcements import PublicAnnouncement
    client,app,_,_=web;enable(app);registered=register(client).json();ref=seeded(app.state.database)
    from uuid import UUID
    app.state.push_repo.apply_intent(UUID(registered['id']),intent(ref),None,NOW)
    with app.state.database.transaction() as s:s.scalar(select(PublicAnnouncement)).excerpt='新期限'
    assert client.get('/api/push/reminders').json()['items'][0]['status']=='needs_review'
