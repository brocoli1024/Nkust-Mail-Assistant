import base64
import hashlib
import hmac
import json
from urllib.parse import urlsplit,urlunsplit
from cryptography.fernet import Fernet

HOSTS=frozenset(('web.push.apple.com','fcm.googleapis.com','updates.push.services.mozilla.com'))
class PushError(ValueError):
    """Only a stable non-sensitive code may cross this boundary."""

def decode_key(value):
    if not isinstance(value,str) or not value or len(value)>256:raise PushError('PUSH_INVALID_KEY')
    try:return base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
    except Exception:raise PushError('PUSH_INVALID_KEY') from None

def validate_subscription(value):
    try:
        if set(value)!={'endpoint','keys'} or set(value['keys'])!={'p256dh','auth'}:raise ValueError()
        endpoint=value['endpoint'];u=urlsplit(endpoint)
        if (not isinstance(endpoint,str) or len(endpoint)>4096 or any(ord(c)<33 or ord(c)>126 for c in endpoint)
            or u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password
            or u.username is not None or u.password is not None or u.port not in (None,443) or u.fragment or u.query or not u.path.startswith('/')
            or '\\' in endpoint):raise ValueError()
        if len(decode_key(value['keys']['auth']))!=16:raise ValueError()
        pub=decode_key(value['keys']['p256dh'])
        if len(pub)!=65 or pub[0]!=4:raise ValueError()
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),pub)
    except Exception:raise PushError('PUSH_INVALID_SUBSCRIPTION') from None
    return {'endpoint':urlunsplit(('https',u.hostname,u.path,'','')),'keys':{'p256dh':value['keys']['p256dh'],'auth':value['keys']['auth']}}

def token_hash(token):
    if not isinstance(token,str) or not 43<=len(token)<=128:raise PushError('PUSH_DEVICE_UNAUTHORIZED')
    return hashlib.sha256(token.encode()).hexdigest()

class PushCipher:
    def __init__(self,key):self._fernet=Fernet(key.encode('ascii'))
    def encrypt(self,device_id,subscription_version,value):
        envelope={'context':f'push:{device_id}:{subscription_version}','value':value}
        return self._fernet.encrypt(json.dumps(envelope).encode()).decode()
    def decrypt(self,device_id,subscription_version,value):
        try:
            envelope=json.loads(self._fernet.decrypt(value.encode()))
            if envelope['context']!=f'push:{device_id}:{subscription_version}':raise ValueError()
            return envelope['value']
        except Exception:raise PushError('PUSH_SUBSCRIPTION_UNAVAILABLE') from None

def fingerprint(key,value):return hmac.new(key,value.encode(),hashlib.sha256).hexdigest()
