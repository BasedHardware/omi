"""Narrow, conservative reference checks over extraction evidence; no model calls."""

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from config.refactor_modes import serving_for, shadow_or_serve

logger = logging.getLogger(__name__)
VALIDITY_MODE_ENV = 'ACTION_ITEM_VALIDITY_MODE'
VALIDITY_SERVE_PERCENT_ENV = 'ACTION_ITEM_VALIDITY_MODE_SERVE_PERCENT'
VALIDITY_SERVE_UID_SHA256S_ENV = 'ACTION_ITEM_VALIDITY_MODE_SERVE_UID_SHA256S'

_PLACEHOLDER = re.compile(r'\b(?:speaker\s*\d+|the other (?:speaker|person|one)|another speaker)\b', re.I)
_DEICTIC_ONLY = re.compile(
    r'^(?:send|email|share|bring|move|put|do|review|check|follow up on)\s+'
    r'(?:it|this|that|them)(?:\s+(?:here|there))?[.!?]*$',
    re.I,
)
_GENERIC = frozenset(
    'i you he she we they it this that them here there the a an to for of on in with '
    'will would should can could said says send email share bring move put do review check '
    'follow up speaker person other another one task agreed promised please'.split()
)


def field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)


def unresolved_reference(
    description: str | None,
    *,
    context: str = '',
    source_texts: Sequence[str] = (),
) -> str | None:
    """Abstain when context may resolve the reference; names are never identity proof.

    This is a recall-protecting heuristic, not an assertion of semantic accuracy.
    Speaker identity stays with the shared capture projection; this policy does
    not infer a task's subject or counterpart from the speaking voice.
    """
    text = (description or '').strip()
    placeholder = bool(_PLACEHOLDER.search(text))
    if not placeholder and not _DEICTIC_ONLY.fullmatch(text):
        return None
    evidence = ' '.join((context, *source_texts))
    meaningful = {word.casefold() for word in re.findall(r'\w+', evidence)} - _GENERIC
    if meaningful:
        return None
    return 'unresolved_reference'


def select_valid_items(uid: str, items: Sequence[Any], *, transcript_segments: Sequence[Any] = ()) -> list[Any]:
    """Run after V2 selection. Shadow never mutates candidates or serving output."""
    if not shadow_or_serve(VALIDITY_MODE_ENV):
        return list(items)
    segments = {field(row, 'id'): row for row in transcript_segments}
    selected = []
    unresolved = 0
    for item in items:
        ids = field(item, 'source_segment_ids') or ()
        if ids and not transcript_segments:
            # Legacy desktop prefilter lacks capture context; the capture adapter
            # repeats this final check with the actual segments and shared roles.
            selected.append(item)
            continue
        reason = unresolved_reference(
            field(item, 'description'),
            context=field(item, 'context') or '',
            source_texts=[field(segments[sid], 'text') or '' for sid in ids if sid in segments],
        )
        if reason:
            unresolved += 1
        else:
            selected.append(item)
    # Bounded, aggregate, text-free receipt; no uid/description/source labels.
    logger.info(
        'event=action_item_validity reason=unresolved_reference count=%d serving=%s',
        unresolved,
        serving_for(VALIDITY_MODE_ENV, uid),
    )
    return selected if serving_for(VALIDITY_MODE_ENV, uid) else list(items)
