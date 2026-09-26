"""The §1.7 deterministic minimum — the exact no-LLM state a free conversation lands in.

Spec: `omi-knowledge-base/projects/local-models-free-tier/implementation/`
`10-backend-plumbing.md` §1.7. Referenced by W1/W2/W3/W4 and by the desktop
client's own copy (`desktop/macos/Desktop/Sources/LocalInference/`
`DeterministicConversationMinimum.swift`, S9) — keep the two algorithms in step.

Everything here is pure: same input, same output, and the only clock read is
``started_at``. Nothing in this module may import a model client, and the
guardrail test asserts that. This is what makes the minimum usable as the
deny-fallback for ``authorize_managed_compute``: it cannot itself spend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from datetime import tzinfo
from typing import Any, Callable, Iterable, List, Optional

from models.conversation_enums import CategoryEnum
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.

# ~60 chars, cut on a word boundary. Long enough for a real first sentence,
# short enough to stay one line in every conversation list we ship.
TITLE_MAX_CHARS = 60

# The schema requires a category and we refuse to infer one without a model.
MINIMUM_CATEGORY = CategoryEnum.other

DEFAULT_SOURCE_LABEL = 'Recording'

_SENTENCE_TERMINATORS = frozenset('.!?')


def transcript_text(conversation: Any) -> str:
    """Flatten a conversation's transcript segments into one space-joined string.

    Segment order is the transcript's own order. Blank segments are dropped so a
    leading empty segment cannot swallow the title.
    """
    segments: Iterable[Any] = list(getattr(conversation, 'transcript_segments', None) or [])
    parts: List[str] = []
    for segment in segments:
        text = (getattr(segment, 'text', '') or '').strip()
        if text:
            parts.append(text)
    return ' '.join(parts)


def first_sentence(text: str) -> str:
    """The first sentence of ``text``: everything up to and including the first
    ``.``/``!``/``?``, or the whole string when it has no terminator."""
    collapsed = ' '.join((text or '').split())
    if not collapsed:
        return ''
    for index, character in enumerate(collapsed):
        if character in _SENTENCE_TERMINATORS:
            return collapsed[: index + 1]
    return collapsed


def truncate_on_word_boundary(text: str, max_chars: int = TITLE_MAX_CHARS) -> str:
    """Cut ``text`` to at most ``max_chars``, never mid-word when a boundary exists."""
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    boundary = head.rfind(' ')
    if boundary <= 0:
        # One unbroken token longer than the budget: a hard cut is the only cut.
        return head
    return head[:boundary].rstrip()


def fallback_title(
    started_at: Optional[datetime],
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
    tz_name: Optional[str] = None,
) -> str:
    """``"Recording · 3:14 PM"`` — the empty-transcript title.

    ``started_at`` is the only clock. A naive datetime is read as UTC.
    ``tz_name`` is the user's IANA zone when the caller has one; without it the
    time is rendered in UTC, which is wrong for the user's wall clock but never
    non-deterministic. Callers that can cheaply resolve the zone should.
    """
    label = (source_label or '').strip() or DEFAULT_SOURCE_LABEL
    moment = started_at
    if moment is None:
        # No transcript and no start time: the label alone still satisfies the
        # non-empty-title invariant `_get_conversation_obj` reads as "discarded".
        return label
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    zone = _resolve_zone(tz_name)
    if zone is not None:
        moment = moment.astimezone(zone)
    # %-I is a GNU/BSD extension; both CI and Cloud Run are POSIX. Strip the
    # zero by hand so the format is portable rather than platform-lucky.
    rendered = moment.strftime('%I:%M %p').lstrip('0')
    return f'{label} · {rendered}'


def _resolve_zone(tz_name: Optional[str]) -> Optional[tzinfo]:
    if not tz_name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz_name)
    except Exception:
        # An unknown or malformed zone falls back to UTC rather than raising:
        # this path is the fail-closed store and must not be able to throw.
        return None


def deterministic_minimum_title(
    conversation: Any,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
    tz_name_provider: Optional[Callable[[], Optional[str]]] = None,
) -> str:
    """§1.7's title. Never empty — an empty title marks a conversation discarded.

    ``tz_name_provider`` is called at most once, and only when the transcript is
    empty, so the common path costs no lookup.
    """
    sentence = first_sentence(transcript_text(conversation))
    if sentence:
        return truncate_on_word_boundary(sentence)
    tz_name = tz_name_provider() if tz_name_provider is not None else None
    return fallback_title(
        getattr(conversation, 'started_at', None),
        source_label=source_label,
        tz_name=tz_name,
    )


def build_deterministic_minimum_structured(
    conversation: Any,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
    tz_name_provider: Optional[Callable[[], Optional[str]]] = None,
) -> Structured:
    """The whole §1.7 row: deterministic title, empty overview, category ``other``,
    no action items, no events. Every other field keeps its model default."""
    return Structured(
        title=deterministic_minimum_title(
            conversation,
            source_label=source_label,
            tz_name_provider=tz_name_provider,
        ),
        overview='',
        category=MINIMUM_CATEGORY,
        sections=[],
        action_items=[],
        events=[],
    )
