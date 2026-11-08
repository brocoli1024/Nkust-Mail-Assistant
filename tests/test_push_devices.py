from datetime import datetime, timezone
import json
import secrets
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text
from tests.test_multi_user_database import database
from app.push.config import PushSettings
from app.push.security import PushCipher, PushError
from app.push.repository import PushRepository

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)

def subscription(endpoint='https://fcm.googleapis.com/fcm/send/synthetic'):
    import base64
    enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
    pub=ec.derive_private_key(1,ec.SECP256R1()).public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
    return {'endpoint':endpoint, 'keys':{'p256dh':enc(pub),'auth':enc(b'a'*16)}}

def repository(db):
    return PushRepository(db, PushCipher(Fernet.generate_key().decode()), b'k'*32)

def test_disabled_needs_no_push_keys(monkeypatch):
    monkeypatch.delenv('NKUST_PUSH_ENABLED', raising=False)
    assert not PushSettings.from_env().enabled
    with pytest.raises(ValueError): PushSettings(enabled=True).validate()
    assert 'secret-value' not in repr(PushSettings(trigger_secret='secret-value'))

def test_device_isolation_and_redaction(database):
    db,_=database; repo=repository(db)
    a=repo.register_device('a'*43,subscription(),NOW)
    b=repo.register_device('b'*43,subscription('https://web.push.apple.com/synthetic'),NOW)
    assert a.id != b.id and a.epoch != b.epoch
    assert repo.authenticate('a'*43,NOW).id==a.id
    with pytest.raises(PushError): repo.authenticate('c'*43,NOW)
    with db.engine.connect() as c:
        row=c.execute(text('select * from push_devices where id=:id'),{'id':str(a.id)}).mappings().one()
        serialized=json.dumps(dict(row),default=str)
        assert 'fcm.googleapis.com' not in serialized and 'a'*43 not in serialized
    assert 'fcm.googleapis.com' not in repr(a)

def test_endpoint_cannot_be_claimed_by_new_device(database):
    db,_=database; repo=repository(db)
    repo.register_device('a'*43,subscription(),NOW)
    with pytest.raises(PushError,match='PUSH_SUBSCRIPTION_IN_USE'):
        repo.register_device('b'*43,subscription(),NOW)

def test_cipher_context_and_invalid_subscription(database):
    db,_=database;repo=repository(db)
    from uuid import uuid4
    a,b=uuid4(),uuid4();cipher=repo.cipher
    encrypted=cipher.encrypt(a,1,subscription())
    assert cipher.decrypt(a,1,encrypted)==subscription()
    with pytest.raises(PushError):cipher.decrypt(b,1,encrypted)
    for url in ['http://fcm.googleapis.com/x','https://evil.invalid/x','https://user@fcm.googleapis.com/x','https://fcm.googleapis.com:444/x']:
        with pytest.raises(PushError):repo.register_device(secrets.token_urlsafe(32),subscription(url),NOW)

def test_0011_preserves_0010_and_public_role_denied(database):
    db,config=database
    from alembic import command
    command.downgrade(config,'0010')
    with db.transaction() as s:assert s.scalar(text('select count(*) from users'))==2
    command.upgrade(config,'head')
    with db.engine.connect() as c:
        assert c.scalar(text('select count(*) from users'))==2
        assert c.scalar(text('select version_num from alembic_version'))=='0011'
        assert all(n in inspect(c).get_table_names() for n in ['push_devices','push_reminders','push_operations','push_leases','push_rate_buckets'])
        if c.dialect.name=='postgresql':
            role=c.scalar(text("select 1 from pg_roles where rolname='nkust_public_sync'"))
            if role:
                for name in ['push_devices','push_reminders','push_operations','push_leases','push_rate_buckets']:
                    assert not c.scalar(text("select has_table_privilege('nkust_public_sync', :t, 'SELECT')"),{'t':name})
