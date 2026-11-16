"""End-of-recording proof for uploaded audio. Pure policy and content-free metrics.

Owns: the shape of the phone's end marker, the rule that turns a marker into
proof that a recording's speech has fully landed, and the upload trace header.
The marker lets full processing start without the arrival-quiet wait; it never
changes custody, and a marker that proves nothing leaves the quiet rule as is.

Lifecycle: ops kill switch ``SYNC_UPLOAD_WATERMARK_ENABLED``, default on; owner
lifecycle-owner (SCA-1766); review 2026-12-14.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from datetime import datetime
from functools import cache
from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram

from utils.observability.reasons import (
    CaptureEndOutcome,
    CaptureEndProofOutcome,
    CaptureEndTypeReason,
    ReasonFamily,
    UploadTraceGateReason,
    reason_label,
)

FIELD = 'capture_end'
# The phone's VAD and the server's transcript place the last speech a few
# seconds apart; the same bound separates a resumed recording from this end.
TOLERANCE_SECONDS = 5.0
# ``utils.sync.processing_hold.FIELD``; pinned by a test so this module stays import-light.
HOLD_FIELD = 'sync_processing_hold'
CLOCK_END_MATCH_SECONDS = 1.0
MAX_CLOCK_SPAN_SECONDS = 7 * 86400
CLIENT_END_TYPES = {'user_initiated': 'user_initiated', 'silence_backstop': 'silence_backstop', 'disconnect': 'unknown'}
TRACE_GATES = frozenset(
    'none rate_limited auto_upload_off background retries_exhausted in_flight offline server_hold other'.split()
)


def enabled() -> bool:
    return os.getenv('SYNC_UPLOAD_WATERMARK_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def silence_seconds() -> int | None:
    """Phone-side silence timer, or ``None`` to tell phones not to send silence ends.

    ``SYNC_CAPTURE_END_SILENCE_SECONDS``: default 120, clamped to 60..1800;
    ``0``, a malformed value or the kill switch withdraws it.
    """
    if not enabled():
        return None
    try:
        value = int(os.getenv('SYNC_CAPTURE_END_SILENCE_SECONDS', '120'))
    except (TypeError, ValueError):
        return None
    return None if value <= 0 else max(60, min(1800, value))


def _collector(kind: Any, name: str, doc: str, labels: list[str], **kwargs: Any) -> Any:
    try:
        return kind(name, doc, labels, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


@cache
def _received() -> Counter:
    return _collector(
        Counter, 'omi_sync_capture_end_total', 'Phone end markers by end type and outcome', ['end_type', 'outcome']
    )


@cache
def _proof() -> Counter:
    return _collector(
        Counter, 'omi_sync_capture_end_proof_total', 'End-proof evaluations at hold admission', ['result']
    )


@cache
def _seal_to_accept() -> Histogram:
    return _collector(
        Histogram,
        'omi_sync_seal_to_accept_seconds',
        'Seconds from a phone file being sealed to the server accepting it, by the gate that held it',
        ['gate'],
        buckets=(5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200, 14400, 43200, 86400),
    )


def record_received(end_type: str, outcome: str) -> None:
    _received().labels(
        end_type=reason_label(ReasonFamily.CAPTURE_END, end_type, CaptureEndTypeReason),
        outcome=reason_label(ReasonFamily.CAPTURE_END, outcome, CaptureEndOutcome),
    ).inc()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def normalize(
    *,
    end_type: str,
    last_speech_at: float | None,
    end_decided_at: float,
    sent_at: float,
    pending_wals: int,
    received_at: float,
) -> dict[str, Any]:
    """The stored marker, or ``ValueError`` for a marker no honest phone sends.

    ``last_speech_at`` and ``end_decided_at`` stay on the device clock. Recorded
    time on the conversation is on that clock too unless the upload was shifted
    onto the server clock, and ``proof`` undoes that recorded shift, so the
    comparison is always phone clock against phone clock. ``last_speech_at`` is ``None`` when the phone detected no speech;
    it is stored as ``None`` and such a marker can type the end but never prove
    it. ``end_at`` is the end instant mapped to server time through the
    send/receive offset, clamped so a fast phone clock cannot place the end in
    the future. ``end_observed_at`` is when the server learned of it.
    """
    kind = CLIENT_END_TYPES.get(end_type)
    decided, sent = _number(end_decided_at), _number(sent_at)
    speech = None if last_speech_at is None else _number(last_speech_at)
    if kind is None or decided is None or sent is None or (last_speech_at is not None and speech is None):
        raise ValueError('invalid capture end')
    if type(pending_wals) is not int or pending_wals < 0:
        raise ValueError('invalid capture end')
    if (speech is not None and speech > decided + TOLERANCE_SECONDS) or decided > sent + TOLERANCE_SECONDS:
        raise ValueError('capture end clocks are out of order')
    if sent - (speech if speech is not None else decided) > MAX_CLOCK_SPAN_SECONDS:
        raise ValueError('capture end is too old')
    return {
        'end_type': kind,
        'last_speech_at': speech,
        'end_decided_at': decided,
        'end_at': min(received_at, decided + (received_at - sent)),
        'end_observed_at': received_at,
        'pending_wals': min(pending_wals, 10_000),
    }


def _seconds(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def proof(row: Mapping[str, Any], marker: Mapping[str, Any] | None) -> str:
    """Whether ``marker`` proves every spoken second of the recording is on ``row``.

    ``proven`` needs all three: the phone has no file left to upload; the
    content assigned to the row reaches the phone's last speech; and nothing on
    the row is later than the end, which would mean the recording resumed and
    this marker describes an earlier stop. A marker with no speech time
    (``no_speech_clock``) cannot show the content has landed, since an accepted
    upload is not yet a transcript, so it never proves anything.
    """
    if not marker or marker.get('end_type') not in {'user_initiated', 'silence_backstop', 'unknown'}:
        return 'absent'
    if int(marker.get('pending_wals') or 0) > 0:
        return 'pending'
    speech, decided = _number(marker.get('last_speech_at')), _number(marker.get('end_decided_at'))
    if speech is None:
        return 'no_speech_clock'
    finished = _seconds(row.get('finished_at'))
    if not finished or decided is None:
        return 'absent'
    # The marker is on the phone clock. Uploaded audio from a phone running
    # ahead is stored shifted onto the server clock, and the hold state keeps
    # that shift beside the end it applies to. Undo it so both sides are on
    # the phone clock; if the row's end has since moved for another reason the
    # shift no longer describes it and nothing can be proven.
    state = row.get(HOLD_FIELD) or {}
    shift = _number(state.get('content_clock_offset')) if isinstance(state, Mapping) else None
    if shift is not None:
        if abs(finished - _seconds(state.get('content_clock_end'))) > CLOCK_END_MATCH_SECONDS:
            return 'clock_unknown'
        finished += shift
    if finished < speech - TOLERANCE_SECONDS:
        return 'content_behind'
    if finished > decided + TOLERANCE_SECONDS:
        return 'resumed'
    return 'proven'


def record_proof(result: str) -> None:
    _proof().labels(result=reason_label(ReasonFamily.CAPTURE_END, result, CaptureEndProofOutcome)).inc()


def parse_trace(header: str | None, *, received_at: float) -> tuple[str, float] | None:
    """``sealed=<epoch>;first=<epoch>;gate=<label>;attempts=<n>`` to ``(gate, seconds)``.

    Measurement only. Anything malformed is dropped, never an upload error.
    """
    if not header or len(header) > 200:
        return None
    fields: dict[str, str] = {}
    for part in header.split(';'):
        key, _, value = part.partition('=')
        fields[key.strip()] = value.strip()
    try:
        sealed = float(fields['sealed'])
    except (KeyError, ValueError):
        return None
    if not math.isfinite(sealed) or sealed <= 0:
        return None
    gate = fields.get('gate', 'other')
    return (gate if gate in TRACE_GATES else 'other'), max(0.0, received_at - sealed)


def observe_trace(header: str | None, *, received_at: float) -> None:
    if not enabled():
        return
    parsed = parse_trace(header, received_at=received_at)
    if parsed is not None:
        _seal_to_accept().labels(gate=reason_label(ReasonFamily.CAPTURE_END, parsed[0], UploadTraceGateReason)).observe(
            parsed[1]
        )
