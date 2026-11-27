"""Bounded transcript evidence for the negotiated conversation Home list."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from math import isfinite
from typing import Any

from database.home_feed_fields import LIST_TRANSCRIPT as FIELD, LIST_TRANSCRIPT_SOURCE_VERSION as SOURCE_VERSION
from utils.home_feed.projection import reveal_display, seal_display
from utils.home_feed.card_content import SCHEMA
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import present

HEADER = 'X-Omi-Home-List-Transcript'
VERSION = '1'


def stamp(uid: str, segments: Sequence[Any], *, preview_needed: bool) -> str | None:
    """Capture the values Home derives from the inline transcript."""
    if not segments:
        return None
    start, end = float('inf'), float('-inf')
    prefix = ''
    has_owner_speech = False
    for segment in segments:
        if not isinstance(segment, dict):
            return None
        text, first, last, owner = (segment.get(key) for key in ('text', 'start', 'end', 'is_user'))
        if not isinstance(text, str) or type(owner) is not bool:
            return None
        if not isinstance(first, (int, float)) or not isinstance(last, (int, float)):
            return None
        if isinstance(first, bool) or isinstance(last, bool):
            return None
        try:
            if not isfinite(first) or not isfinite(last):
                return None
        except OverflowError:
            return None
        start, end = min(start, first), max(end, last)
        has_owner_speech = has_owner_speech or owner
        if preview_needed and len(prefix) < 161:
            words = text.strip()
            if words:
                prefix = (prefix + (' ' if prefix else '') + words[:161])[:161]
    try:
        return seal_display(
            uid,
            {
                'schema': SCHEMA,
                'has_owner_speech': has_owner_speech,
                'preview_prefix': prefix if preview_needed else None,
                'duration_seconds': max(0, int(end - max(0, start))),
            },
        )
    except (UnicodeError, OverflowError, ValueError):
        # Optional presentation must never block a transcript write.
        return None


def shows_preview(row: Mapping[str, Any]) -> bool:
    return bool(
        (row.get('discarded') and row.get('content_kind') not in ('media', 'noise')) or row.get('processing_deferred')
    )


def _title_independent(row: Mapping[str, Any]) -> bool:
    structured = row.get('structured') or {}
    if not str(structured.get('title') or '').strip():
        return False
    if structured.get('title_provenance') or str(row.get('user_title') or '').strip():
        return True
    # See home_titles.neutralize_minimum_title. Keep the full reader for
    # unmarked echo titles and notes still awaiting a real summary.
    start, end = row.get('started_at'), row.get('finished_at')
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return False
    decision = row.get('relevance_decision') or {}
    return (
        present(structured)
        and (end - start).total_seconds() > 60
        and row.get('summary_blocked_reason') != 'content_below_floor'
        and decision.get('reason') != 'content_below_floor'
        and not summary_owed(row)
    )


def evidence(uid: str, row: Mapping[str, Any]) -> dict[str, bool | int | str] | None:
    if (
        not row.get('home_source_version')
        or row.get(SOURCE_VERSION) != row['home_source_version']
        or row.get('has_transcript_corrections')
        or row.get('is_locked')
        or row.get('visibility') != 'private'
        or row.get('status') != 'completed'
        or row.get('record_lane_owner')
        or row.get('record_transcription_empty')
        or row.get('v3_derived')
    ):
        return None
    # Legacy clock hydration may derive recorded time from transcript segments.
    recorded_start, recorded_end = row.get('recorded_start'), row.get('recorded_end')
    if (
        not isinstance(recorded_start, datetime)
        or not isinstance(recorded_end, datetime)
        or recorded_end < recorded_start
    ):
        return None
    if not _title_independent(row):
        return None
    value = reveal_display(uid, row.get(FIELD))
    if value is None:
        return None
    owner, preview, duration = (value.get(key) for key in ('has_owner_speech', 'preview_prefix', 'duration_seconds'))
    if type(owner) is not bool:
        return None
    if type(duration) is not int or duration < 0:
        return None
    result: dict[str, bool | int | str] = {'has_owner_speech': owner, 'duration_seconds': duration}
    if shows_preview(row):
        if not isinstance(preview, str) or len(preview) > 161:
            return None
        result['preview_prefix'] = preview
    return result
