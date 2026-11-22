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
