"""Terminal handling for live transcription provider failures."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from models.message_event import MessageServiceStatusEvent
from utils.observability.transcription import record_live_stt_failure
from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome, failure_from_exception

logger = logging.getLogger(__name__)

LIVE_STT_FAILURE_CLOSE_CODE = 1011
LIVE_STT_FAILURE_CLOSE_REASON = 'transcription_service_unavailable'

_KNOWN_FAILURE_REASONS = frozenset(
    {
        'initialization_failed',
        'connection_lost',
        'send_failed',
        'socket_unavailable',
    }
)
_FAILURE_PHASE_BY_REASON = {
    'initialization_failed': 'initialization',
    'connection_lost': 'connection',
    'socket_unavailable': 'connection',
    'send_failed': 'send',
}


class LiveSTTSession(Protocol):
    active: bool
    close_code: int
    stt_terminal_failure: bool


class LiveSTTClientSocket(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


def live_stt_upstream_failure(provider: str | None) -> TranscriptionFailure:
    """Build the shared bounded failure used after a live socket becomes unusable."""

    return TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider, retryable=True)


def live_stt_initialization_failure(error: BaseException, provider: str | None) -> TranscriptionFailure:
    """Classify live provider startup failures using the shared outcome vocabulary."""

    failure = failure_from_exception(error, provider=provider)
    # Socket construction happens after client audio settings are validated. A
    # ValueError/TypeError at this boundary is therefore a provider deployment
    # configuration failure, not invalid user input.
    if failure.outcome == TranscriptionOutcome.INVALID_INPUT:
        return TranscriptionFailure(
            TranscriptionOutcome.CONFIG_ERROR,
            provider=provider,
            retryable=False,
        )
    return failure


def _bounded_reason(reason: str) -> str:
    return reason if reason in _KNOWN_FAILURE_REASONS else 'connection_lost'


def live_stt_socket_is_dead(stt_socket: Any) -> bool:
    """Treat a broken or unreadable provider death latch as terminal."""

    try:
        return bool(stt_socket.is_connection_dead)
    except Exception:
        return True


async def terminate_live_stt_session(
    websocket: LiveSTTClientSocket,
    session: LiveSTTSession,
    *,
    failure: TranscriptionFailure,
    reason: str,
    platform: str | None,
) -> bool:
    """Send the terminal status before closing the client socket.

    The transition is idempotent because single- and multi-channel send paths can
    observe the same provider death during teardown. The close reason and event
    fields are deliberately bounded and never include provider exception text.
    """

    if session.stt_terminal_failure:
        return False

    session.stt_terminal_failure = True
    session.close_code = LIVE_STT_FAILURE_CLOSE_CODE
    bounded_reason = _bounded_reason(reason)
    try:
        record_live_stt_failure(
            provider=failure.provider,
            platform=platform,
            outcome=failure.outcome,
            phase=_FAILURE_PHASE_BY_REASON[bounded_reason],
        )
    except Exception as error:
        logger.warning(
            'Unable to record terminal live STT failure error_type=%s',
            type(error).__name__,
        )
    event = MessageServiceStatusEvent(
        status='stt_failed',
        status_text=failure.public_message,
        outcome=failure.outcome.value,
        provider=failure.provider,
        retryable=failure.retryable,
        reason=bounded_reason,
    )

    event_sent = False
    try:
        await websocket.send_json(event.to_json())
        event_sent = True
    except Exception as error:
        logger.warning(
            'Unable to deliver terminal live STT status error_type=%s',
            type(error).__name__,
        )
    finally:
        session.active = False

    try:
        await websocket.close(
            code=LIVE_STT_FAILURE_CLOSE_CODE,
            reason=LIVE_STT_FAILURE_CLOSE_REASON,
        )
    except Exception as error:
        logger.info(
            'Unable to close client after terminal live STT failure error_type=%s',
            type(error).__name__,
        )

    return event_sent


async def send_live_stt_audio(
    websocket: LiveSTTClientSocket,
    session: LiveSTTSession,
    *,
    stt_socket: Any,
    audio: bytes,
    provider: str | None,
    platform: str | None,
) -> bool:
    """Send one audio chunk, terminating the client if the provider is unusable."""

    if stt_socket is None:
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason='socket_unavailable',
            platform=platform,
        )
        return False

    if live_stt_socket_is_dead(stt_socket):
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason='connection_lost',
            platform=platform,
        )
        return False

    try:
        accepted = stt_socket.send(audio)
    except Exception:
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason='send_failed',
            platform=platform,
        )
        return False

    if accepted is not True:
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason='send_failed',
            platform=platform,
        )
        return False

    # Safe socket wrappers report send failures through the death latch instead
    # of raising so every provider must be checked after the send as well.
    if live_stt_socket_is_dead(stt_socket):
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason='send_failed',
            platform=platform,
        )
        return False

    return True


async def flush_live_stt_buffer(
    websocket: LiveSTTClientSocket,
    session: LiveSTTSession,
    *,
    stt_socket: Any,
    buffer: bytearray,
    provider: str | None,
    platform: str | None,
) -> bool:
    """Send and clear a buffer only after the provider accepted its contents."""

    sent = await send_live_stt_audio(
        websocket,
        session,
        stt_socket=stt_socket,
        audio=bytes(buffer),
        provider=provider,
        platform=platform,
    )
    if sent:
        buffer.clear()
    return sent
