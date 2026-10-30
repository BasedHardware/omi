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

from prometheus_client import Counter, Histogram

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

# Zero-initialise every series so ramp gates read 0, not absent, before the first close.
for _initiator in INITIATORS:
    for _held in HELD:
        LISTEN_WS_CLOSE_FINALIZE_SECONDS.labels(initiator=_initiator, held=_held)
        for _code_class in CODE_CLASSES:
            LISTEN_WS_CLOSE_TOTAL.labels(code_class=_code_class, initiator=_initiator, held=_held)


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
