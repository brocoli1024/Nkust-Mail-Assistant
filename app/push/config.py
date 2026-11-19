from dataclasses import dataclass, field
import os

@dataclass(frozen=True)
class PushSettings:
    enabled: bool = False
    vapid_public_key: str = ''
    vapid_private_key: str = field(default='',repr=False)
    vapid_subject: str = ''
    trigger_secret: str = field(default='',repr=False)
    rate_hash_key: str = field(default='',repr=False)
    max_devices: int = 2000
    max_active: int = 10000
    per_device: int = 20

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv('NKUST_PUSH_ENABLED','').lower()=='true',
            **{name:os.getenv('NKUST_PUSH_'+name.upper(),'') for name in
               ('vapid_public_key','vapid_private_key','vapid_subject','trigger_secret','rate_hash_key')}).validate()

    def validate(self):
        if self.enabled:
            if not all((self.vapid_public_key,self.vapid_private_key,self.vapid_subject,
                        len(self.trigger_secret)>=32,len(self.rate_hash_key)>=32)):
                raise ValueError('PUSH_CONFIGURATION_INVALID')
            if not self.vapid_subject.startswith(('mailto:','https://')):
                raise ValueError('PUSH_CONFIGURATION_INVALID')
            from cryptography.hazmat.primitives.asymmetric import ec
            from .security import decode_key
            try:
                raw=decode_key(self.vapid_public_key)
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),raw)
                private=ec.derive_private_key(int.from_bytes(decode_key(self.vapid_private_key),'big'),ec.SECP256R1())
                from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
                if private.public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)!=raw:raise ValueError()
                # Exercise the actual library's public signing API before accepting settings.
                # A syntactically valid HTTPS URI may still be rejected by its subject validator.
                from py_vapid import Vapid
                import time
                Vapid.from_string(self.vapid_private_key).sign({'sub':self.vapid_subject,
                    'aud':'https://web.push.apple.com','exp':int(time.time())+3600})
            except Exception:raise ValueError('PUSH_CONFIGURATION_INVALID') from None
        return self
