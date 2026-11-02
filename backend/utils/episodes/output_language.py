"""L3 output-language authority at the episode prompt boundary.

The moment prompt is pinned to one resolved language on every path (kill switch
``EPISODE_OUTPUT_LANGUAGE_PIN``): the user's explicit preference first, then the
conversation's dominant language tag — never the newest moment's speech or the
episode's previous output deciding on its own. Blank and sentinel tags
(``multi``, ``auto``, …) count as unset, so they never reach a prompt.

A state written in a different language (the wrong-language incident) is not fed
back verbatim: ``repair_instruction`` tells the model to rewrite it in the
resolved language as part of the next update, and the episode only stamps
``output_language`` once the state matches it.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Optional

from config.refactor_modes import serving_for
from utils.llm.output_language import language_preference as read_language_preference, normalize_language
from utils.translation_language import detect_language

# langdetect is unreliable on short text (backend AGENTS.md); a shorter state carries no
# language worth repairing anyway.
_MIN_STATE_DETECT_CHARS = 20
_SEGMENT_LANGUAGE_FIELDS = ('language', 'language_code', 'language_tag', 'detected_language', '_provider_language')


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
        return invoke(
            account,
            [*messages, ('system', f'Write all output in {language}. Keep names and quoted words verbatim.')],
        )

    return with_language


def stored_language(episode: Optional[Mapping[str, Any]]) -> str:
    """The language the episode document says its state is written in ('' when unstamped)."""
    return normalize_language((episode or {}).get('output_language'))


def detected_state_language(episode: Optional[Mapping[str, Any]], *, hint_language: Optional[str] = None) -> str:
    """Detect the language in current state text, ignoring any previous stamp."""
    parts = [str((episode or {}).get('title') or '')] + [str(b) for b in (episode or {}).get('bullets') or []][:3]
    text = ' '.join(part for part in parts if part)
    if len(text) < _MIN_STATE_DETECT_CHARS:
        return ''
    # The detector's hint only gates whether it runs; use its broad supported baseline
    # rather than letting a regional/unsupported target code mute output verification.
    return normalize_language(detect_language(text, hint_language='en'))


def state_language(episode: Optional[Mapping[str, Any]], *, hint_language: Optional[str] = None) -> str:
    """The language the prior state is written in, checking text even when stamped."""
    return detected_state_language(episode, hint_language=hint_language) or stored_language(episode)


def languages_match(left: Optional[str], right: Optional[str]) -> bool:
    """Compare safe language tags at the base-language precision of local detection."""
    a, b = normalize_language(left), normalize_language(right)
    return bool(a and b and (a == b or a.split('-', 1)[0] == b.split('-', 1)[0]))


def dominant_segment_language(segments: Any) -> str:
    """Choose the character-weighted dominant language from an in-memory segment batch.

    Prefer an existing per-segment language tag. When the stream did not retain one,
    detect only sufficiently long segments locally; no provider call or database read
    is made. Short/noisy text is deliberately left unknown.
    """
    weights: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for segment in segments or ():
        if not isinstance(segment, Mapping):
            continue
        text = str(segment.get('text') or '')
        letters = sum(char.isalpha() for char in text)
        language = ''
        for key in _SEGMENT_LANGUAGE_FIELDS:
            language = normalize_language(segment.get(key))
            if language:
                break
        if not language and letters >= _MIN_STATE_DETECT_CHARS:
            language = normalize_language(detect_language(text, hint_language='en'))
        if language:
            first_seen.setdefault(language, len(first_seen))
            weights[language] += max(letters, 1)
    if not weights:
        return ''
    return max(weights, key=lambda language: (weights[language], -first_seen[language]))


def resolve_episode_language(
    uid: str,
    conversation_language: Optional[str],
    *,
    preference: Optional[str] = None,
) -> str:
    """Preference, then the conversation's dominant language tag, then English.

    The stored episode language describes the prior state for comparison; it is
    never an authority over the current resolved output language.
    """
    if preference is None:
        preference = language_preference(uid)
    preferred = normalize_language(preference)
    if preferred:
        return preferred
    return normalize_language(conversation_language) or 'en'


def language_preference(uid: str) -> str:
    """Read the user's safe, normalized output-language preference once at the boundary."""
    return read_language_preference(uid)


def repair_instruction(prior_language: str, output_language: str) -> str:
    """The directive that rewrites a wrong-language state instead of feeding it back."""
    return (
        f'The episode state so far is written in {prior_language}, not {output_language}. '
        f'Rewrite the whole state - topic, bullets, open questions - in {output_language} as part of '
        'this update, keeping names and quoted words verbatim. Do not drop information in the rewrite.'
    )
