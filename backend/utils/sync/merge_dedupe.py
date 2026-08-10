"""Shrink-only merge dedupe for offline sync transcript segments.

Exact absolute-range keys cover 207 retries. Live+offline / clock-offset merges
need text+slop matching so the same spoken lines are not appended twice (#4769).

Text+slop is batch-gated and length-gated so short repeated phrases ("yeah",
"okay") inside the slop window are not silently dropped.
"""

from __future__ import annotations

_MERGE_TEXT_DUP_SLOP_SECONDS = 10 * 60
_MERGE_TEXT_DUP_DURATION_RATIO = 0.25
# Short backchannels are common twice in one conversation; never text-dedupe them.
_MERGE_TEXT_DUP_MIN_CHARS = 20
_MERGE_TEXT_DUP_MIN_WORDS = 4


def _normalize_merge_segment_text(text: str | None) -> str:
    return ' '.join((text or '').strip().lower().split())


def _text_eligible_for_slop_dedupe(text: str) -> bool:
    if len(text) >= _MERGE_TEXT_DUP_MIN_CHARS:
        return True
    return len(text.split()) >= _MERGE_TEXT_DUP_MIN_WORDS


def _segment_abs_range(segment: dict) -> tuple[float, float]:
    abs_start = float(segment['timestamp'])
    duration = float(segment['end']) - float(segment['start'])
    return abs_start, abs_start + duration


def _is_text_clock_offset_duplicate(
    *,
    text: str,
    abs_start: float,
    duration: float,
    existing_text_index: list[dict],
    text_match_slop_seconds: float,
    duration_ratio_slop: float,
) -> bool:
    if not _text_eligible_for_slop_dedupe(text):
        return False
    for existing in existing_text_index:
        if existing['text'] != text:
            continue
        existing_duration = existing['duration']
        max_duration = max(duration, existing_duration, 1e-3)
        if abs(duration - existing_duration) / max_duration > duration_ratio_slop:
            continue
        if abs(abs_start - existing['abs_start']) <= text_match_slop_seconds:
            return True
    return False


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
    3. Batch-gated text+slop for clock-offset live+offline duplicates (#4769):
       only when enough eligible lines match (all remaining, or >=2), and only
       for text long enough that short repeated phrases are kept.
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

    survivors = []
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

        survivors.append(segment)

    if not survivors or not existing_text_index:
        return survivors

    text_dup_flags = []
    for segment in survivors:
        abs_start, abs_end = _segment_abs_range(segment)
        text = _normalize_merge_segment_text(segment.get('text'))
        duration = max(0.0, abs_end - abs_start)
        text_dup_flags.append(
            _is_text_clock_offset_duplicate(
                text=text,
                abs_start=abs_start,
                duration=duration,
                existing_text_index=existing_text_index,
                text_match_slop_seconds=text_match_slop_seconds,
                duration_ratio_slop=duration_ratio_slop,
            )
        )

    text_dup_count = sum(1 for flag in text_dup_flags if flag)
    # Batch gate: full remaining batch is a re-upload, or multiple lines share
    # the same clock-offset fingerprint (#4769 "every line duplicated").
    apply_text_dedupe = text_dup_count >= 2 or (text_dup_count == len(survivors) and text_dup_count >= 1)
    if not apply_text_dedupe:
        return survivors

    return [segment for segment, is_dup in zip(survivors, text_dup_flags) if not is_dup]
