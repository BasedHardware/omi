"""Transcript rendering for episode moments (owner: refactor lane L3).

Contract stub: current behavior. L3 replaces the body with the shared notes renderer
(cluster keys, owner gate, speaker evidence); L4 calls it from ``service.py``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def name_segments(segments: Sequence[Mapping[str, Any]], names: Mapping[str, str]) -> list[dict[str, Any]]:
    out = []
    for segment in segments:
        item = dict(segment)
        if item.get('person_id') and names.get(str(item['person_id'])):
            item['person_name'] = names[str(item['person_id'])]
        out.append(item)
    return out
