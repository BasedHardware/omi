"""Prove a speaker window on its timing store alone when the other store overlaps it.

Most pendant recordings hold two stored copies on independent clocks: ``.batch.enc``
from the live pusher and ``.opus.enc`` from sync upload. ``locate`` refuses a window
where any two spans overlap, yet a ``sync:`` segment was timed on the uploaded file,
so its own store can still prove it. A ``final:batch:`` unit can come from either
producer; only its admission-stamped ``provider_speaker.timing_store`` selects
the clock. Historical units without that stamp keep their refusal.

Only the per-window cohort reaches this. Everything else keeps today's refusal.
"""

import logging
import time
from typing import Any, Dict, Mapping, Sequence

from config.refactor_modes import default_on
from config.batch_conversation_speakers import BATCH_CONVERSATION_SCOPE
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
SPEAKER_BATCH_STORE_ENV = 'SPEAKER_BATCH_STORE_ENABLED'
SYNC_STORE = 'sync'
BATCH_STORE = 'batch'


def in_sync_store(chunk: Mapping[str, Any]) -> bool:
    return str(chunk.get('path') or '').endswith(('.opus', '.opus.enc'))


def in_batch_store(chunk: Mapping[str, Any]) -> bool:
    return bool(chunk.get('is_batch')) or str(chunk.get('path') or '').endswith(('.batch.enc', '.batch.bin'))


def in_store(chunk: Mapping[str, Any], store: str) -> bool:
    return (store == SYNC_STORE and in_sync_store(chunk)) or (store == BATCH_STORE and in_batch_store(chunk))


def sync_store_coverage(chunks: Sequence[Mapping[str, Any]], *, max_spans: int) -> PreparedAudioCoverage:
    return _store_coverage(chunks, SYNC_STORE, max_spans=max_spans)


def _store_coverage(chunks: Sequence[Mapping[str, Any]], store: str, *, max_spans: int) -> PreparedAudioCoverage:
    """Index one store's spans; one spanless or malformed object invalidates it."""
    timestamps, spans = [], []
    for chunk in chunks:
        if not in_store(chunk, store):
            continue
        bounds = chunk_actual_bounds(chunk) if isinstance(chunk.get('span'), Mapping) else None
        if bounds is None or bounds[1] is None:
            return PreparedAudioCoverage(validated=False)
        timestamps.append(bounds[0])
        spans.append({'start': bounds[0], 'end': bounds[1]})
    if not spans:
        return PreparedAudioCoverage(validated=False)
    return prepare_audio_coverage([{'chunk_timestamps': timestamps, 'chunk_spans': spans}], max_spans=max_spans)


def single_store_placements(
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
    """Windows refused for overlapping stores that their timing store alone proves."""
    if not index.validated or not index.ambiguity:
        return {}
    enabled = {SYNC_STORE: default_on(SPEAKER_SYNC_STORE_ENV), BATCH_STORE: default_on(SPEAKER_BATCH_STORE_ENV)}
    candidates = {}
    for segment in segments:
        placement = placements.get(segment.id) if segment.id is not None else None
        scope = segment.speaker_id_scope or ''
        if not scope or scope.startswith(BATCH_CONVERSATION_SCOPE):
            scope = (getattr(segment, 'provider_speaker', None) or {}).get('scope') or ''
        if scope.startswith('sync:') and scope != 'sync:':
            store = SYNC_STORE
            store_enabled = enabled[SYNC_STORE]
        elif (
            scope.startswith('final:batch:')
            and scope != 'final:batch:'
            and not scope.startswith(BATCH_CONVERSATION_SCOPE)
        ):
            store = (getattr(segment, 'provider_speaker', None) or {}).get('timing_store')
            if store not in (SYNC_STORE, BATCH_STORE):
                continue
            store_enabled = enabled[BATCH_STORE]
        else:
            continue
        if (
            placement is None
            or placement.reason != 'untrusted_clock'
            or not store_enabled
            or segment.end <= segment.start
        ):
            continue
        window = (started_at + segment.start, started_at + segment.end)
        if index.ambiguous(*window):
            candidates[segment.id] = (window, store)
    if not candidates or not per_window_evidence(uid, segments) or time.monotonic() >= deadline:
        return {}
    session = AudioChunkReadSession(uid, conversation_id)
    session.deadline = min(session.deadline, deadline)
    chunks = session.chunks
    if session.limit_hit:
        return {}
    coverage = {
        store: _store_coverage(chunks, store, max_spans=max_spans) for store in {s for _, s in candidates.values()}
    }
    proven = {
        segment_id: AudioPlacement(window, store, store=store)
        for segment_id, (window, store) in candidates.items()
        if coverage[store].validated and not coverage[store].ambiguous(*window) and coverage[store].covers(*window)
    }
    logger.info(
        'event=conversation_speaker_store candidates=%d proven=%d batch_proven=%d sync_proven=%d',
        len(candidates),
        len(proven),
        sum(p.store == BATCH_STORE for p in proven.values()),
        sum(p.store == SYNC_STORE for p in proven.values()),
    )
    return proven
