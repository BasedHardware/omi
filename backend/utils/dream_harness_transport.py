"""One gateway tool/verifier turn; reserved policy and configured fallback stay gateway-owned."""

import json
from typing import Any

import httpx

from utils import dream_capacity
from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.shaped_agent import Turn


class CapacityWait(RuntimeError):
    pass


class PreTokenFailure(RuntimeError):
    pass


MAIN_LANE = 'omi:auto:dream-reasoning'
VERIFY_LANE = 'omi:auto:dream-verify'
CONTEXT_BYTES = 1048576


def accounted_usage(turn, aggregate, ceiling):
    unknown = aggregate.get('unknown_attempts', 0)
    reported = aggregate.get('unknown_reported_tokens', 0)
    if (
        type(unknown) is not int
        or not 0 <= unknown <= 2
        or type(reported) is not int
        or not 0 <= reported <= turn.tokens
    ):
        raise ValueError('dream_invalid_usage')
    charged = turn.tokens + unknown * ceiling - reported
    if charged < turn.tokens or charged > 2 * ceiling:
        raise ValueError('dream_invalid_usage')
    turn.accounted_tokens = charged
    return unknown


def input_bytes(messages, mount):
    payload = {
        'messages': messages,
        'tools': mount.tools,
        'schema': mount.schema.model_json_schema() if mount.schema is not None else None,
    }
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode()) + 32 * len(messages) + 256


def usage_turn(value):
    prompt, completion = value.get('prompt_tokens'), value.get('completion_tokens')
    cached = (value.get('prompt_tokens_details') or {}).get('cached_tokens')
    if any(type(count) is not int or count < 0 for count in (prompt, completion)):
        raise ValueError('dream_invalid_usage')
    if cached is not None and (type(cached) is not int or cached < 0 or cached > prompt):
        raise ValueError('dream_invalid_cache_usage')
    return Turn(tokens=prompt + completion, prompt_tokens=prompt, completion_tokens=completion, cached_tokens=cached)


async def model_turn(
    uid, lane, mount, messages, *, completion_limit=4096, model_seconds: float = 480, on_usage=None, usage_sink=None
):
    if lane not in {MAIN_LANE, VERIFY_LANE}:
        raise ValueError('dream_invalid_lane')
    ceiling = input_bytes(messages, mount)
    # Bytes are a conservative upper bound; observed usage settles the turn and
    # gives subsequent turns their actual remaining token allowance.
    # Reserve two attempts: the configured Gemini -> non-Gemini fallback may
    # follow a billed failure. Unknown usage retains its conservative ceiling.
    remaining = min(CONTEXT_BYTES, (mount.budget.tokens or 0) // 2) - ceiling
    if remaining < 128:
        raise ValueError('dream_input_token_budget')
    completion = min(completion_limit, remaining)
    model = await dream_capacity.available_model()
    if model is None:
        raise CapacityWait('dream_capacity_wait')
    headers = llm_gateway_headers(feature='dream_agent')
    headers['X-Omi-User-Uid'] = uid
    request: dict[str, Any] = {
        'model': lane,
        'messages': messages,
        'stream': False,
        'max_completion_tokens': completion,
        'reasoning_effort': 'none' if lane == VERIFY_LANE else 'medium',
    }
    if mount.schema is not None:
        request['response_format'] = {
            'type': 'json_schema',
            'json_schema': {'name': mount.schema.__name__, 'schema': mount.schema.model_json_schema()},
        }
    else:
        request.update(tools=list(mount.tools), tool_choice='auto')
    # No dream_reserved_only override: retain the route's configured non-Gemini
    # fallback exactly. The gateway artifact never offers shared/PAYG Gemini.
    if usage_sink is not None:
        usage_sink['usage_unknown'] = True
    async with get_llm_gateway_semaphore():
        response = await get_llm_gateway_client().post(
            get_llm_gateway_base_url() + '/v1/chat/completions',
            headers=headers,
            json=request,
            timeout=httpx.Timeout(model_seconds, connect=3, write=60, pool=5),
        )
    if response.is_error:
        error_body = {}
        try:
            error_body = response.json()
            failure = error_body.get('error', {}).get('failure_class')
        except (ValueError, AttributeError):
            failure = None
        known_zero = (
            response.status_code in {400, 401, 403, 404, 422, 429} or failure == 'reserved_capacity_unavailable'
        )
        aggregate = error_body.get('dream_usage')
        if isinstance(aggregate, dict):
            paid = usage_turn(aggregate)
            unknown = accounted_usage(paid, aggregate, ceiling + completion)
            if on_usage is not None:
                await on_usage(paid)
            known_zero = unknown == 0 and paid.tokens == 0
        if known_zero and usage_sink is not None:
            usage_sink['usage_unknown'] = False
        if response.status_code == 429 or failure in {'reserved_capacity_unavailable', 'provider_429_omi_paid'}:
            await dream_capacity.mark_saturated(model)
            raise CapacityWait('dream_capacity_wait')
        if known_zero:
            raise PreTokenFailure('dream_gateway_rejected')
        raise RuntimeError('dream_gateway_failure')
    body = response.json()
    aggregate = body.get('dream_usage')
    unknown = 0
    if aggregate is not None:
        if (
            not isinstance(aggregate, dict)
            or type(aggregate.get('unknown_attempts')) is not int
            or not 0 <= aggregate['unknown_attempts'] <= 2
        ):
            raise ValueError('dream_invalid_usage')
        unknown = aggregate['unknown_attempts']
        turn = usage_turn({**aggregate, 'prompt_tokens_details': {'cached_tokens': aggregate.get('cached_tokens')}})
        unreported = aggregate.get('cache_unreported_tokens', 0)
        if type(unreported) is not int or not 0 <= unreported <= turn.prompt_tokens - (turn.cached_tokens or 0):
            raise ValueError('dream_invalid_cache_usage')
        turn.cache_unreported_tokens = unreported
    else:
        turn = usage_turn(body.get('usage') or {})
    accounted_usage(turn, aggregate or {}, ceiling + completion)
    if usage_sink is not None:
        usage_sink['usage_unknown'] = unknown > 0
    # Account before parsing so a billed malformed verifier response is paid.
    if on_usage is not None:
        await on_usage(turn)
    if usage_sink is not None:
        usage_sink['transport_complete'] = True
    choice = body['choices'][0]
    if choice.get('finish_reason') in {'length', 'max_tokens'}:
        raise ValueError('dream_response_truncated')
    message = choice['message']
    if mount.schema is not None:
        turn.value = mount.schema.model_validate_json(message.get('content') or '', strict=True)
    else:
        calls = message.get('tool_calls') or []
        if not isinstance(calls, list) or len(calls) > 64 or any(not isinstance(call, dict) for call in calls):
            raise ValueError('dream_invalid_tool_calls')
        turn.tool_calls = tuple(calls)
        # Preserve the provider's thought signatures and tool ids on round trips.
        turn.messages = (message,)
        turn.value = message.get('content')
    return turn
