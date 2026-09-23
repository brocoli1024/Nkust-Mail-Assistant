"""iAI Chat Completions adapter. No vendor SDK, redirects or silent model fallback."""
import json
import time
from urllib.parse import urlsplit

import httpx

from app.providers.base import AIError, AISetupRequired


class IAIProvider:
    name = 'iai'

    def __init__(self, settings, *, transport=None, sleep=time.sleep, require_model=True):
        self.model = settings.ai_model.strip()
        self.base_url = settings.ai_base_url.rstrip('/')
        parsed = urlsplit(self.base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AISetupRequired('AI_ENDPOINT_INVALID: use an HTTPS API base URL')
        if settings.ai_provider != 'iai':
            raise AISetupRequired('AI_PROVIDER_UNKNOWN: configure AI_PROVIDER=iai')
        if not settings.ai_api_key.strip():
            raise AISetupRequired('AI_KEY_MISSING: set AI_API_KEY in the local .env file')
        if require_model and not self.model:
            raise AISetupRequired('AI_MODEL_MISSING: run ai-models and configure an exact AI_MODEL ID')
        if not 1 <= settings.ai_timeout_seconds <= 300:
            raise AISetupRequired('AI_TIMEOUT_INVALID: expected 1–300 seconds')
        self._key = settings.ai_api_key.strip()
        self.timeout = settings.ai_timeout_seconds
        self.transport = transport
        self.sleep = sleep

    def _request(self, method, path, body=None):
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, transport=self.transport,
                              trust_env=False) as client:
                for attempt in range(2):
                    response = client.request(method, self.base_url + path,
                                              headers={'Authorization': 'Bearer ' + self._key}, json=body)
                    if response.status_code in (429, 502, 503, 504) and attempt == 0:
                        # Bound retries, including provider-suggested delay.
                        try:
                            delay = max(1, min(30, float(response.headers.get('Retry-After', '2'))))
                        except ValueError:
                            delay = 2
                        self.sleep(delay)
                        continue
                    if not 200 <= response.status_code < 300:
                        raise AIError(f'AI_HTTP_ERROR: status {response.status_code}; check key, quota or model')
                    if len(response.content) > 1_000_000:
                        raise AIError('AI_RESPONSE_TOO_LARGE')
                    return response.json()
        except AIError:
            raise
        except httpx.TimeoutException:
            # A timeout may already have consumed quota; do not retry it automatically.
            raise AIError('AI_TIMEOUT: request timed out; no automatic timeout retry') from None
        except (httpx.HTTPError, ValueError):
            raise AIError('AI_CONNECTION_FAILED: request or response decoding failed') from None

    def list_models(self):
        data = self._request('GET', '/models')
        if not isinstance(data, dict) or not isinstance(data.get('data'), list):
            raise AIError('AI_MODELS_INVALID: unexpected model list format')
        return [item['id'] for item in data['data'] if isinstance(item, dict) and isinstance(item.get('id'), str)]

    def generate(self, system, payload, schema):
        # JSON object mode verified with iAI Furen-std. Full schema validation remains local.
        body = {'model': self.model, 'stream': False, 'max_tokens': 1800,
                'response_format': {'type': 'json_object'},
                'messages': [
                    {'role': 'system', 'content': system + '\nJSON Schema:\n' + json.dumps(schema, ensure_ascii=False)},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
                ]}
        result = self._request('POST', '/chat/completions', body)
        try:
            choice = result['choices'][0]
            if not isinstance(choice, dict):
                raise AIError('AI_RESPONSE_INVALID: invalid completion choice')
            if choice.get('finish_reason') != 'stop':
                raise AIError('AI_INCOMPLETE: output was truncated, filtered or did not finish normally')
            content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise AIError('AI_OUTPUT_EMPTY')
            return content
        except (KeyError, IndexError, TypeError):
            raise AIError('AI_RESPONSE_INVALID: missing completion content') from None
