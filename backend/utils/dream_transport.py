"""One gateway-only model turn. Reserved routing belongs to the gateway."""

import json

import httpx

from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.shaped_agent import Turn

# These lanes default to Luna. The gateway owns the reserved-capacity selection
# when #20960 is present; no dream caller constructs a Gemini provider client.
TRIAGE_LANE = 'omi:auto:dream-triage'
MAIN_LANE = 'omi:auto:dream-reasoning'


def input_ceiling(messages, schema):
    # A conservative byte upper bound includes schema, role framing and tokenizer
    # overhead. No provider call is made if input + completion exceeds the cap.
    return len(json.dumps({'messages': messages, 'schema': schema}, ensure_ascii=False, default=str).encode()) + 256


class PreTokenFailure(RuntimeError):
    """The gateway rejected a call before producing any billable model output."""


async def model_turn(uid, lane, mount, messages, *, usage_sink=None):
    if usage_sink is not None:
        usage_sink['usage_unknown'] = False
    schema = mount.schema.model_json_schema()
    ceiling = input_ceiling(messages, schema)
    remaining = mount.budget.tokens - ceiling
    if remaining < 128:
        raise ValueError('dream_input_token_budget')
    completion = min(4096 if lane == MAIN_LANE else 768, remaining)
    headers = llm_gateway_headers(feature='dream_agent')
    headers['X-Omi-User-Uid'] = uid
    # Resolve local configuration before marking the provider outcome unknown.
    client = get_llm_gateway_client()
    url = get_llm_gateway_base_url() + '/v1/chat/completions'
    async with get_llm_gateway_semaphore():
        if usage_sink is not None:
            usage_sink['usage_unknown'] = True
        response = await client.post(
            url,
            headers=headers,
            json={
                'model': lane,
                'messages': messages,
                'stream': False,
                'max_completion_tokens': completion,
                'response_format': {
                    'type': 'json_schema',
                    'json_schema': {'name': mount.schema.__name__, 'schema': schema},
                },
            },
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PreTokenFailure('dream_gateway_rejected') from exc
    body = response.json()
    usage = body['usage']
    tokens = int(usage['prompt_tokens']) + int(usage['completion_tokens'])
    if tokens < 0 or tokens > ceiling + completion:
        raise ValueError('dream_invalid_usage')
    if usage_sink is not None:
        usage_sink['tokens'] += tokens
        usage_sink['usage_unknown'] = False
    value = mount.schema.model_validate_json(body['choices'][0]['message']['content'])
    return Turn(value=value, tokens=tokens)
