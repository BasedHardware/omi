from __future__ import annotations

from typing import Dict, List, Tuple

from models.transcript_segment import TranscriptSegment


def _should_merge(prev: Dict, curr: Dict) -> bool:
    """Return ``True`` if two consecutive same‑speaker segments should be merged.

    The logic mirrors the existing chronological‑continuation helper used for
    cross‑speaker repairs:

    * Segments must share the same ``speaker``.
    * ``prev['end']`` must be greater than or equal to ``curr['start']`` **or**
      the gap between them must be less than three seconds.
    """
    if prev["speaker"] != curr["speaker"]:
        return False
    # Overlap or acceptable gap (less than 3 seconds)
    return prev["end"] >= curr["start"] or (curr["start"] - prev["end"]) < 3.0


def merge_live_segments(
    live_segments: List[Dict],
    saved_segments: List[Dict],
    _unused: Dict,
) -> Tuple[List[Dict], List[str]]:
    """Merge newly received ``live_segments`` with previously saved ones.

    The function now:
    1. Combines both lists.
    2. Sorts the combined list by ``start`` time.
    3. Iteratively merges consecutive same‑speaker segments when
       ``_should_merge`` deems it appropriate.
    4. Returns the merged list and a list of segment IDs that were removed
       during the merge.
    """
    # Combine and sort by start time to guarantee chronological order.
    combined = sorted(live_segments + saved_segments, key=lambda s: s["start"])

    merged: List[Dict] = []
    removed_ids: List[str] = []

    for segment in combined:
        if not merged:
            merged.append(segment.copy())
            continue
        prev = merged[-1]
        if _should_merge(prev, segment):
            # Merge the current segment into the previous one.
            prev["end"] = max(prev["end"], segment["end"])
            prev["text"] = f"{prev['text']} {segment['text']}"
            # Record the ID of the segment that got absorbed.
            removed_ids.append(segment["id"])
        else:
            merged.append(segment.copy())

    return merged, removed_ids
