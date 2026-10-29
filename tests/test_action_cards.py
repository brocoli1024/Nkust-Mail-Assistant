from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.schemas.action_cards import SourceDocument, SourceSegment, CorrectionPatch
from app.services.action_cards import build_action_card, apply_patch, display_context


def source(text, kind='public', anchor=None):
    return SourceDocument(kind=kind, source_ref='synthetic', title='合成公告',
        segments=(SourceSegment(kind='original', text=text),), anchor=anchor)


def test_separate_dates_and_exact_evidence():
    s = source('報名截止：115年10月08日；活動日期：115年10月21日')
    card = build_action_card(s)
    assert card.fields['deadline'].value == '2026-10-08'
    assert card.fields['event_date'].value == '2026-10-21'
    assert card.fields['deadline'].state == 'supported'
    for field in card.fields.values():
        for e in field.evidence:
            assert s.segments[e.segment].text[e.start:e.end] == e.quote


@pytest.mark.parametrize('text', ['發布日期：2026年10月29日，活動公告', '報名截止：115年2月30日',
    '報名截止：10月8日', '報名截止：明年10月8日', '報名截止：2026年10月8日至2026年10月10日',
    '報名截止：2026年10月8日；報名截止：2026年10月9日'])
def test_ambiguous_dates_are_not_supported(text):
    card = build_action_card(source(text))
    assert card.fields['deadline'].state == 'pending'
    assert card.fields['event_date'].state == 'pending'


def test_private_inferred_year_remains_pending():
    card = build_action_card(source('報名截止：10月8日', 'private', datetime(2026,1,1,tzinfo=timezone.utc)))
    assert card.fields['deadline'].state == 'pending'
    assert any(e.year_inferred for e in card.candidates)


def test_actions_and_explicit_sections():
    card = build_action_card(source('無須報名，但請繳交報告。申請對象：全校學生。應備文件：在學證明。'))
    assert card.requires_action is True
    assert '繳交報告' in card.fields['action'].value
    assert '無須報名' not in card.fields['action'].value
    assert card.fields['audience'].value == '全校學生'
    assert card.fields['materials'].value == '在學證明'
    assert 'is_eligible' not in card.model_dump()
    assert build_action_card(source('獎學金錄取名單與報名資訊')).requires_action is None


def test_ai_is_reference_not_truth_and_hash_is_stable():
    s = source('公告內容未提供日期')
    card = build_action_card(s, legacy={'deadline':'2030-01-01'}, ai_references=({'status':'completed','result':{'deadline':'2030-01-01'}},))
    assert card.fields['deadline'].state == 'pending'
    assert card.legacy['deadline'] == '2030-01-01'
    assert card.ai_references
    assert build_action_card(s).baseline_hash == build_action_card(s).baseline_hash
    a = display_context(card, now=datetime(2026,10,29,15,59,tzinfo=timezone.utc))
    b = display_context(card, now=datetime(2026,10,29,16,0,tzinfo=timezone.utc))
    assert a['taipei_today'] == '2026-10-29' and b['taipei_today'] == '2026-10-30'


def test_corrections_keep_original_and_require_valid_confirmation():
    original = build_action_card(source('日期未定'))
    patch = CorrectionPatch.model_validate({'fields':{'deadline':{'mode':'value','value':'2026-11-01','confirmed':True}}})
    changed = apply_patch(original, patch)
    assert changed.fields['deadline'].state == 'user_confirmed'
    assert original.fields['deadline'].value is None
    for value in ('2026-02-30', '11/1'):
        with pytest.raises(ValidationError):
            CorrectionPatch.model_validate({'fields':{'deadline':{'mode':'value','value':value,'confirmed':True}}})
    with pytest.raises(ValidationError):
        CorrectionPatch.model_validate({'fields':{'deadline':{'mode':'value','value':'2026-11-01'}}})
    with pytest.raises(ValidationError):
        CorrectionPatch.model_validate({'fields':{}, 'owner':2})
    with pytest.raises(ValidationError):
        CorrectionPatch.model_validate({'fields':{'summary':{'mode':'value','value':'字'*161}}})


