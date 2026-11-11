"""Per-attempt wire adaptation for the desktop proxy's direct kill-switch path."""

import json
import os
from collections.abc import Mapping

from utils.llm import vertex_pt_routing as ptr
from config.vertex_reservations import RESERVATIONS


def request_body(body: bytes, url: str) -> bytes:
    if ':generateContent' not in url and ':streamGenerateContent' not in url:
        return body
    model = url.split('/models/')[-1].split(':')[0]
    payload = json.loads(body)
    if not isinstance(payload, Mapping):
        return body
    if model != ptr.PT_MODEL_TARGET:
        config = payload.get('generationConfig', payload.get('generation_config', {}))
        if not isinstance(config, Mapping):
            return body
        thinking = config.get('thinkingConfig', config.get('thinking_config', {}))
        if not isinstance(thinking, Mapping) or ('thinkingLevel' not in thinking and 'thinking_level' not in thinking):
            return body
    return json.dumps(ptr.model_payload(payload, model), separators=(',', ':')).encode()


def target_url(model: str, action: str, capacity: str, default: str) -> str:
    if model not in RESERVATIONS or capacity != ptr.REQUEST_TYPE_DEDICATED:
        return default
    host, location = ptr.reservation_endpoint(model, os.environ)
    project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
    return f'https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}'


def gate_fields(headers: Mapping[str, str]) -> dict[str, object]:
    outcome = headers.get('x-omi-screen-task-gate', '')
    return {
        'gate_outcome': outcome if outcome in {'passed', 'rejected', 'fail_open'} else 'none',
        'audit_sample': headers.get('x-omi-screen-task-audit') == 'true' and outcome == 'rejected',
    }
