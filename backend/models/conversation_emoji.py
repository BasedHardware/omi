"""The shared emoji policy for notes rows that never chose one.

Two values with distinct meanings:

- ``DEFAULT_EMOJI`` (🧠) is the *unset sentinel*: every extraction schema's
  pydantic default supplies it, so a submission that omitted the field is
  indistinguishable from one that chose it — the default value itself is the
  signal (the 2026-10-23 rollout pinned 🧠 on every v2 conversation this way).
- ``NEUTRAL_EMOJI`` (💬) is the deterministic stand-in when nothing chose:
  category ``other``, the ``Structured`` model default, and the last resort
  for a string no enum maps.

🧠 therefore only reaches a stored row when it is the deliberate
relevance-discard placeholder, never as an accident of a forgotten field.
"""

from __future__ import annotations

from typing import Any

DEFAULT_EMOJI = '🧠'
NEUTRAL_EMOJI = '💬'

CATEGORY_EMOJI = {
    'personal': '🙂',
    'education': '📚',
    'health': '🩺',
    'finance': '💰',
    'legal': '⚖️',
    'philosophy': '🤔',
    'spiritual': '🧘',
    'science': '🔬',
    'entrepreneurship': '🚀',
    'parenting': '👶',
    'romantic': '❤️',
    'travel': '✈️',
    'inspiration': '💡',
    'technology': '💻',
    'business': '💼',
    'social': '👥',
    'work': '🧑‍💻',
    'sports': '⚽',
    'politics': '🏛️',
    'literature': '📖',
    'history': '🏺',
    'architecture': '🏗️',
    'music': '🎵',
    'weather': '⛅',
    'news': '📰',
    'entertainment': '🎬',
    'psychology': '💭',
    'real': '🌍',
    'design': '🎨',
    'family': '🏡',
    'economics': '📊',
    'environment': '🌿',
    'other': NEUTRAL_EMOJI,
}


def fallback_emoji(emoji: str, category: Any) -> str:
    """The submitted emoji, or the category's emoji when none arrived.

    Agentic submissions are round-tripped through ``model_dump`` before the
    final validation, so a defaulted emoji is indistinguishable from one the
    model chose: the default value itself is the signal. Every ``CategoryEnum``
    member maps (``other`` → ``NEUTRAL_EMOJI``); an arbitrary string falls back
    to the neutral emoji, never the sentinel brain.
    """
    if emoji and emoji.strip() and emoji != DEFAULT_EMOJI:
        return emoji
    return CATEGORY_EMOJI.get(getattr(category, 'value', category)) or NEUTRAL_EMOJI
