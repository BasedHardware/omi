"""Shrink-only merge dedupe for offline sync transcript segments.

Exact absolute-range keys cover 207 retries. Live+offline / clock-offset merges
need text+slop matching so the same spoken lines are not appended twice (#4769).
"""

from __future__ import annotations

_MERGE_TEXT_DUP_SLOP_SECONDS = 10 * 60
_MERGE_TEXT_DUP_DURATION_RATIO = 0.25


def _normalize_merge_segment_text(text: str | None) -> str:
    return ' '.join((text or '').strip().lower().split())


def _segment_abs_range(segment: dict) -> tuple[float, float]:
    abs_start = float(segment['timestamp'])
    duration = float(segment['end']) - float(segment['start'])
    return abs_start, abs_start + duration


def dedupe_segments_for_merge(
    conversation_started_at: float,
    existing_segments: list,
    incoming_segments: list,
    *,
    text_match_slop_seconds: float = _MERGE_TEXT_DUP_SLOP_SECONDS,
    duration_ratio_slop: float = _MERGE_TEXT_DUP_DURATION_RATIO,
) -> list:
    """Return incoming segments that are not already represented on the conversation.

    Matching order (fail-closed / shrink-only):
    1. Exact absolute wall-clock range (legacy retry after 207).
    2. Exact conversation-relative range (same place on the timeline).
    3. Same normalized text + similar duration + absolute starts within slop
       (live+offline / clock-offset duplicates — #4769).
    """
    existing_abs = set()
    existing_rel = set()
    existing_text_index = []

    for segment in existing_segments:
        abs_start, abs_end = _segment_abs_range(segment)
        existing_abs.add((round(abs_start, 2), round(abs_end, 2)))
        rel_start = float(segment['start'])
        rel_end = float(segment['end'])
        existing_rel.add((round(rel_start, 2), round(rel_end, 2)))
        text = _normalize_merge_segment_text(segment.get('text'))
        if text:
            existing_text_index.append(
                {
                    'text': text,
                    'abs_start': abs_start,
                    'duration': max(0.0, abs_end - abs_start),
                }
            )

    deduped_segments = []
    for segment in incoming_segments:
        abs_start, abs_end = _segment_abs_range(segment)
        abs_key = (round(abs_start, 2), round(abs_end, 2))
        if abs_key in existing_abs:
            continue

        conv_rel_start = abs_start - conversation_started_at
        conv_rel_end = abs_end - conversation_started_at
        rel_key = (round(conv_rel_start, 2), round(conv_rel_end, 2))
        if rel_key in existing_rel:
            continue

        text = _normalize_merge_segment_text(segment.get('text'))
        duration = max(0.0, abs_end - abs_start)
        if text:
            is_text_duplicate = False
            for existing in existing_text_index:
                if existing['text'] != text:
                    continue
                existing_duration = existing['duration']
                max_duration = max(duration, existing_duration, 1e-3)
                if abs(duration - existing_duration) / max_duration > duration_ratio_slop:
                    continue
                if abs(abs_start - existing['abs_start']) <= text_match_slop_seconds:
                    is_text_duplicate = True
                    break
            if is_text_duplicate:
                continue

        deduped_segments.append(segment)

    return deduped_segments
