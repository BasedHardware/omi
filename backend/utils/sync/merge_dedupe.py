"""Shrink-only merge dedupe for offline sync transcript segments.

Exact absolute-range keys cover 207 retries. Live+offline / clock-offset merges
need text+slop matching so the same spoken lines are not appended twice (#4769).

Text+slop is batch-gated and length-gated so short repeated phrases ("yeah",
"okay") inside the slop window are not silently dropped.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from statistics import median

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


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def fuzzy_live_match(left: str, right: str) -> bool:
    """Order-sensitive only; short instructions require exact tokens.

    Eight-to-eleven-token lines cannot safely tolerate a changed instruction.
    Longer lines require 0.95, deliberately stricter than the requested 0.9.
    """
    a, b = _tokens(left), _tokens(right)
    if min(len(a), len(b)) < 8:
        return False
    if min(len(a), len(b)) < 12:
        return a == b
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.95


def _same_known_speaker(left: dict, right: dict) -> bool:
    # Provider-local speaker numbers are not cross-provider identity evidence.
    if left.get('person_id') or right.get('person_id'):
        return bool(left.get('person_id') and left.get('person_id') == right.get('person_id'))
    return left.get('is_user') is True and right.get('is_user') is True


def _live_windows(existing: list[dict]) -> list[dict]:
    ordered = sorted(existing, key=lambda item: item['abs_start'])
    windows = list(ordered)
    for index, first in enumerate(ordered):
        text, end, members = first['text'], first['abs_start'] + first['duration'], first['members']
        for following in ordered[index + 1 : index + 3]:
            if following['abs_start'] - end > 15 or not _same_known_speaker(first, following):
                break
            text += ' ' + following['text']
            end = max(end, following['abs_start'] + following['duration'])
            members += following['members']
            windows.append(dict(first, text=text, duration=end - first['abs_start'], members=members))
    return windows


def _fuzzy_survivors(existing: list[dict], incoming: list, slop: float, offset: float | None) -> list:
    if offset is None:
        anchors, used_members, used_texts = [], set(), set()
        for segment in incoming:
            text = tuple(_tokens(segment.get('text', '')))
            if len(text) < 8 or text in used_texts:
                continue
            candidates = [
                item
                for item in existing
                if abs(float(segment['timestamp']) - item['abs_start']) <= 90
                and _same_known_speaker(segment, item)
                and tuple(_tokens(item['text'])) == text
                and not used_members.intersection(item['members'])
            ]
            # Multiple possible occurrences cannot corroborate a clock.
            if len(candidates) != 1:
                continue
            item = candidates[0]
            anchors.append(item['abs_start'] - float(segment['timestamp']))
            used_members.update(item['members'])
            used_texts.add(text)
        if len(anchors) < 2 or max(anchors) - min(anchors) > 2:
            return incoming
        offset = median(anchors)
    # The broad clock search is not a license to delete a later saying.
    tolerance = min(2.0, slop)
    consumed, survivors = set(), []
    for segment in incoming:
        candidates = [
            item
            for item in existing
            if not consumed.intersection(item['members'])
            and abs(float(segment['timestamp']) + offset - item['abs_start']) <= tolerance
            and _same_known_speaker(segment, item)
            and fuzzy_live_match(segment.get('text', ''), item['text'])
        ]
        if not candidates:
            survivors.append(segment)
            continue
        item = min(candidates, key=lambda item: abs(float(segment['timestamp']) + offset - item['abs_start']))
        consumed.update(item['members'])
    return survivors


def dedupe_segments_for_merge(
    conversation_started_at: float,
    existing_segments: list,
    incoming_segments: list,
    *,
    text_match_slop_seconds: float = _MERGE_TEXT_DUP_SLOP_SECONDS,
    duration_ratio_slop: float = _MERGE_TEXT_DUP_DURATION_RATIO,
    single_match_slop_seconds: float = 0,
    fuzzy_live_overlap: bool = False,
    estimated_offset_seconds: float | None = None,
) -> list:
    """Return incoming segments that are not already represented on the conversation.

    Matching order (fail-closed / shrink-only):
    1. Exact absolute wall-clock range (legacy retry after 207).
    2. Exact conversation-relative range (same place on the timeline).
    3. Batch-gated text+slop for clock-offset live+offline duplicates (#4769):
       only when enough eligible lines match (all remaining, or >=2), and only
       for text long enough that short repeated phrases are kept.
    4. For a live explicit target, one eligible line in a mixed batch may be
       removed with the caller's much tighter single-match time bound.
    """
    existing_abs = set()
    existing_rel = set()
    existing_text_index = []

    for index, segment in enumerate(existing_segments):
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
                    'person_id': segment.get('person_id'),
                    'is_user': segment.get('is_user'),
                    'members': (index,),
                }
            )

    if fuzzy_live_overlap:
        # Even exact timeline ranges require corroboration on the fleet path.
        return _fuzzy_survivors(
            _live_windows(existing_text_index),
            incoming_segments,
            max(60.0, text_match_slop_seconds),
            estimated_offset_seconds,
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
    close_dup_flags = []
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
        close_dup_flags.append(
            single_match_slop_seconds > 0
            and _is_text_clock_offset_duplicate(
                text=text,
                abs_start=abs_start,
                duration=duration,
                existing_text_index=existing_text_index,
                text_match_slop_seconds=single_match_slop_seconds,
                duration_ratio_slop=duration_ratio_slop,
            )
        )

    text_dup_count = sum(1 for flag in text_dup_flags if flag)
    # Batch gate: full remaining batch is a re-upload, or multiple lines share
    # the same clock-offset fingerprint (#4769 "every line duplicated").
    apply_text_dedupe = text_dup_count >= 2 or (text_dup_count == len(survivors) and text_dup_count >= 1)
    if not apply_text_dedupe:
        return [segment for segment, is_dup in zip(survivors, close_dup_flags) if not is_dup]

    return [segment for segment, is_dup in zip(survivors, text_dup_flags) if not is_dup]
