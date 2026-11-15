"""Positive STT-empty receipts, fenced to the closed audio and pending generation."""

import math
from collections.abc import Mapping
from datetime import datetime

from config.episode_composition import legacy_empty_wire_enabled, settled_terminal_enabled

FIELD = 'record_transcription_empty'
EMPTY_OUTCOMES = frozenset({'silence', 'no_recoverable_speech'})


def pending_generation(row):
    return [row.get('home_transcription_pending_at'), row.get('episode_transcription_pending_at')]


def stamp(current, result, span):
    """Only the validated empty-result assignment supplies terminal_empty_outcome.

    Persist with the existing transcript/receipt transaction; no extra reads,
    job transitions, audio changes or provider calls. Old projectors increment
    the revision without refreshing this receipt, which safely invalidates it.
    """
    if not (settled_terminal_enabled() or legacy_empty_wire_enabled()):
        return
    if span.get('terminal_empty_outcome') not in EMPTY_OUTCOMES:
        return
    previous = current.get(FIELD) or {}
    generation = pending_generation(current)
    spans = (
        [list(span) for span in previous.get('spans') or []]
        if previous.get('pending_generation') == generation
        and previous.get('projection_revision') == current.get('record_projection_revision')
        else []
    )
    spans.append([span['start'], span['end']])
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    result[FIELD] = {
        'version': 1,
        'projection_revision': result['record_projection_revision'],
        'pending_generation': generation,
        'spans': merged,
    }


def terminal(row):
    """A partial empty unit, summary failure or old revision never settles STT."""
    receipt = row.get(FIELD)
    if (
        not isinstance(receipt, Mapping)
        or receipt.get('version') != 1
        or not row.get('record_projection_revision')
        or receipt.get('projection_revision') != row.get('record_projection_revision')
        or receipt.get('pending_generation') != pending_generation(row)
        or row.get('record_upload_sessions')
        or row.get('record_audio_partial')
    ):
        return False
    if row.get('server_batch_audio_closed') is True:
        start, end = row.get('server_batch_audio_start'), row.get('server_batch_audio_end')
    elif row.get('record_audio_closed') is True:
        start, end = row.get('started_at'), row.get('finished_at')
        start = start.timestamp() if isinstance(start, datetime) else None
        end = end.timestamp() if isinstance(end, datetime) else None
    else:
        return False
    if not all(type(value) in (int, float) and math.isfinite(value) for value in (start, end)) or end <= start:
        return False
    return any(
        isinstance(span, (list, tuple))
        and len(span) == 2
        and all(type(value) in (int, float) and math.isfinite(value) for value in span)
        and span[0] <= start + 1e-6
        and span[1] >= end - 1e-6
        for span in receipt.get('spans') or []
    )
