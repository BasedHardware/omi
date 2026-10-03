"""Deterministic selection among generations that strictly contain a segment.

Stamp appends and smart merge can grow one generation's stored interval over
its successor's, and a rollover mints its row at wall-clock ``created_at``
while ``started_at`` can be back-dated to cover pre-rollover buffered audio.
When several strict matches canonicalize differently the bound row is still
decidable: clamp each stored start to the row's creation time — a creation
interval proxy, not a proof of coverage — and prefer the generations whose
proxy interval holds the segment, falling back to every strict match when
none does. Pick the latest ``(created, start, id)`` so input order never
changes the outcome. Stdlib only; callers pass objects with ``id``, ``start``,
``end`` and ``created`` attributes.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


def effective_created(start: float, created: Optional[float]) -> float:
    """Creation time usable for ordering; absent or non-finite falls back to ``start``."""
    return created if isinstance(created, (int, float)) and math.isfinite(created) else start


def own_interval_start(start: float, created: Optional[float]) -> float:
    """The row's stored start clamped to its creation time (creation interval proxy)."""
    return max(start, effective_created(start, created))


def pick_overlapping(generations: Sequence, start: float, end: float):
    """The strict match to bind, or ``None`` only when ``generations`` is empty."""
    covering = [
        generation
        for generation in generations
        if own_interval_start(generation.start, generation.created) <= start and end <= generation.end
    ]
    pool = covering if covering else list(generations)
    if not pool:
        return None
    return max(
        pool,
        key=lambda generation: (
            effective_created(generation.start, generation.created),
            generation.start,
            generation.id,
        ),
    )
