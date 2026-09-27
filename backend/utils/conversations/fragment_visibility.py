"""Which sync review fragments intake stores as discarded.

Sync keeps short filler speech as a durable, reviewable record so a later
chunk can promote the complete recording; intake stores it ``discarded=True``
and every reader trusts that stored flag.  Rows written before intake did so
are rewritten by ``scripts/conversation_relevance_backfill.py``.

This predicate deliberately uses only server-owned metadata.  It never
decodes transcript text, and it never treats duration by itself as evidence
that a recording is low signal.  The content verdict itself belongs to the
relevance step (``utils/conversations/relevance.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _value(value: Any) -> Any:
    """Return enum values without importing model modules into read paths."""
    return getattr(value, 'value', value)


def is_user_curated(data: Mapping[str, Any]) -> bool:
    """Whether a user action (or a live owner) protects this row from any relevance discard.

    Only user actions count. A generated summary is not evidence that anyone
    cares: the pipeline writes one for whatever it processes.
    """
    return bool(
        data.get('sync_relevance_user_kept')
        or data.get('sync_live_target')
        or data.get('has_photos')
        or data.get('photos')
        or data.get('user_title')
        or data.get('starred')
        or data.get('folder_user_set')
        or _value(data.get('visibility', 'private')) not in (None, 'private')
    )


def is_low_signal_sync_fragment(data: Mapping[str, Any] | None) -> bool:
    """Whether ``data`` is an uncurated completed sync review fragment."""
    if not data:
        return False
    if _value(data.get('status')) != 'completed':
        return False
    if data.get('sync_relevance') != 'review':
        return False
    return not is_user_curated(data)
