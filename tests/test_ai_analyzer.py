import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.providers.base import AIError
from app.services.ai_analyzer import analyze

SOURCE = '體育室\n獎學金\n運動績優獎勵金申請至115年10月08日止'


def answer(**changes):
    return {'summary': '運動績優獎勵金開放申請', 'category': '獎學金', 'requires_action': True,
            'action_evidence': '運動績優獎勵金申請', 'keywords': ['獎學金'], 'event_date': None,
            'deadline': '2026-10-08', 'event_evidence': None,
            'deadline_evidence': '申請至115年10月08日止', **changes}


def run(data):
    provider = Mock()
    provider.generate.return_value = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return analyze(provider, department='體育室', source_category='獎學金', title='運動績優獎勵金',
                   original_text=SOURCE, received_at=datetime(2026, 9, 19))


def test_valid_analysis():
    result = run(answer())
    assert result.output.deadline == '2026-10-08'
    assert result.output.requires_action is True
    assert not result.warnings


def test_unknown_action_does_not_retain_unverified_quote():
    result = run(answer(requires_action=None, action_evidence='invented action'))
    assert result.output.action_evidence is None


def test_web_content_can_support_date_and_action():
    provider = Mock()
    provider.generate.return_value = json.dumps(answer())
    result = analyze(provider, department='體育室', source_category='獎學金', title='公告',
        original_text='詳見公告網頁', supplemental_text=SOURCE,
        source_url='https://example.invalid/announcement', received_at=datetime(2026, 9, 19))
    assert result.output.deadline == '2026-10-08'
    assert result.output.requires_action is True
    assert provider.generate.call_args[0][1]['original_text'] == '詳見公告網頁'


@pytest.mark.parametrize('data', ['not json', '```json\n{}\n```', answer(category='不存在'),
                                 answer(requires_action='true'), answer(deadline='2026-02-30'),
                                 answer(extra='unexpected'), answer(keywords=['x' * 41])])
def test_invalid_outputs(data):
    with pytest.raises(AIError, match='OUTPUT_INVALID'):
        run(data)


def test_hallucinated_date_and_action_not_applied():
    result = run(answer(deadline='2027-10-08', action_evidence='立即繳費'))
    assert result.output.deadline is None
    assert result.output.requires_action is None
    assert len(result.warnings) == 2


def test_event_deadline_cannot_be_swapped():
    result = run(answer(event_date='2026-10-08', event_evidence='申請至115年10月08日止'))
    assert result.output.event_date is None
    assert result.output.deadline == '2026-10-08'


def test_provider_failure_propagates_without_fake_analysis():
    provider = Mock()
    provider.generate.side_effect = AIError('AI_UNAVAILABLE')
    with pytest.raises(AIError, match='UNAVAILABLE'):
        analyze(provider, department='x', source_category='x', title='x', original_text='x', received_at=datetime(2026, 1, 1))
