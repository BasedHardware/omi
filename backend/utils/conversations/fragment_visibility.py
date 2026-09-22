"""Visibility policy for low-signal sync fragments.

Sync keeps short filler speech as a durable, reviewable record so a later
chunk can promote the complete recording.  The original sync rollout wrote
those records with ``discarded=False``; this module lets read paths apply the
same policy to those legacy rows without a destructive backfill.

This predicate deliberately uses only server-owned metadata.  It never
decodes transcript text, and it never treats duration by itself as evidence
that a recording is low signal.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _value(value: Any) -> Any:
    """Return enum values without importing model modules into read paths."""
    return getattr(value, 'value', value)


def _has_meaningful_enrichment(data: Mapping[str, Any]) -> bool:
    """Protect a review row that already has a generated or client projection."""
    structured = data.get('structured')
    if isinstance(structured, Mapping):
        if str(structured.get('overview') or '').strip():
            return True
        for field in ('sections', 'action_items', 'events'):
            if structured.get(field):
                return True
    # ``client_processing`` is an explicit client projection and is therefore
    # user-visible curation even when the server overview is still empty.
    client_processing = data.get('client_processing')
    return isinstance(client_processing, Mapping) and client_processing.get('schema_version') == 1


def is_low_signal_sync_fragment(data: Mapping[str, Any] | None) -> bool:
    """Whether ``data`` is an uncurated completed sync review fragment.

    Review is intentionally narrow.  Live targets, shared/curated rows,
    photo-bearing rows, and already enriched rows remain visible.  A row with
    ``sync_relevance_user_kept`` is the durable opt-out written by the restore
    path and must not be hidden again by a later sync append.
    """
    if not data:
        return False
    if _value(data.get('status')) != 'completed':
        return False
    if data.get('sync_relevance') != 'review':
        return False
    if data.get('sync_relevance_user_kept'):
        return False
    if data.get('sync_live_target'):
        return False
    if data.get('has_photos') or data.get('photos'):
        return False
    if data.get('user_title') or data.get('starred') or data.get('folder_user_set'):
        return False
    if _value(data.get('visibility', 'private')) not in (None, 'private'):
        return False
    return not _has_meaningful_enrichment(data)


def is_effectively_discarded(data: Mapping[str, Any] | None) -> bool:
    """Whether normal list/search readers should treat a row as discarded."""
    return bool(data) and (bool(data.get('discarded')) or is_low_signal_sync_fragment(data))