def test_equal_instants_have_equal_hashes_and_source_adapters_are_safe():
    from datetime import timedelta
    from types import SimpleNamespace
    from app.services.action_cards import public_source, private_source, demo_source
    a=source('報名截止：2026年10月8日','private',datetime(2026,1,1,tzinfo=timezone.utc))
    b=a.model_copy(update={'anchor':a.anchor.astimezone(timezone(timedelta(hours=8)))})
    assert build_action_card(a).source_hash == build_action_card(b).source_hash
    row=SimpleNamespace(source_key='nkust-latest',canonical_url='javascript:alert(1)', title='公告',excerpt='本文')
    assert public_source(row).url is None
    mail=SimpleNamespace(email_id=2,source_index=0,source_fingerprint='a',title='私信',original_text='原文',url='https://user:pass@example.invalid/')
    assert private_source(mail,datetime(2026,1,1),email_parser_version='v1').url is None
    assert demo_source(SimpleNamespace(id='demo-a',title='合成',excerpt='範例')).anchor is None


@pytest.mark.parametrize('change',[{'mode':'pending','value':'偷偷保存'}, {'mode':'value','value':'日期','confirmed':'false'}])
def test_patch_rejects_inconsistent_or_coerced_content(change):
    with pytest.raises(ValidationError):
        CorrectionPatch.model_validate({'fields':{'summary':change}})


def test_private_year_anchor_uses_taipei_year():
    c=build_action_card(source('報名截止：1月8日','private',datetime(2026,12,31,16,0,tzinfo=timezone.utc)))
    assert c.candidates[0].year_inferred
    # 推定僅是候選，仍不得成為確定日期。
    assert c.fields['deadline'].state == 'pending'


def test_summary_and_reference_validation_preserve_provenance():
    c=build_action_card(source('來源內容'*100),ai_references=({'status':'completed','version':'unknown','result':'broken'}, {'status':'failed','result':{'summary':'假的'}}, None))
    f=c.fields['summary']
    assert len(f.value)==160 and f.evidence
    assert f.evidence[0].quote == f.value
    assert c.source.segments[0].text == '來源內容'*100
    assert all(r['result'] is None for r in c.ai_references)
    assert all(r['warning'] for r in c.ai_references)


@pytest.mark.parametrize('name,limit',[('action',1200),('audience',1200),('materials',1200)])
def test_patch_boundaries(name,limit):
    p=CorrectionPatch.model_validate({'fields':{name:{'mode':'value','value':'字'*limit,'quote':'文'*2000}}})
    assert len(p.fields[name].value)==limit
    for value,quote in [('字'*(limit+1),None),('字','文'*2001)]:
        with pytest.raises(ValidationError):
            CorrectionPatch.model_validate({'fields':{name:{'mode':'value','value':value,'quote':quote}}})


def test_duplicate_source_dates_and_context_conflicts():
    s=source('報名截止：2026年10月8日')
    s=s.model_copy(update={'segments':s.segments+s.segments})
    assert build_action_card(s).fields['deadline'].value=='2026-10-08'
    c=build_action_card(source('發布日期：2026年10月8日；活動日期：2026年10月8日；報名截止：2026年10月7日'))
    assert c.fields['event_date'].value=='2026-10-08'
    assert c.fields['deadline'].value=='2026-10-07'
    assert build_action_card(source('報名截止：2026年10月8日 15:30')).time_status=='unparsed'

@pytest.mark.parametrize('text', ['活動日期：2026年10月8日至10日', '活動日期：2026/10/8–10', '報名截止：2026年10月8日至10月10日'])
def test_abbreviated_ranges_remain_pending(text):
    card=build_action_card(source(text))
    assert card.fields['event_date'].state=='pending'
    assert card.fields['deadline'].state=='pending'


def test_tentative_date_is_not_supported():
    assert build_action_card(source('活動日期：2026年10月8日（暫定）')).fields['event_date'].state=='pending'
