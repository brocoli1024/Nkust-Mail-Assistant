import io
from app.push.keygen import create_values,main
from app.push.config import PushSettings

def test_generated_values_match_validated_config_and_are_distinct():
    a=create_values();b=create_values()
    assert a['NKUST_PUSH_VAPID_PUBLIC_KEY']!=b['NKUST_PUSH_VAPID_PUBLIC_KEY']
    assert a['NKUST_PUSH_TRIGGER_SECRET']!=a['NKUST_PUSH_RATE_HASH_KEY']
    PushSettings(enabled=True,vapid_public_key=a['NKUST_PUSH_VAPID_PUBLIC_KEY'],vapid_private_key=a['NKUST_PUSH_VAPID_PRIVATE_KEY'],vapid_subject=a['NKUST_PUSH_VAPID_SUBJECT'],trigger_secret=a['NKUST_PUSH_TRIGGER_SECRET'],rate_hash_key=a['NKUST_PUSH_RATE_HASH_KEY']).validate()

def test_noninteractive_use_refuses_to_print_credentials():
    output=io.StringIO();assert main(stdin=io.StringIO(),stdout=output)==2
    assert output.getvalue()=='PUSH_SETUP_REQUIRES_PRIVATE_TERMINAL\n'
