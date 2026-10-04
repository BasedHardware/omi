"""Stamp disambiguation among generations that strictly contain a segment.

Stamp appends and smart merge can grow one generation's stored interval over
its successor's, and a rollover mints its row at wall-clock ``created_at``
while ``started_at`` can be back-dated to cover pre-rollover buffered audio,
so no local clock reliably names the owner of an overlapped segment. Only the
phone's stamp can: among the caller's filtered matches it must name exactly
one canonical row — by row id or by canonical id — or the overlap stays
undecidable and the segment keeps no target. Stdlib only; callers pass objects
with ``id``,
``canonical``, ``start``, ``end`` and ``deleted`` attributes.
"""

from __future__ import annotations

from typing import Optional, Sequence


def pick_overlapping(matches: Sequence, stamped_target: Optional[str]):
    """The already-filtered match the stamp selects, or ``None`` while it stays ambiguous."""
    matching = [
        generation
        for generation in matches
        if generation.id == stamped_target or generation.canonical == stamped_target
    ]
    canonicals = {generation.canonical for generation in matching}
    if len(canonicals) != 1:
        return None
    canonical = canonicals.pop()
    for generation in matching:
        if generation.id == canonical and not generation.deleted:
            return generation
    return min(matching, key=lambda generation: generation.id)
