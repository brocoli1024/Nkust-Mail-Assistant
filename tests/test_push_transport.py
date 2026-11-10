from datetime import datetime,timezone
import socket
from types import SimpleNamespace
import pytest
from tests.test_push_devices import subscription,NOW
from app.push.transport import PinnedPushSession,PushSender
from app.push.security import PushError

def dns(host,port,**kw):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
class Connection:
    last=None
    status=201
    def __init__(self,host,address,timeout):self.host,self.address=host,address;Connection.last=self
    def request(self,method,path,body=None,headers=None):self.method=method;self.path=path
    def getresponse(self):return SimpleNamespace(status=self.status,getheaders=lambda:[],read=lambda n:b'')
    def close(self):pass

def test_endpoint_public_dns_and_no_redirect():
    session=PinnedPushSession(resolver=dns,connection_factory=Connection)
    response=session.post(subscription()['endpoint'],data=b'encrypted',headers={},timeout=3)
    assert response.status_code==201 and Connection.last.address=='8.8.8.8'
    assert Connection.last.method=='POST'
    for host in ['https://evil.invalid/x','https://fcm.googleapis.com:444/x','https://user@fcm.googleapis.com/x']:
        with pytest.raises(PushError):session.post(host,data=b'x',timeout=1)
    bad=PinnedPushSession(resolver=lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))],connection_factory=Connection)
    with pytest.raises(PushError):bad.post(subscription()['endpoint'],data=b'x',timeout=1)
    Connection.status=302
    assert session.post(subscription()['endpoint'],data=b'x',timeout=1).status_code==302
    Connection.status=201

def test_timeout_is_unknown_not_retry(caplog):
    def timeout(**kw):raise TimeoutError('sensitive endpoint must not escape')
    sender=PushSender(SimpleNamespace(vapid_private_key='x',vapid_subject='mailto:test@example.invalid'),None,webpush_fn=timeout)
    result=sender.send(subscription(),{'id':'x'},60,NOW)
    assert result.status=='unknown' and 'sensitive' not in repr(result)
    assert 'PUSH_TRANSPORT_TIMEOUT' in caplog.text
    assert 'sensitive endpoint' not in caplog.text

def test_standard_library_receives_pinned_session():
    calls=[]
    def fake(**kw):calls.append(kw);return SimpleNamespace(status_code=201)
    sender=PushSender(SimpleNamespace(vapid_private_key='x',vapid_subject='mailto:test@example.invalid'),None,webpush_fn=fake)
    assert sender.send(subscription(),{'id':'test'},15,NOW).status=='accepted'
    assert isinstance(calls[0]['requests_session'],PinnedPushSession)
    assert calls[0]['ttl']==15 and calls[0]['content_encoding']=='aes128gcm'

def test_real_webpush_crypto_uses_public_adapter(monkeypatch):
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
    enc=lambda value:base64.urlsafe_b64encode(value).decode().rstrip('=')
    private=ec.generate_private_key(ec.SECP256R1())
    recipient=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
    sub={'endpoint':'https://fcm.googleapis.com/fcm/send/synthetic','keys':{'p256dh':enc(recipient),'auth':enc(b'a'*16)}}
    captured=[]
    def post(self,url,data=None,headers=None,timeout=None,**kw):
        captured.append((data,headers));return SimpleNamespace(status_code=201,text='',headers={})
    monkeypatch.setattr(PinnedPushSession,'post',post)
    settings=SimpleNamespace(vapid_private_key=enc(private.private_numbers().private_value.to_bytes(32,'big')),vapid_subject='mailto:test@example.invalid')
    result=PushSender(settings,None).send(sub,{'title':'合成通知'},60,datetime.now(timezone.utc))
    assert result.status=='accepted' and captured and isinstance(captured[0][0],bytes)
    assert b'title' not in captured[0][0]
    assert any(k.lower()=='authorization' for k in captured[0][1])

def test_dns_resolution_respects_budget():
    import time
    def slow(*args,**kw):time.sleep(.2);return dns(*args,**kw)
    start=time.monotonic()
    with pytest.raises((PushError,TimeoutError)):
        PinnedPushSession(resolver=slow,connection_factory=Connection).post(subscription()['endpoint'],data=b'x',timeout=.01)
    assert time.monotonic()-start<.15


def test_adapter_exception_diagnostic_never_logs_private_detail(caplog):
    def broken(**kw):raise AttributeError('private subscription and credential')
    sender=PushSender(SimpleNamespace(vapid_private_key='x',vapid_subject='https://example.invalid'),None,webpush_fn=broken)
    assert sender.send(subscription(),{'id':'test'},60,NOW).status=='unknown'
    assert 'PUSH_ADAPTER_ATTRIBUTE_ERROR' in caplog.text
    assert 'private subscription' not in caplog.text
