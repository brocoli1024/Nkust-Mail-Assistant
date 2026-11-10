"""Standard Web Push crypto with a bounded, TLS-verified pinned transport."""
from dataclasses import dataclass
import ipaddress,json,logging,socket,ssl,time
from urllib.parse import urlsplit
import requests
from concurrent.futures import ThreadPoolExecutor,TimeoutError as FutureTimeout
_LOG=logging.getLogger('nkust.push.transport')
_DNS_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix="push-dns")
from app.services.public_source import _PinnedHTTPSConnection
from .security import HOSTS,PushError

@dataclass(frozen=True)
class SendOutcome:
    status: str
    code: str

class PinnedPushSession:
    def __init__(self,resolver=socket.getaddrinfo,connection_factory=_PinnedHTTPSConnection):
        self.resolver,self.connection_factory=resolver,connection_factory
    def post(self,url,data=None,headers=None,timeout=None,**kwargs):
        # This adapter does not invoke requests networking, retry or redirect handlers.
        u=urlsplit(url)
        if (u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443)
            or u.query or u.fragment or not u.path.startswith('/') or len(url)>4096
            or any(ord(c)<33 or ord(c)>126 for c in url) or '\\' in url):raise PushError('PUSH_ENDPOINT_REJECTED')
        deadline=time.monotonic()+min(5,float(timeout or 5))
        future=_DNS_POOL.submit(self.resolver,u.hostname,443,type=socket.SOCK_STREAM)
        try:records=future.result(timeout=max(.001,deadline-time.monotonic()))
        except FutureTimeout:
            future.cancel();raise PushError('PUSH_DNS_TIMEOUT') from None
        addresses=sorted({r[4][0] for r in records})
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise PushError('PUSH_ENDPOINT_REJECTED')
        if not isinstance(data,(bytes,bytearray)) or len(data)>4096:raise PushError('PUSH_PAYLOAD_INVALID')
        if time.monotonic()>=deadline:raise PushError('PUSH_DNS_TIMEOUT')
        connection=self.connection_factory(u.hostname,addresses[0],max(.01,deadline-time.monotonic()))
        try:
            safe={k:v for k,v in (headers or {}).items() if k.lower() in ('authorization','ttl','content-encoding','content-type','crypto-key','encryption','urgency','topic')}
            safe['Content-Type']='application/octet-stream'
            connection.request('POST',u.path,body=data,headers=safe)
            if getattr(connection,'sock',None):connection.sock.settimeout(max(.01,deadline-time.monotonic()))
            response=connection.getresponse()
            # Provider bodies can echo capability URLs; neither read nor retain them.
            result=requests.Response();result.status_code=response.status;result._content=b''
            result.headers={};return result
        finally:connection.close()

class PushSender:
    def __init__(self,settings,cipher,webpush_fn=None):
        self.settings,self.cipher,self.webpush_fn=settings,cipher,webpush_fn
        self.timeout=5
    def send(self,subscription,payload,ttl,now):
        from pywebpush import webpush,WebPushException
        try:
            response=(self.webpush_fn or webpush)(subscription_info=subscription,
                data=json.dumps(payload,ensure_ascii=False,separators=(',',':')),
                vapid_private_key=self.settings.vapid_private_key,
                vapid_claims={'sub':self.settings.vapid_subject,'exp':int(now.timestamp())+3600},
                content_encoding='aes128gcm',ttl=max(0,int(ttl)),timeout=self.timeout,
                requests_session=PinnedPushSession(),verbose=False)
            status=response.status_code
        except WebPushException as error:
            response=error.response
            if response is None:
                _LOG.warning('PUSH_WEBPUSH_NO_RESPONSE')
                return SendOutcome('unknown','PUSH_OUTCOME_UNKNOWN')
            status=response.status_code
        except PushError:return SendOutcome('failed','PUSH_ENDPOINT_REJECTED')
        except Exception as error:
            # Fixed categories only. Exception text may contain capability URLs or credentials.
            if isinstance(error,(TimeoutError,requests.Timeout)):code='PUSH_TRANSPORT_TIMEOUT'
            elif isinstance(error,ssl.SSLError):code='PUSH_TLS_FAILED'
            elif isinstance(error,socket.gaierror):code='PUSH_DNS_FAILED'
            elif isinstance(error,AttributeError):code='PUSH_ADAPTER_ATTRIBUTE_ERROR'
            elif isinstance(error,OSError):code='PUSH_CONNECTION_FAILED'
            elif isinstance(error,(ValueError,TypeError)):code='PUSH_CRYPTO_OR_INPUT_FAILED'
            else:code='PUSH_TRANSPORT_EXCEPTION'
            _LOG.warning(code)
            return SendOutcome('unknown','PUSH_OUTCOME_UNKNOWN')
        if 200<=status<=202:return SendOutcome('accepted','PUSH_PROVIDER_ACCEPTED')
        if status in (404,410):return SendOutcome('invalid','PUSH_SUBSCRIPTION_EXPIRED')
        if status==429 or 500<=status<=599:return SendOutcome('retryable','PUSH_PROVIDER_RETRY')
        return SendOutcome('failed','PUSH_PROVIDER_REJECTED')
