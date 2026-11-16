"""Listen websocket close outcomes: who closed the socket, with which code, while cap-held or not.

A client-reported 1006 means no close frame reached the client. This counter is the server-side
half: the first close the server observed (a client disconnect frame read by receive, or a server
close that returned) and the code it carried, recorded once per session at teardown. A sender's
WebSocketDisconnect is not an observation: Starlette maps every send-side OSError to 1006.

Labels are closed vocabularies only; never uid, session or conversation identifiers. Raw close
codes fold into ``CODE_CLASSES``, so application codes (4xxx, 1008, 1003) count as ``other``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from prometheus_client import REGISTRY, Counter, Histogram

from utils.observability.reasons import ListenNoAudioCloseReason

logger = logging.getLogger(__name__)

CODE_CLASSES = ('1000', '1001', '1006', '1011', 'other')
INITIATORS = ('client', 'server', 'unknown')
HELD = ('true', 'false')

# Teardown's bounded read for a disconnect frame no receive loop consumed.
CLOSE_FRAME_DRAIN_SECONDS = 0.25

LISTEN_WS_CLOSE_TOTAL = Counter(
    'omi_listen_ws_close_total',
    'Listen websocket sessions by first observed close code class, initiator and cap-held state at close',
    ['code_class', 'initiator', 'held'],
)
LISTEN_WS_CLOSE_FINALIZE_SECONDS = Histogram(
    'omi_listen_ws_close_finalize_seconds',
    'Seconds from the first observed listen websocket close to the end of session teardown',
    ['initiator', 'held'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)

# Named differently from omi_listen_no_audio_teardown_total on purpose: that family keeps its own
# labels (transcription_source), and one metric name cannot carry two label sets. Its client_platform
# values mirror utils.observability.transcription._PLATFORMS; a test pins the two sets together.
# Reuse the registered collector when a test reloads this module.
OMI_LISTEN_NO_AUDIO_CLOSE_REASON_TOTAL: Counter = getattr(REGISTRY, '_names_to_collectors', {}).get(
    'omi_listen_no_audio_close_reason_total'
) or Counter(
    'omi_listen_no_audio_close_reason_total',
    'Accepted /v4/listen sessions that tore down before any first audio byte, by the close the server observed',
    ['client_platform', 'close_reason'],
)

# Zero-initialise every series so ramp gates read 0, not absent, before the first close.
for _initiator in INITIATORS:
    for _held in HELD:
        LISTEN_WS_CLOSE_FINALIZE_SECONDS.labels(initiator=_initiator, held=_held)
        for _code_class in CODE_CLASSES:
            LISTEN_WS_CLOSE_TOTAL.labels(code_class=_code_class, initiator=_initiator, held=_held)
for _platform in ('android', 'desktop', 'ios', 'linux', 'macos', 'mobile', 'unknown', 'web', 'windows'):
    for _close_reason in ListenNoAudioCloseReason:
        OMI_LISTEN_NO_AUDIO_CLOSE_REASON_TOTAL.labels(client_platform=_platform, close_reason=_close_reason.value)


def no_audio_close_reason(state: Any) -> ListenNoAudioCloseReason:
    """Bucket the first close the server observed for a session that never sent audio. Never raises.

    A client frame with 1000/1001 is a normal close; any other client code (1005, 1006, 1011, app
    codes) is abnormal. A server-initiated close is one the server issued. With no observed frame
    and no server close, the bucket is no_close_frame. ``never_accepted`` is not decided here: the
    teardown seam only runs for sessions that reached the runtime.
    """
    try:
        initiator = getattr(state, 'ws_close_initiator', None)
        code = getattr(state, 'ws_close_code', None)
        if initiator == 'client':
            normal = not isinstance(code, bool) and code in (1000, 1001)
            return (
                ListenNoAudioCloseReason.CLIENT_CLOSE_NORMAL
                if normal
                else ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL
            )
        if initiator == 'server':
            return ListenNoAudioCloseReason.SERVER_CLOSE
        if initiator is None:
            return ListenNoAudioCloseReason.NO_CLOSE_FRAME
        return ListenNoAudioCloseReason.UNKNOWN
    except Exception:
        return ListenNoAudioCloseReason.UNKNOWN


def close_code_class(code: Any) -> str:
    if isinstance(code, bool) or not isinstance(code, int):
        return 'other'
    label = str(code)
    return label if label in CODE_CLASSES else 'other'


def note_ws_close(state: Any, initiator: str, code: Any) -> None:
    """Remember the first close the server observed; later observations of the same end are echoes."""
    if getattr(state, 'ws_close_initiator', None) is not None:
        return
    try:
        state.ws_close_initiator = initiator if initiator in INITIATORS else 'unknown'
        state.ws_close_code = code
        state.ws_close_observed_at = time.monotonic()
    except Exception as error:
        logger.warning('Listen websocket close note failed type=%s', type(error).__name__)


def record_listen_ws_close(state: Any, *, held: bool, teardown_started_at: float) -> None:
    """Count one ended session. Never raises: telemetry must not fail teardown."""
    try:
        initiator = getattr(state, 'ws_close_initiator', None)
        code = getattr(state, 'ws_close_code', None)
        if initiator is None:
            # No frame was read and no server close returned: report the intended code, unattributed.
            initiator, code = 'unknown', getattr(state, 'close_code', None)
        held_label = 'true' if held else 'false'
        LISTEN_WS_CLOSE_TOTAL.labels(code_class=close_code_class(code), initiator=initiator, held=held_label).inc()
        observed_at: Optional[float] = getattr(state, 'ws_close_observed_at', None)
        started = observed_at if isinstance(observed_at, float) else teardown_started_at
        LISTEN_WS_CLOSE_FINALIZE_SECONDS.labels(initiator=initiator, held=held_label).observe(
            max(0.0, time.monotonic() - started)
        )
    except Exception as error:
        logger.warning('Listen websocket close metric failed type=%s', type(error).__name__)
