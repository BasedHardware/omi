"""One gateway-only model turn. Reserved routing belongs to the gateway."""

import json
from collections import Counter
from functools import lru_cache
from typing import get_args

from pydantic import ValidationError

from models.dream_agent import Plan, Triage

import httpx

from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.shaped_agent import Turn
from utils.observability.fallback import record_fallback

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


def _truncate_arrays(value, schema, root):
    """Keep ordered prefixes at the original Plan/Triage Pydantic array bounds.

    These schemas contain objects, arrays, local refs and nullable anyOf arms.
    Only arrays are capped; minima, types, extras and model validators still
    belong to Pydantic. Traverse retained items only, including nested ReviewItem
    payloads, so an oversized model response does not discard the entire pass.
    """
    if '$ref' in schema:
        target = root
        for part in schema['$ref'][2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        schema = {**target, **{key: item for key, item in schema.items() if key != '$ref'}}
    for arm in schema.get('anyOf', []):
        value = _truncate_arrays(value, arm, root)
    if isinstance(value, list) and schema.get('type') == 'array':
        bounded = value[: schema['maxItems']] if 'maxItems' in schema else value
        return [_truncate_arrays(item, schema.get('items', {}), root) for item in bounded]
    if isinstance(value, dict) and schema.get('type') == 'object':
        properties = schema.get('properties', {})
        return {key: _truncate_arrays(item, properties.get(key, {}), root) for key, item in value.items()}
    return value


@lru_cache(maxsize=1)
def _diagnostic_fields():
    # Static model metadata only; never retain response values or exception data.
    fields = set()
    for model in (Plan, Triage):
        schema = model.model_json_schema()
        for node in [schema, *schema.get('$defs', {}).values()]:
            fields.update(node.get('properties', {}))
    return frozenset(fields)


def validation_counts(exc, *, prefix=()):
    """Only schema-owned field names and Pydantic error types may leave parsing.

    Unknown extra keys can contain user content; never log them, input, message,
    context or URL. Numeric locations collapse into their enclosing field path.
    """
    fields = _diagnostic_fields()
    counts = Counter()
    for error in exc.errors(include_input=False, include_context=False, include_url=False):
        path = (
            '.'.join(
                part if part in fields else 'unknown_field'
                for part in (*prefix, *error['loc'])
                if not isinstance(part, int)
            )
            or 'root'
        )
        counts[f"{path}:{error['type']}"] += 1
    return dict(counts)


def parse_response(model, content, *, usage_sink=None):
    """Preserve strict top-level shape while isolating malformed list items."""
    schema = model.model_json_schema()
    bounded = _truncate_arrays(content, schema, schema)
    if model not in (Plan, Triage):
        return model.model_validate_json(json.dumps(bounded))
    # Validate object/list types and extras before dropping anything. Empty lists
    # preserve the exact top-level schema; item validation follows independently.
    shape = (
        {key: [] if key in model.model_fields and isinstance(value, list) else value for key, value in bounded.items()}
        if isinstance(bounded, dict)
        else bounded
    )
    model.model_validate_json(json.dumps(shape))
    retained = {}
    dropped = {}
    errors = Counter()
    for name, field in model.model_fields.items():
        item_model = get_args(field.annotation)[0]
        retained[name] = []
        dropped[name] = 0
        for item in bounded.get(name, []):
            try:
                retained[name].append(item_model.model_validate_json(json.dumps(item)))
            except ValidationError as exc:
                dropped[name] += 1
                errors.update(validation_counts(exc, prefix=(name,)))
    if any(dropped.values()):
        record_fallback(
            component='agent_tools',
            from_mode='dream_response',
            to_mode='validated_items',
            reason='malformed_doc',
            outcome='degraded',
        )
    if usage_sink is not None:
        usage_sink.setdefault('dropped_invalid', {}).update(dropped)
        totals = Counter(usage_sink.get('validation_errors', {}))
        totals.update(errors)
        usage_sink['validation_errors'] = dict(totals)
    return model.model_validate(retained)


async def model_turn(uid, lane, mount, messages, *, usage_sink=None, completion_limit=4096):
    if usage_sink is not None:
        usage_sink['usage_unknown'] = False
    schema = mount.schema.model_json_schema()
    ceiling = input_ceiling(messages, schema)
    remaining = mount.budget.tokens - ceiling
    if remaining < 128:
        raise ValueError('dream_input_token_budget')
    completion = min(4096 if lane == MAIN_LANE else 768, remaining, completion_limit)
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
        usage_sink.setdefault('model_lanes', []).append(lane)
    content = json.loads(body['choices'][0]['message']['content'])
    value = parse_response(mount.schema, content, usage_sink=usage_sink)
    return Turn(value=value, tokens=tokens)
