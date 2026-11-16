"""Prompt-only canonical copies of independently matched batch/sync speech.

Stored text, IDs and annotations stay authoritative. This bounded projection
prefers placed batch speech and preserves uncertain repeats, novel wording and
manual/translated lines. Provider scopes are required; repetition within one
scope is never removed. It performs no IO and never authorizes audio reclaim.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
import math
from typing import Any, Sequence

from config.sync_live_dedupe import sync_live_dedupe_enabled
from utils.sync.donor_dedupe import dedupe_donor

_MAX_SEGMENTS = 4096
_MAX_LOCAL_REFERENCES = 128
_CLOCK_WINDOW_SECONDS = 45
_ORIGIN = datetime.fromtimestamp(0, timezone.utc)


def _scope(row: dict) -> str:
    scope = row.get('speaker_id_scope') or ''
    return '' if scope.startswith('final:batch:conversation:') else scope


def _same_possible_voice(left: dict, right: dict) -> bool:
    a, b = left.get('person_id'), right.get('person_id')
    if a and b and a != b:
        return False
    return not (left.get('is_user') is True and b or right.get('is_user') is True and a)


def _exact_copy(row: dict, candidates: list[dict]) -> bool:
    words = (row.get('text') or '').casefold().split()
    # Short acknowledgments and clock-shifted repeated phrases abstain. A
    # cross-scope copy with identical text and centisecond-equivalent endpoints
    # is safe to omit from this prompt, even below the long lexical threshold.
    return len(set(words)) >= 3 and any(
        words == (other.get('text') or '').casefold().split()
        and abs(row['start'] - other['start']) <= 0.01
        and abs(row['end'] - other['end']) <= 0.01
        for other in candidates
    )


def _bounds(row: Mapping[str, Any]) -> tuple[float, float] | None:
    start, end = row.get('start'), row.get('end')
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        return None
    if not isinstance(end, (int, float)) or isinstance(end, bool):
        return None
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        return None
    return float(start), float(end)


def canonical_prompt_segments(segments: Sequence[Any]) -> list[Any]:
    """Select existing segment objects; callers retain the complete stored source."""
    if not sync_live_dedupe_enabled() or len(segments) > _MAX_SEGMENTS:
        return list(segments)
    fields = (
        'start',
        'end',
        'text',
        'speaker_id_scope',
        'speaker_label_source',
        'audio_alignment',
        'translations',
        'person_id',
        'is_user',
    )
    rows: list[dict[str, Any]] = [
        {key: segment.get(key) if isinstance(segment, Mapping) else getattr(segment, key, None) for key in fields}
        for segment in segments
    ]
    if not any(_scope(row).startswith('final:batch:') for row in rows):
        return list(segments)
    if len({_scope(row) for row in rows if _scope(row)}) < 2:
        return list(segments)

    def preference(index):
        row = rows[index]
        return (
            row.get('speaker_label_source') not in {'manual', 'carried'},
            row.get('audio_alignment') == 'unplaced',
            not _scope(row).startswith('final:batch:'),
            -len(row.get('text') or ''),
            _scope(row),
            index,
        )

    retained: set[int] = set()
    reference: list[dict[str, Any]] = []
    for index in sorted(range(len(rows)), key=preference):
        row = rows[index]
        scope = _scope(row)
        bounds = _bounds(row)
        if bounds is None:
            retained.add(index)
            continue
        start, end = bounds
        protected = row.get('speaker_label_source') in {'manual', 'carried'} or row.get('translations')
        candidates = []
        if scope and not protected:
            midpoint = (start + end) / 2
            candidates = [
                other
                for other in reference
                if _scope(other) != scope
                and abs((other['start'] + other['end']) / 2 - midpoint) <= _CLOCK_WINDOW_SECONDS
                and _same_possible_voice(row, other)
            ]
        if 0 < len(candidates) <= _MAX_LOCAL_REFERENCES:
            if _exact_copy(row, candidates):
                continue
            incoming = [dict(row, timestamp=start)]
            kept = dedupe_donor(incoming, {}, {'started_at': _ORIGIN, 'transcript_segments': candidates}).kept
            if not kept:
                continue
        retained.add(index)
        if scope.startswith('final:batch:'):
            reference.append(row)
    return [segment for index, segment in enumerate(segments) if index in retained]
