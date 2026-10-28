"""L3 output-language authority at the episode prompt boundary.

The moment prompt is pinned to one resolved language on every path (kill switch
``EPISODE_OUTPUT_LANGUAGE_PIN``): the user's explicit preference first, then the
language the episode state is already written in, then the conversation's
dominant language — never the newest moment's speech deciding on its own. Blank
and sentinel tags (``multi``, ``auto``, …) count as unset, so they never reach a
prompt.

A state written in a different language (the wrong-language incident) is not fed
back verbatim: ``repair_instruction`` tells the model to rewrite it in the
resolved language as part of the next update, and the episode only stamps
``output_language`` once the state matches it.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from config.refactor_modes import serving_for
from utils.llm.output_language import normalize_language

# langdetect is unreliable on short text (backend AGENTS.md); a shorter state carries no
# language worth repairing anyway.
_MIN_STATE_DETECT_CHARS = 20


def resolved_invoke(uid, conversation_language, invoke):
    if not serving_for('LIFECYCLE_V2_MODE', uid):
        return invoke
    try:
        from utils.llm.output_language import resolve_output_language
    except ImportError:
        # L3 is integrated independently; until then retain the current prompt.
        return invoke
    language = resolve_output_language(uid, conversation_language)
    if invoke is None:
        from utils.episodes.incremental import invoke_model

        invoke = invoke_model

    def with_language(account, messages):
        return invoke(account, [*messages, ('system', f'Write all episode output in {language}.')])

    return with_language


def stored_language(episode: Optional[Mapping[str, Any]]) -> str:
    """The language the episode document says its state is written in ('' when unstamped)."""
    return normalize_language((episode or {}).get('output_language'))


def state_language(episode: Optional[Mapping[str, Any]], *, hint_language: Optional[str] = None) -> str:
    """The language the prior state (title, bullets) is actually written in.

    Stamped episodes answer from the stamp. Legacy documents predate it, so their
    state text is detected once per update (cached by ``detect_language``); a state
    too short to detect counts as unknown and is never repaired.
    """
    stored = stored_language(episode)
    if stored:
        return stored
    from utils.translation_language import detect_language

    parts = [str((episode or {}).get('title') or '')] + [str(b) for b in (episode or {}).get('bullets') or []][:3]
    text = ' '.join(part for part in parts if part)
    if len(text) < _MIN_STATE_DETECT_CHARS:
        return ''
    # detect_language only runs when the hint is a code it knows; a sentinel hint would mute it.
    hint = normalize_language(hint_language) or 'en'
    return normalize_language(detect_language(text, hint_language=hint))


def resolve_episode_language(
    uid: str,
    episode: Optional[Mapping[str, Any]],
    conversation_language: Optional[str],
    *,
    preference: Optional[str] = None,
) -> str:
    """Preference, then the language the episode already speaks, then the conversation's, then English."""
    if preference is None:
        from utils.llm.output_language import language_preference

        preference = language_preference(uid)
    preferred = normalize_language(preference)
    if preferred:
        return preferred
    stored = stored_language(episode)
    if stored:
        return stored
    return normalize_language(conversation_language) or 'en'


def repair_instruction(prior_language: str, output_language: str) -> str:
    """The directive that rewrites a wrong-language state instead of feeding it back."""
    return (
        f'The episode state so far is written in {prior_language}, not {output_language}. '
        f'Rewrite the whole state - topic, bullets, open questions - in {output_language} as part of '
        'this update, keeping names and quoted words verbatim. Do not drop information in the rewrite.'
    )
