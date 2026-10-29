"""Kill switches for the W12 OpenAI spend cuts.

Each lever is independently reversible through its env key; defaults follow the
reviewed risk class: zero-output-risk cuts default on, semantic prompt edits
default off until their eval is accepted.
"""

import os

from config.refactor_switches import default_off as rollout_default_off
from config.refactor_switches import default_on as rollout_default_on

_FALSE_WORDS = frozenset({'false', '0', 'off', 'no'})
_TRUE_WORDS = frozenset({'true', '1', 'on', 'yes'})


def topic_deterministic_short_enabled() -> bool:
    """Answer very short topic requests deterministically without an LLM call."""
    return rollout_default_on(
        'CONVERSATION_TOPIC_DETERMINISTIC_SHORT_ENABLED',
        os.getenv('CONVERSATION_TOPIC_DETERMINISTIC_SHORT_ENABLED', 'true').strip().lower() not in _FALSE_WORDS,
    )


def memory_l1_owner_neutral_prefix_enabled() -> bool:
    """Serve the L1 system prompt without the owner name embedded in it.

    Off keeps the exact legacy wording. On moves the owner name to the volatile
    tail so the instruction prefix is shareable across a user's calls (and the
    provider's prompt cache can read it); enable only after the fixture eval
    shows unchanged extraction behavior.
    """
    return rollout_default_off(
        'MEMORY_L1_OWNER_NEUTRAL_PREFIX_ENABLED',
        os.getenv('MEMORY_L1_OWNER_NEUTRAL_PREFIX_ENABLED', 'false').strip().lower() in _TRUE_WORDS,
    )
