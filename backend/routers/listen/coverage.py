"""Post-commit adapter from S1 snapshots to L1's coverage authority.

No receipt-only envelope is sufficient. Call only after the segment transaction
returns its durable LiveTranscriptMerge; a ledger failure withholds custody ACKs.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from config.refactor_modes import shadow_or_serve, serving_for
from models.capture_coverage import CaptureCommittedEvent, CaptureKey, CoverageRecord, FrameRange
from utils.committed_capture import PROOF_KIND
from utils.capture_evidence import unknown_envelope
from utils.conversations.lifecycle_metrics import observe


def record_committed(
    uid: str,
    conversation_id: str,
    snapshot: dict[str, Any] | None,
    *,
    recording_session_id: str | None = None,
    device_id: str | None = None,
) -> list[CaptureCommittedEvent]:
    """Persist exact committed S1 runs before returning any acknowledgements."""
    if not shadow_or_serve('CAPTURE_COVERAGE_MODE'):
        return []
    if not snapshot or snapshot.get('proof') != PROOF_KIND or snapshot.get('conflicts'):
        return []
    try:
        # L1 lands independently. Lazy import is part of the cross-lane contract.
        from utils.capture.coverage import record
    except ImportError:
        observe('live_coverage', None)
        return []
    grouped: dict[tuple[str, str, str], list[FrameRange]] = defaultdict(list)
    try:
        for run in snapshot.get('runs') or []:
            start, end = run.get('source_frame_start'), run.get('source_frame_end')
            root = run.get('capture_root')
            if not root or type(start) is not int or type(end) is not int or start < 0 or end <= start:
                continue
            grouped[(str(root), str(run.get('channel', 'mono')), str(run.get('clock_epoch', 'default')))].append(
                FrameRange(start=start, end=end)
            )
    except (AttributeError, TypeError, ValueError):
        observe('live_coverage', None)
        return []
    events = []
    for (root, channel, epoch), ranges in grouped.items():
        key = CaptureKey(
            capture_root=root,
            channel=channel,
            clock_epoch=epoch,
            recording_session_id=recording_session_id,
            device_id=device_id,
        )
        try:
            record(uid, key, CoverageRecord(conversation_id=conversation_id, origin='live', ranges=ranges))
        except Exception:
            observe('live_coverage', None)
            continue
        observe('live_coverage', True)
        if not serving_for('CAPTURE_COVERAGE_MODE', uid):
            continue
        events.extend(
            CaptureCommittedEvent(
                conversation_id=conversation_id,
                capture_root=root,
                channel=channel,
                clock_epoch=epoch,
                recording_session_id=recording_session_id,
                source_start=r.start,
                source_end=r.end,
            )
            for r in ranges
        )
    return events


async def publish_committed(host: Any, conversation_id: str, snapshot: dict[str, Any] | None) -> None:
    """Queue coverage after the segment write; release it at the audio window."""
    if not snapshot or snapshot.get('proof') != PROOF_KIND or not shadow_or_serve('CAPTURE_COVERAGE_MODE'):
        return
    receiver = getattr(host, 'receiver', None)
    archive = getattr(receiver, 'raw_archive', None)
    if archive is not None and archive.durable and getattr(host, 'private_cloud_sync_enabled', False):
        try:
            await archive.defer_ack(conversation_id, lambda: _publish_committed(host, conversation_id, snapshot))
        except Exception:
            observe('live_coverage', None)
        return
    # Without cloud-audio consent, retain the pre-custody transcript receipt
    # contract: the caller's LiveTranscriptMerge is already durable. Do not
    # interpret an empty archive checkpoint as audio custody or retain WAL
    # forever waiting for an upload that consent explicitly forbids.
    await _publish_committed(host, conversation_id, snapshot)


async def _publish_committed(host: Any, conversation_id: str, snapshot: dict[str, Any]) -> None:
    try:
        events = await host.persistence.call(
            record_committed,
            host.request.uid,
            conversation_id,
            snapshot,
            recording_session_id=getattr(host, 'recording_session_id', None),
            device_id=getattr(getattr(host, 'client_device_context', None), 'client_device_id', None),
        )
        if serving_for('CAPTURE_COVERAGE_MODE', host.request.uid):
            for event in events:
                host.send_event(event)

    except Exception:
        # Transcript durability already succeeded; an optional custody publication
        # failure must never trigger rollover/re-ingestion of the same speech.
        observe('live_coverage', None)


def committed_snapshot(host: Any, conversation_id: str, segments) -> dict:
    source_map = host.state.source_position_map
    if source_map is not None:
        return source_map.committed_snapshot(conversation_id, segments) or unknown_envelope(
            'missing_source_position', origin='live'
        )
    return unknown_envelope('multichannel_mix' if host.is_multi_channel else 'missing_source_position', origin='live')
