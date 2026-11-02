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
        'attempt_usage': [
            {
                'provider': attempt.provider,
                'model': attempt.resolved_model or attempt.configured_model,
                'prompt_tokens': (
                    attempt.usage.prompt_tokens + attempt.usage.tool_use_prompt_tokens if attempt.usage else 0
                ),
                'cached_tokens': attempt.usage.cached_input_tokens if attempt.usage else 0,
                'completion_tokens': attempt.usage.billable_output_tokens if attempt.usage else 0,
                'cache_field_reported': bool(
                    attempt.usage
                    and attempt.usage.cache_status not in {CacheStatus.NOT_REPORTED, CacheStatus.NOT_APPLICABLE}
                ),
                'usage_complete': attempt.billable_usage_complete,
                'traffic_type': attempt.traffic_type,
                'cache_mode': attempt.cache_mode,
                'cacheable_prefix_tokens': attempt.cacheable_prefix_tokens,
                'cache_write_tokens': attempt.cache_write_tokens
                + (attempt.usage.cache_write_tokens if attempt.usage else 0),
                'cache_storage_token_seconds': attempt.cache_storage_token_seconds,
            }
            for attempt in trace.attempts
        ],
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
