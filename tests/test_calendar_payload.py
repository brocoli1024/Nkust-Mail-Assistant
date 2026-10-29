import json
from app.services.action_cards import build_action_card
from tests.test_action_cards import source
from app.services.calendar_export import calendar_payload


def test_calendar_payload_has_only_bounded_export_information():
    card=build_action_card(source('PRIVATE START '+('字'*1000)+' SECRET ORIGINAL TAIL',kind='private'))
    result=calendar_payload(card)
    assert set(result)=={'schema_version','source','baseline_hash','summary','action','dates','time_status','context'}
    assert result['context']=='current' and result['source']['kind']=='private'
    assert 'SECRET ORIGINAL TAIL' not in json.dumps(result)
    assert 'segments' not in result['source'] and 'ai_references' not in result
    assert len(result['summary'])<=160


def test_calendar_payload_preserves_separate_date_states_and_snapshot():
    c=build_action_card(source('報名截止：2026年11月10日；活動日期：2026年11月20日'))
    result=calendar_payload(c.model_dump(mode='json'),snapshot=True)
    assert result['dates']['deadline']['value']=='2026-11-10'
    assert result['dates']['event_date']['value']=='2026-11-20'
    assert result['dates']['event_date']['state']=='supported'
    assert result['dates']['event_date']['evidence']==['活動日期：2026年11月20日']
    assert result['context']=='snapshot'
