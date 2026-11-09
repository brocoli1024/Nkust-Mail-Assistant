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
def current_epoch(client):return client.get('/api/push/reminders').json()['device']['epoch']
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
    response=client.put('/api/push/reminders/'+str(todo),json={'intent':cancel.model_dump(mode='json'),'expected_revision':None,'expected_epoch':current_epoch(client)},headers=headers)
    assert response.status_code==200
    create=intent(ref,todo,1)
    assert client.put('/api/push/reminders/'+str(todo),json={'intent':create.model_dump(mode='json'),'expected_revision':None,'expected_epoch':current_epoch(client)},headers=headers).status_code==409

def test_limits_survive_restart(web):
    client,app,_,_=web;enable(app);assert register(client).status_code==200
    headers={'Origin':str(client.base_url).rstrip('/')}
    from uuid import uuid4
    for _ in range(3):assert client.post('/api/push/test',json={'operation_id':str(uuid4()),'expected_epoch':current_epoch(client)},headers=headers).status_code==202
    assert client.post('/api/push/test',json={'operation_id':str(uuid4()),'expected_epoch':current_epoch(client)},headers=headers).status_code==429
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

def test_mutation_and_all_disable_require_matching_epoch(web):
    from uuid import uuid4
    from app.push.models import PushReminder,PushDevice
    from sqlalchemy import select
    client,app,_,_=web;enable(app);a=register(client).json();ref=seeded(app.state.database)
    # Browser cookies changed after an old tab's GET /reminders.
    client.cookies.clear()
    b=client.post('/api/push/device',json={'subscription':subscription('https://web.push.apple.com/new-device')},headers={'Origin':str(client.base_url).rstrip('/')}).json()
    assert a['epoch']!=b['epoch']
    payload=intent(ref,enabled=False);path='/api/push/reminders/'+str(payload.todo_id)
    body={'intent':payload.model_dump(mode='json'),'expected_revision':None,'expected_epoch':a['epoch']}
    headers={'Origin':str(client.base_url).rstrip('/')}
    assert client.put(path,json=body,headers=headers).status_code==409
    assert client.delete('/api/push/device',headers=headers).status_code in (403,415)
    assert client.request('DELETE','/api/push/device',json={},headers=headers).status_code==422
    assert client.request('DELETE','/api/push/device',json={'expected_epoch':a['epoch']},headers=headers).status_code==409
    with app.state.database.transaction() as session:
        assert not session.scalars(select(PushReminder)).all()
        assert session.scalar(select(PushDevice).where(PushDevice.epoch==b['epoch'])).enabled

def test_test_replay_does_not_rerun_dispatcher(web):
    from uuid import uuid4
    client,app,_,_=web;enable(app);d=register(client).json();calls=[]
    app.state.push_runner=lambda:(calls.append(1) or RunSummary())
    payload={'operation_id':str(uuid4()),'expected_epoch':d['epoch']}
    headers={'Origin':str(client.base_url).rstrip('/')}
    assert client.post('/api/push/test',json=payload,headers=headers).status_code==202
    assert client.post('/api/push/test',json=payload,headers=headers).status_code==202
    assert len(calls)==1

def test_real_serialized_client_payload_registers_at_api(web):
    import json,subprocess,shutil
    client,app,_,_=web;enable(app)
    value={**subscription(),'expirationTime':None}
    script=r"""
const fs=require('node:fs'),{createClient}=require('./app/static/web/push-client.js');
const value=JSON.parse(fs.readFileSync(0,'utf8'));let payload;
const registration={pushManager:{subscribe:()=>Promise.resolve({toJSON:()=>value})}};
const env={isSecureContext:true,PushManager:function(){},Notification:{permission:'default'},navigator:{userAgent:'Chrome',serviceWorker:{register:async()=>registration,ready:Promise.resolve(registration)}},matchMedia:()=>({matches:false}),atob:s=>Buffer.from(s,'base64').toString('binary'),setTimeout,clearTimeout,fetch:async(url,options)=>{if(options.body)payload=JSON.parse(options.body);return {ok:true,json:async()=>url.endsWith('/config')?{enabled:true,publicKey:'YQ'}:{epoch:'test'}};}};
(async()=>{const client=createClient(env);await client.prepare();await client.subscribeFromClick();process.stdout.write(JSON.stringify(payload));})().catch(()=>{process.exitCode=1;});
"""
    node=shutil.which('node');assert node
    result=subprocess.run([node,'-e',script],input=json.dumps(value),capture_output=True,text=True,check=True)
    payload=json.loads(result.stdout)
    assert set(payload['subscription'])=={'endpoint','keys'}
    response=client.post('/api/push/device',json=payload,headers={'Origin':str(client.base_url).rstrip('/')})
    assert response.status_code==200 and 'epoch' in response.json()

def test_reset_after_lost_disable_response_and_new_epoch_guard(web):
    client,app,_,_=web;enable(app);a=register(client).json();token=client.cookies.get('nkust_push_device');headers={'Origin':str(client.base_url).rstrip('/')}
    assert client.request('DELETE','/api/push/device',json={'expected_epoch':a['epoch']},headers=headers).status_code==200
    lost_headers={**headers,'Cookie':'nkust_push_device='+token}
    assert client.post('/api/push/device/reset',json={'expected_epoch':a['epoch']},headers=lost_headers).status_code==200
    b=register(client).json();assert b['epoch']!=a['epoch']
    rejected=client.post('/api/push/device/reset',json={'expected_epoch':a['epoch']},headers=headers)
    assert rejected.status_code==409
    assert client.get('/api/push/reminders').json()['device']['epoch']==b['epoch']
