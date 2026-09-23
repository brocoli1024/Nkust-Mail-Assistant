import json
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.providers.iai import IAIProvider
from app.providers.base import AIError, AISetupRequired


def settings(**kwargs):
    return replace(Settings(ai_api_key='synthetic-test-key', ai_model='synthetic-model'), **kwargs)


def test_wire_format_and_models():
    calls = []
    def respond(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'synthetic-model'}]})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]})
    provider = IAIProvider(settings(), transport=httpx.MockTransport(respond))
    assert provider.list_models() == ['synthetic-model']
    assert provider.generate('system', {'title': '合成公告'}, {}) == '{}'
    assert calls[1].url.path == '/aihub/v1/chat/completions'
    assert calls[1].headers['Authorization'] == 'Bearer synthetic-test-key'
    assert json.loads(calls[1].content)['model'] == 'synthetic-model'
    assert json.loads(calls[1].content)['response_format'] == {'type': 'json_object'}
    assert 'synthetic-test-key' not in repr(settings())


@pytest.mark.parametrize('config', [settings(ai_api_key=''), settings(ai_model=''),
                                  settings(ai_base_url='http://example.invalid'), settings(ai_timeout_seconds=0)])
def test_invalid_settings(config):
    with pytest.raises(AISetupRequired):
        IAIProvider(config)


def test_retry_and_sanitized_error():
    requests = []
    sleeps = []
    def respond(request):
        requests.append(request)
        return httpx.Response(503, text='secret response body', headers={'Retry-After': '10000'})
    provider = IAIProvider(settings(), transport=httpx.MockTransport(respond), sleep=sleeps.append)
    with pytest.raises(AIError, match='503') as caught:
        provider.generate('system', {}, {})
    assert len(requests) == 2 and sleeps == [30]
    assert 'secret' not in str(caught.value)


def test_auth_failure_and_redirect_not_retried():
    for code in (401, 302):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(code, headers={'Location': 'https://example.invalid'})
        provider = IAIProvider(settings(), transport=httpx.MockTransport(respond))
        with pytest.raises(AIError):
            provider.list_models()
        assert len(calls) == 1


def test_truncated_output_rejected():
    provider = IAIProvider(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})))
    with pytest.raises(AIError, match='INCOMPLETE'):
        provider.generate('system', {}, {})
