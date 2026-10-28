"""Post-ingest boundary for one sync segment: enroll, store audio, finish.

process_segment hands the real store/finish callbacks in from its module
globals so existing monkeypatches keep working; this helper only decides
whether the intake wrote anything. A transient repeat-only intake is
acknowledged without new enrollment, audio storage or enrichment — except
when it provably completes previously admitted sync work (a sync-scoped
exact retry), where existing debt still enrolls and finishes. Transient
markers never escape into persistence or receipts.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from utils.capture_evidence import (
    bounded_envelope,
    merge_track_receipts,
    sync_segment_receipt,
    unknown_envelope,
)
from utils.metrics import OMI_CAPTURE_EVIDENCE_ENVELOPES_TOTAL
from utils.observability.fallback import record_fallback
from utils.stt.outcomes import TranscriptionOutcome
from utils.sync.assignment_telemetry import CREATED_UNKNOWN_REASONS
from utils.sync.bridge_observation import log_bridge_observation

logger = logging.getLogger(__name__)


def log_sync_lineage_created(observation: dict) -> None:
    """One id-free gate-3 observation after a successful assignment commit."""
    try:
        suffix = ''
        if observation['outcome'] == 'created_unknown':
            reason = observation.get('incomplete_reason')
            if reason not in CREATED_UNKNOWN_REASONS:
                reason = 'not_recorded'
            suffix = f' incomplete_reason={reason}'
        logger.info(
            'event=sync_lineage_resolve outcome=%s stage=assignment '
            'checked_live_candidates_bucket=%s lookup_complete=%s%s',
            observation['outcome'],
            observation['checked_live_candidates_bucket'],
            str(observation['lookup_complete']).lower(),
            suffix,
        )
    except Exception:
        pass


def log_assignment_observations(conversation: dict, *, lineage_eligible: bool) -> None:
    """Consume only the successful assignment result, before external effects."""
    bridge = conversation.pop('_sync_lineage_bridge', None)
    if bridge is not None:
        log_bridge_observation(bridge)
    created = conversation.pop('_sync_lineage_created', None)
    if lineage_eligible and created is not None:
        log_sync_lineage_created(created)


def acknowledge_processed_segment(
    deferred_outcome: Optional[dict],
    *,
    provider: str,
    model: str,
    lane: str,
    job_id: Optional[str],
    segment_key: Optional[str],
    attempt_ref: Optional[str],
    set_outcome: Callable,
    record_outcome: Callable,
) -> None:
    """Commit the success outcome to the deferred checkpoint or job ledger."""
    set_outcome(
        deferred_outcome,
        outcome=TranscriptionOutcome.SUCCESS,
        provider=provider,
        model=model,
        retryable=False,
    )
    if deferred_outcome is None:
        record_outcome(
            TranscriptionOutcome.SUCCESS,
            provider=provider,
            model=model,
            lane=lane,
            retryable=False,
            job_id=job_id,
            segment_key=segment_key,
            attempt_ref=attempt_ref,
        )


def apply_capture_evidence_dark_write(
    incoming: dict, source_position_map: Optional[tuple[dict, int]], transcript_segments: list
) -> None:
    """Populate ``incoming['capture_evidence']`` from the pre-ingest receipts."""
    receipt = unknown_envelope('missing_source_position', origin='sync_vad')
    if source_position_map is not None:
        frame_map, derivative_start = source_position_map
        rate = frame_map['claim']['rate_hz']
        mapped = [
            sync_segment_receipt(
                frame_map,
                wav_sample_start=derivative_start + round(segment.start * rate),
                wav_sample_end=derivative_start + round(segment.end * rate),
                segment_id=str(segment.id),
            )
            for segment in transcript_segments
        ]
        if all(item is not None for item in mapped):
            receipt = merge_track_receipts([], mapped)
            if frame_map['incomplete'] and receipt.get('capability') == 'source_position':
                receipt['coverage'] = 'incomplete'
            receipt = bounded_envelope(receipt)
    incoming['capture_evidence'] = receipt


def record_capture_evidence_metric(incoming: dict) -> None:
    """Emit the post-ingest envelope metric for a dark-written capture receipt."""
    OMI_CAPTURE_EVIDENCE_ENVELOPES_TOTAL.labels(
        path='sync',
        status='mapped' if incoming['capture_evidence']['capability'] == 'source_position' else 'unknown',
    ).inc()


def log_sync_lineage_append(stats: dict, existing_completion: bool = False) -> None:
    """One bounded, id-free telemetry line per dedupe-evaluated intake."""
    try:
        logger.info(
            'event=sync_lineage_append appended_seconds=%.2f dropped_as_repeat_seconds=%.2f '
            'alignment_method=%s repeat_only=%s existing_completion=%s span_delta_bucket=%s '
            'appended_seconds_overlapping_live=%s',
            stats['appended_seconds'],
            stats['dropped_as_repeat_seconds'],
            stats['alignment_method'],
            stats['repeat_only'],
            existing_completion,
            stats.get('span_delta_bucket', 'none'),
            (
                f"{stats['appended_seconds_overlapping_live']:.1f}"
                if stats.get('appended_seconds_overlapping_live') is not None
                else 'unknown'
            ),
        )
    except Exception:
        pass


def log_sync_lineage_stamp_append(span_delta_bucket: str) -> None:
    """Dedupe-off lineage observability: one bounded token, no dedupe markers."""
    try:
        logger.info('event=sync_lineage_stamp_append span_delta_bucket=%s', span_delta_bucket)
    except Exception:
        pass


def log_sync_lineage_stamp_gap_refused() -> None:
    """Both legacy and batch projection report a committed stamp-gap reroute."""
    try:
        logger.info('event=sync_lineage_stamp_append outcome=stamp_gap_refused span_delta_bucket=0')
    except Exception:
        pass
    record_fallback(
        component='sync_dispatch',
        from_mode='explicit_target',
        to_mode='temporal_assignment',
        reason='policy',
        outcome='degraded',
        log=logger,
    )


def complete_sync_intake(
    *,
    uid: str,
    assigned: dict,
    created: bool,
    survivors: list,
    response: dict,
    lock: threading.Lock,
    language: Optional[str],
    audio_enabled: bool,
    store_audio: Callable[[str], None],
    finish: Callable,
    mark_finalize: Callable[[], None],
    acknowledge: Callable[[], None],
    attach_episode: Optional[Callable[[str, str, dict], str]] = None,
) -> str:
    """Enroll the intake result, store audio, run enrichment and log telemetry.

    Returns the canonical conversation id. The ``assigned`` row is consumed:
    transient ``_sync_lineage_*`` markers are popped here and never reach
    ``finish`` or the response. ``store_audio`` receives the canonical id and
    decides itself whether anything is uploaded; ``mark_finalize`` and
    ``acknowledge`` keep the caller's phase and outcome bookkeeping order.
    ``attach_episode``, when handed in, joins the landed row to the live
    episode covering it before anything downstream can fail; it never raises
    and never changes the intake result.
    """
    for row, row_created in assigned.pop('_sync_size_rollover_rows', []):
        complete_sync_intake(
            uid=uid,
            assigned=row,
            created=row_created,
            survivors=[],
            response=response,
            lock=lock,
            language=language,
            audio_enabled=audio_enabled,
            store_audio=store_audio,
            finish=finish,
            mark_finalize=mark_finalize,
            acknowledge=lambda: None,
            attach_episode=attach_episode,
        )
    repeat_only = bool(assigned.pop('_sync_lineage_repeat_only', False))
    completion_pending = bool(assigned.pop('_sync_lineage_completion_pending', False))
    stats = assigned.pop('_sync_lineage_dedupe', None)
    stamp_bucket = assigned.pop('_sync_lineage_stamp_append', None)
    stamp_gap_refused = assigned.pop('_sync_lineage_stamp_gap_refused', False)
    # An exact sync-scoped retry may owe enrichment from an earlier partial
    # run. That existing debt still enrolls and finishes even though this
    # upload wrote nothing; pristine live repeats invent no new debt.
    # Merged ancestry alone is not evidence of pending completion.
    existing_completion = completion_pending
    conversation_id = assigned['id']
    with lock:
        if not repeat_only:
            response['new_memories' if created else 'updated_memories'].add(conversation_id)
            if assigned['sync_relevance'] == 'keep':
                response.setdefault('_merged', {})[conversation_id] = language
        elif existing_completion:
            response.setdefault('_merged', {})[conversation_id] = language
    if stats is not None:
        log_sync_lineage_append(stats, existing_completion=existing_completion and repeat_only)
    if stamp_bucket is not None:
        log_sync_lineage_stamp_append(stamp_bucket)
    if stamp_gap_refused:
        log_sync_lineage_stamp_gap_refused()
    if attach_episode is not None and (not repeat_only or existing_completion):
        # The row is visible in Home from this moment; fold it under the live
        # episode before audio storage or enrichment can stall behind it.
        attach_episode(uid, conversation_id, assigned)
    store_audio(conversation_id)
    mark_finalize()
    if not repeat_only or existing_completion:
        finish(
            uid,
            assigned,
            response,
            lock,
            language,
            audio_source_id=(None if repeat_only else (conversation_id if audio_enabled else None)),
        )
    acknowledge()
    return conversation_id
