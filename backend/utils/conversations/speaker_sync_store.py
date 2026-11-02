"""Prove a sync-timed window on the sync store alone when the live store overlaps it.

Most pendant recordings hold two stored copies on independent clocks: ``.batch.enc``
from the live pusher and ``.opus.enc`` from sync upload. ``locate`` refuses a window
where any two spans overlap, yet a ``sync:`` segment was timed on the uploaded file,
so its own store can still prove it. ``final:batch:`` stays out: desktop record units
are timed on ``.batch.enc`` and nothing on the conversation tells them apart.

Only the per-window cohort reaches this. Everything else keeps today's refusal.
"""

import logging
import time
from typing import Any, Dict, Mapping, Sequence

from config.refactor_modes import default_on
from utils.conversations.audio_inventory import chunk_actual_bounds
from utils.conversations.audio_placement import (
    AudioPlacement,
    PreparedAudioCoverage,
    prepare_audio_coverage,
)
from utils.conversations.speaker_window_cohort import per_window_evidence
from utils.other.audio_chunks import AudioChunkReadSession

logger = logging.getLogger(__name__)

SPEAKER_SYNC_STORE_ENV = 'SPEAKER_SYNC_STORE_ENABLED'
SYNC_STORE = 'sync'


def in_sync_store(chunk: Mapping[str, Any]) -> bool:
    return str(chunk.get('path') or '').endswith(('.opus', '.opus.enc'))


def sync_store_coverage(chunks: Sequence[Mapping[str, Any]], *, max_spans: int) -> PreparedAudioCoverage:
    """Index the sync store's own spans; one spanless or malformed object invalidates it."""
    timestamps, spans = [], []
    for chunk in chunks:
        if not in_sync_store(chunk):
            continue
        bounds = chunk_actual_bounds(chunk) if isinstance(chunk.get('span'), Mapping) else None
        if bounds is None or bounds[1] is None:
            return PreparedAudioCoverage(validated=False)
        timestamps.append(bounds[0])
        spans.append({'start': bounds[0], 'end': bounds[1]})
    if not spans:
        return PreparedAudioCoverage(validated=False)
    return prepare_audio_coverage([{'chunk_timestamps': timestamps, 'chunk_spans': spans}], max_spans=max_spans)


def sync_store_placements(
    uid: str,
    conversation_id: str,
    segments: Sequence[Any],
    placements: Mapping[str, AudioPlacement],
    index: PreparedAudioCoverage,
    started_at: float,
    deadline: float,
    *,
    max_spans: int,
) -> Dict[str, AudioPlacement]:
    """Windows refused only for overlapping stores that the sync store alone proves."""
    if not index.validated or not index.ambiguity or not default_on(SPEAKER_SYNC_STORE_ENV):
        return {}
    candidates = {}
    for segment in segments:
        placement = placements.get(segment.id) if segment.id is not None else None
        scope = segment.speaker_id_scope or ''
        if placement is None or placement.reason != 'untrusted_clock' or not scope.startswith('sync:'):
            continue
        if scope == 'sync:' or segment.end <= segment.start:
            continue
        window = (started_at + segment.start, started_at + segment.end)
        if index.ambiguous(*window):
            candidates[segment.id] = window
    if not candidates or not per_window_evidence(uid, segments) or time.monotonic() >= deadline:
        return {}
    session = AudioChunkReadSession(uid, conversation_id)
    session.deadline = min(session.deadline, deadline)
    chunks = session.chunks
    if session.limit_hit:
        return {}
    coverage = sync_store_coverage(chunks, max_spans=max_spans)
    proven = {
        segment_id: AudioPlacement(window, 'sync', store=SYNC_STORE)
        for segment_id, window in candidates.items()
        if coverage.validated and not coverage.ambiguous(*window) and coverage.covers(*window)
    }
    logger.info('event=conversation_speaker_sync_store candidates=%d proven=%d', len(candidates), len(proven))
    return proven
