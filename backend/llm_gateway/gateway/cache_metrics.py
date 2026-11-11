"""Content-free per-attempt cache telemetry, independent of accounting delivery."""

import json
import logging

from prometheus_client import Counter

LABELS = ['lane', 'model', 'mode', 'reported']
CACHE_ATTEMPTS = Counter('llm_gateway_cache_attempts_total', 'All provider attempts, including missing usage', LABELS)
CACHE_ELIGIBLE = Counter(
    'llm_gateway_cache_eligible_attempts_total', 'Attempts with reusable prefixes above provider minimum', LABELS
)
CACHE_PROMPT_TOKENS = Counter(
    'llm_gateway_cache_prompt_tokens_total', 'Reported input tokens on eligible cache attempts', LABELS
)
CACHE_READ_TOKENS = Counter(
    'llm_gateway_cache_read_tokens_total', 'Reported cached tokens on eligible cache attempts', LABELS
)
logger = logging.getLogger(__name__)


def observe_cache_attempt(attempt):
    usage = attempt.usage
    reported = bool(usage and usage.cache_status.value not in {'not_reported', 'not_applicable'})
    mode = attempt.cache_mode if attempt.cache_mode in {'none', 'explicit', 'implicit'} else 'none'
    labels = {
        'lane': attempt.lane_id,
        'model': attempt.resolved_model or attempt.configured_model,
        'mode': mode,
        'reported': str(reported).lower(),
    }
    CACHE_ATTEMPTS.labels(**labels).inc()
    minimum = (
        4096 if attempt.provider == 'gemini' and mode == 'explicit' else 6144 if attempt.provider == 'gemini' else 1024
    )
    eligible = mode != 'none' and attempt.cacheable_prefix_tokens >= minimum
    if eligible:
        CACHE_ELIGIBLE.labels(**labels).inc()
        CACHE_PROMPT_TOKENS.labels(**labels).inc(usage.prompt_tokens + usage.tool_use_prompt_tokens if usage else 0)
        CACHE_READ_TOKENS.labels(**labels).inc(usage.cached_input_tokens if usage else 0)
    logger.info(
        'llm_gateway_cache_receipt %s',
        json.dumps(
            {
                **labels,
                'provider': attempt.provider,
                'traffic_type': attempt.traffic_type,
                'prompt_tokens': usage.prompt_tokens + usage.tool_use_prompt_tokens if usage else None,
                'cached_tokens': usage.cached_input_tokens if usage else None,
                'cacheable_prefix_tokens': attempt.cacheable_prefix_tokens,
                'cache_write_tokens': attempt.cache_write_tokens,
                'cache_storage_token_seconds': attempt.cache_storage_token_seconds,
            }
        ),
    )
