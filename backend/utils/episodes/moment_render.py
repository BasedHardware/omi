"""Name-only segment projection for episode moments (L3 contract for L4)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def name_segments(segments: Sequence[Mapping[str, Any]], names: Mapping[str, str]) -> list[dict[str, Any]]:
    """Prepare prompt-only copies with People names attached. Keep this cross-lane signature."""
    out = []
    for segment in segments:
        item = dict(segment)
        if item.get('person_id') and names.get(str(item['person_id'])):
            item['person_name'] = names[str(item['person_id'])]
        out.append(item)
    return out
