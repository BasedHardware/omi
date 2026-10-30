"""One gateway tool/verifier turn; reserved policy and configured fallback stay gateway-owned."""

from utils.generated_compute import generated_compute_allowed, generated_compute_configured

import json
from typing import Any

import httpx

from config.dream_agent import admission_for
from config.rollout_cohorts import warm_rollout_cohorts
from utils import dream_capacity
from utils.dream_cost import (
    charge_attempts,
    conservative_attempt_micro,
    estimate_tokens,
    price_attempt,
    price_weighted_tokens,
)
from utils.executors import db_executor, run_blocking
from utils.http_client import get_llm_gateway_client, get_llm_gateway_semaphore
from utils.llm.gateway_client import get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.shaped_agent import Turn, validate_output


class CapacityWait(RuntimeError):
    def __init__(self, message='dream_capacity_wait', *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class PreTokenFailure(RuntimeError):
    pass


MAIN_LANE = 'omi:auto:dream-reasoning'
VERIFY_LANE = 'omi:auto:dream-verify'
# Gemini Flash context window, in tokens. The previous constant was this many
# bytes and was compared to a byte length as if it were a token ceiling.
CONTEXT_TOKENS = 1048576
DREAM_PROVIDER = 'gemini'
DREAM_MODEL = 'gemini-3.8-flash'


def accounted_usage(turn, aggregate, ceiling):
    unknown = aggregate.get('unknown_attempts', 0)
    reported = aggregate.get('unknown_reported_tokens', 0)
    if type(unknown) is not int or unknown < 0 or type(reported) is not int or not 0 <= reported <= turn.tokens:
        raise ValueError('dream_invalid_usage')
    charged = turn.tokens + unknown * ceiling - reported
    if charged < turn.tokens:
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


def message_bytes(messages):
    if not messages:
        return 0
    return len(json.dumps(list(messages), ensure_ascii=False, default=str).encode()) + 32 * len(messages)


def input_token_estimate(messages, mount, *, prior_prompt_tokens=None, prior_message_count=0):
    """First turn: whole payload bytes / 3.5. Later turns: last real prompt plus new bytes / 3.5."""
    if prior_prompt_tokens is None:
        return estimate_tokens(input_bytes(messages, mount))
    if type(prior_prompt_tokens) is not int or prior_prompt_tokens < 0:
        raise ValueError('dream_invalid_usage')
    new_messages = list(messages)[prior_message_count:]
    return prior_prompt_tokens + estimate_tokens(message_bytes(new_messages))


def attempt_room(
    messages,
    mount,
    *,
    prior_prompt_tokens=None,
    prior_message_count=0,
    cached_tokens_estimate=None,
    completion_limit=4096,
):
    """One attempt: estimated input plus bounded completion. No second-attempt halving."""
    estimate = input_token_estimate(
        messages, mount, prior_prompt_tokens=prior_prompt_tokens, prior_message_count=prior_message_count
    )
    budget = mount.budget.tokens or 0
    context_room = CONTEXT_TOKENS - estimate
    known_cached = (
        min(cached_tokens_estimate, estimate)
        if type(cached_tokens_estimate) is int and cached_tokens_estimate >= 0
        else None
    )
    budget_input = price_weighted_tokens(
        DREAM_PROVIDER,
        DREAM_MODEL,
        prompt_tokens=estimate,
        cached_tokens=known_cached,
        completion_tokens=0,
        cache_reported=known_cached is not None,
    )
    budget_room = budget - budget_input
    room = min(context_room, budget_room)
    if room < 128:
        raise ValueError('dream_input_token_budget')
    completion = min(completion_limit, room)
    return estimate, completion


def usage_turn(value):
    prompt, completion = value.get('prompt_tokens'), value.get('completion_tokens')
    cached = (value.get('prompt_tokens_details') or {}).get('cached_tokens')
    if any(type(count) is not int or count < 0 for count in (prompt, completion)):
        raise ValueError('dream_invalid_usage')
    if cached is not None and (type(cached) is not int or cached < 0 or cached > prompt):
        raise ValueError('dream_invalid_cache_usage')
    return Turn(tokens=prompt + completion, prompt_tokens=prompt, completion_tokens=completion, cached_tokens=cached)


def _required_int(value):
    if type(value) is not int:
        raise ValueError('dream_invalid_usage')
    return value


def _apply_cost(turn, micro, status):
    turn.cost_micro_usd = micro
    turn.cost_status = status


def _zero_turn():
    turn = Turn(price_weighted_tokens=0)
    _apply_cost(turn, 0, 'priced')
    return turn


def _price_aggregate(turn, aggregate, ceiling):
    attempts = aggregate.get('attempt_usage') if isinstance(aggregate, dict) else None
    if isinstance(attempts, list) and attempts:
        priced = charge_attempts(attempts, ceiling=ceiling, provider=DREAM_PROVIDER, model=DREAM_MODEL)
        if priced is None:
            raise ValueError('dream_invalid_usage')
        prompt_tokens = _required_int(priced.get('prompt_tokens'))
        completion_tokens = _required_int(priced.get('completion_tokens'))
        turn.tokens = prompt_tokens + completion_tokens
        turn.prompt_tokens = prompt_tokens
        turn.completion_tokens = completion_tokens
        turn.cached_tokens = _required_int(priced.get('cached_tokens'))
        turn.cache_unreported_tokens = _required_int(priced.get('cache_unreported_tokens'))
        turn.accounted_tokens = _required_int(priced.get('tokens'))
        turn.price_weighted_tokens = _required_int(priced.get('price_weighted_tokens'))
        status = priced.get('cost_status')
        if status not in {'priced', 'unpriced'}:
            raise ValueError('dream_invalid_usage')
        _apply_cost(turn, priced.get('cost_micro_usd'), status)
        return
    unknown = aggregate.get('unknown_attempts', 0) if isinstance(aggregate, dict) else 0
    micro, status = price_attempt(
        DREAM_PROVIDER,
        DREAM_MODEL,
        prompt_tokens=turn.prompt_tokens,
        cached_tokens=turn.cached_tokens or 0,
        completion_tokens=turn.completion_tokens,
    )
    if unknown:
        extra, extra_status = conservative_attempt_micro(DREAM_PROVIDER, DREAM_MODEL, ceiling, 0)
        if status != 'priced' or extra_status != 'priced' or micro is None or extra is None:
            _apply_cost(turn, None, 'unpriced')
        else:
            _apply_cost(turn, micro + extra * unknown, 'priced')
    else:
        _apply_cost(turn, micro, status)
    cache_reported = (
        aggregate.get('cache_usage_complete') is True
        if 'cache_usage_complete' in aggregate
        else turn.cached_tokens is not None
    )
    weighted = price_weighted_tokens(
        DREAM_PROVIDER,
        DREAM_MODEL,
        prompt_tokens=turn.prompt_tokens,
        cached_tokens=turn.cached_tokens,
        completion_tokens=turn.completion_tokens,
        cache_reported=cache_reported,
    )
    if turn.accounted_tokens is not None:
        weighted += max(0, turn.accounted_tokens - turn.tokens)
    turn.price_weighted_tokens = weighted


def turn_from_usage(aggregate, ceiling):
    if isinstance(aggregate.get('attempt_usage'), list) and aggregate['attempt_usage']:
        turn = Turn()
        _price_aggregate(turn, aggregate, ceiling)
        return turn, aggregate.get('unknown_attempts', 0)
    turn = usage_turn({**aggregate, 'prompt_tokens_details': {'cached_tokens': aggregate.get('cached_tokens')}})
    unreported = aggregate.get('cache_unreported_tokens', 0)
    if type(unreported) is not int or not 0 <= unreported <= turn.prompt_tokens - (turn.cached_tokens or 0):
        raise ValueError('dream_invalid_cache_usage')
    turn.cache_unreported_tokens = unreported
    unknown = accounted_usage(turn, aggregate, ceiling)
    _price_aggregate(turn, aggregate, ceiling)
    return turn, unknown


async def model_turn(
    uid,
    lane,
    mount,
    messages,
    *,
    completion_limit=4096,
    model_seconds: float = 480,
    on_usage=None,
    usage_sink=None,
    prior_prompt_tokens=None,
    prior_message_count=0,
    cached_tokens_estimate=None,
):
    if generated_compute_configured() and not await run_blocking(
        db_executor, generated_compute_allowed, uid, 'dream', allow_byok=False
    ):
        raise CapacityWait('usage_budget_exhausted')
    if lane not in {MAIN_LANE, VERIFY_LANE}:
        raise ValueError('dream_invalid_lane')
    _estimate, completion = attempt_room(
        messages,
        mount,
        prior_prompt_tokens=prior_prompt_tokens,
        prior_message_count=prior_message_count,
        cached_tokens_estimate=cached_tokens_estimate,
        completion_limit=completion_limit,
    )
    ceiling = _estimate + completion
    await warm_rollout_cohorts(uid)
    mode, allowlisted = admission_for(uid)
    model = await dream_capacity.available_model(mode=mode, owner_allowlisted=allowlisted)
    if model is None:
        # No dispatch: release the caller's minute hold before it pauses/re-reserves.
        if on_usage is not None:
            await on_usage(_zero_turn())
        raise CapacityWait('dream_capacity_wait', retryable=True)
    headers = llm_gateway_headers(feature='dream_agent')
    headers['X-Omi-User-Uid'] = uid
    request: dict[str, Any] = {
        'model': lane,
        'messages': messages,
        'stream': False,
        'max_completion_tokens': completion,
        'reasoning_effort': 'none' if lane == VERIFY_LANE else 'medium',
        'google': {'dream_capacity_mode': mode},
    }
    if mode == 'on_demand':
        request['google']['dream_owner_allowlisted'] = True
    if mount.schema is not None:
        request['response_format'] = {
            'type': 'json_schema',
            'json_schema': {'name': mount.schema.__name__, 'schema': mount.schema.model_json_schema()},
        }
    else:
        request.update(tools=list(mount.tools), tool_choice='auto')
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
            paid, unknown = turn_from_usage(aggregate, ceiling)
            if usage_sink is not None:
                usage_sink['usage_unknown'] = unknown > 0
            if on_usage is not None:
                await on_usage(paid)
            known_zero = unknown == 0 and paid.accounted_tokens in (None, 0) and paid.tokens == 0
        if known_zero and not isinstance(aggregate, dict) and on_usage is not None:
            await on_usage(_zero_turn())
        if known_zero and usage_sink is not None:
            usage_sink['usage_unknown'] = False
        if response.status_code == 429 or failure in {'reserved_capacity_unavailable', 'provider_429_omi_paid'}:
            await dream_capacity.mark_saturated(model)
            # Any billed/unknown aggregate was charged above before re-reserving a retry.
            raise CapacityWait('dream_capacity_wait', retryable=True)
        if known_zero:
            raise PreTokenFailure('dream_gateway_rejected')
        raise RuntimeError('dream_gateway_failure')
    body = response.json()
    aggregate = body.get('dream_usage')
    unknown = 0
    if aggregate is not None:
        if not isinstance(aggregate, dict) or type(aggregate.get('unknown_attempts', 0)) is not int:
            raise ValueError('dream_invalid_usage')
        turn, unknown = turn_from_usage(aggregate, ceiling)
    else:
        turn, unknown = turn_from_usage(body.get('usage') or {}, ceiling)
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
        # Declared near-miss keys are normalized before strict validation (harness tool rule 3).
        turn.value = validate_output(mount.schema, message.get('content') or '', strict=True)
    else:
        calls = message.get('tool_calls') or []
        if not isinstance(calls, list) or len(calls) > 64 or any(not isinstance(call, dict) for call in calls):
            raise ValueError('dream_invalid_tool_calls')
        turn.tool_calls = tuple(calls)
        # Preserve the provider's thought signatures and tool ids on round trips.
        turn.messages = (message,)
        turn.value = message.get('content')
    return turn
