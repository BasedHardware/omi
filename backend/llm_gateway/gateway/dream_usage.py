"""Content-free multi-attempt accounting for nonstreaming Dream sessions."""

from llm_gateway.gateway.accounting import CacheStatus

DREAM_LANES = {'omi:auto:dream-reasoning', 'omi:auto:dream-verify'}
KNOWN_ZERO = {
    'reserved_capacity_unavailable',
    'provider_429_omi_paid',
    'provider_invalid_request',
    'capability_mismatch',
    'invalid_config',
    'provider_auth_failure',
}


def with_dream_usage(response, lane, trace):
    if lane not in DREAM_LANES:
        return response
    known = [attempt.usage for attempt in trace.attempts if attempt.usage is not None]
    uncertain = [
        attempt
        for attempt in trace.attempts
        if not attempt.billable_usage_complete and attempt.error_class not in KNOWN_ZERO
    ]
    unknown = len(uncertain)
    summary = {
        'attempts': len(trace.attempts),
        'unknown_attempts': unknown,
        'unknown_reported_tokens': sum(
            attempt.usage.prompt_tokens + attempt.usage.tool_use_prompt_tokens + attempt.usage.billable_output_tokens
            for attempt in uncertain
            if attempt.usage is not None
        ),
        'prompt_tokens': sum(usage.prompt_tokens + usage.tool_use_prompt_tokens for usage in known),
        'completion_tokens': sum(usage.billable_output_tokens for usage in known),
        'cached_tokens': sum(usage.cached_input_tokens for usage in known),
        'cache_unreported_tokens': sum(
            usage.prompt_tokens + usage.tool_use_prompt_tokens
            for usage in known
            if usage.cache_status == CacheStatus.NOT_REPORTED
        ),
        'cache_usage_complete': bool(known) and all(usage.cache_status != CacheStatus.NOT_REPORTED for usage in known),
    }
    return {**response, 'dream_usage': summary}
