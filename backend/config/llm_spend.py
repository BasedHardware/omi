"""Kill switches for the W12 OpenAI spend cuts.

Each lever is independently reversible through its env key; defaults follow the
reviewed risk class: zero-output-risk cuts default on, semantic prompt edits
default off until their eval is accepted.
"""

import os

from config.refactor_switches import default_on as rollout_default_on

_FALSE_WORDS = frozenset({'false', '0', 'off', 'no'})
_TRUE_WORDS = frozenset({'true', '1', 'on', 'yes'})


def memory_l1_prompt_schema_trim_enabled() -> bool:
    """Omit only fields recomputed by the server from the generation schema."""
    return os.getenv('MEMORY_L1_PROMPT_SCHEMA_TRIM_ENABLED', 'true').strip().lower() not in _FALSE_WORDS


def vertex_embedding_dedupe_enabled() -> bool:
    """Reuse successful, exact-input Vertex embeddings for the same owner."""
    return os.getenv('VERTEX_EMBEDDING_DEDUPE_ENABLED', 'true').strip().lower() not in _FALSE_WORDS


def topic_deterministic_short_enabled() -> bool:
    """Answer very short topic requests deterministically without an LLM call."""
    return rollout_default_on(
        'CONVERSATION_TOPIC_DETERMINISTIC_SHORT_ENABLED',
        os.getenv('CONVERSATION_TOPIC_DETERMINISTIC_SHORT_ENABLED', 'true').strip().lower() not in _FALSE_WORDS,
    )


def outline_cache_prefix_enabled() -> bool:
    """Revert to the legacy wire prompt and cache policy with OMI_OUTLINE_CACHE_PREFIX=off."""
    return os.getenv('OMI_OUTLINE_CACHE_PREFIX', '').strip().lower() in _TRUE_WORDS


def background_outline_flex_enabled() -> bool:
    """Use streamed realtime outlines with LLM_GATEWAY_BACKGROUND_OUTLINE_FLEX=off."""
    return background_flex_retry_enabled() and (
        os.getenv('LLM_GATEWAY_BACKGROUND_OUTLINE_FLEX', '').strip().lower() in _TRUE_WORDS
    )


def background_flex_retry_enabled() -> bool:
    """Restore legacy Flex-first dispatch with LLM_GATEWAY_BACKGROUND_FLEX_RETRY=off."""
    return os.getenv('LLM_GATEWAY_BACKGROUND_FLEX_RETRY', 'true').strip().lower() not in _FALSE_WORDS


def v3_summary_first_open_gating_enabled() -> bool:
    """Opt in to V3 summary generation controls for explicit detail opens."""
    return os.getenv('OMI_V3_SUMMARY_FIRST_OPEN_GATING', '').strip().lower() in _TRUE_WORDS
