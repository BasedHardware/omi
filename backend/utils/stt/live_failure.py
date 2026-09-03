"""Terminal handling for live transcription provider failures."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol

from models.message_event import MessageServiceStatusEvent
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.observability.transcription import record_live_stt_failure
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    bounded_provider,
    failure_from_exception,
)

logger = logging.getLogger(__name__)

LIVE_STT_FAILURE_CLOSE_CODE = 1011
LIVE_STT_FAILURE_CLOSE_REASON = 'transcription_service_unavailable'


# Chain depth is 3 (velma/soniox/deepgram); allow walking it once, not looping.
# Shared by every live surface so a mid-session failover cannot loop a chain
# forever (#12459, #12469).
MAX_STT_FAILOVERS = 2

_KNOWN_FAILURE_REASONS = frozenset(
    {
        'initialization_failed',
        'connection_lost',
        'send_failed',
        'socket_unavailable',
        # Typed in-stream provider rejections. Soniox answers typed error
        # codes (utils.stt.soniox); Modulate/Velma answers free-text frames
        # that the socket bounds to MODULATE_DEATH_SERVE_ERROR when the
        # provider failed to serve the stream it had accepted
        # (utils.stt.streaming.modulate_death_reason).
        'modulate_serve_error',
        'soniox_account_state',
        'soniox_idle_timeout',
        'soniox_rotation',
        'soniox_invalid_hint',
    }
)
_FAILURE_PHASE_BY_REASON = {
    'initialization_failed': 'initialization',
    'connection_lost': 'connection',
    'socket_unavailable': 'connection',
    'send_failed': 'send',
    # A typed in-stream rejection is the provider closing a connection it had
    # accepted. The bounded phase vocabulary has no 'serve' bucket, and 'send'
    # would claim our send failed, so 'connection' is the truthful bucket.
    'modulate_serve_error': 'connection',
    'soniox_account_state': 'connection',
    'soniox_idle_timeout': 'connection',
    'soniox_rotation': 'connection',
    # The config frame was rejected after the WebSocket upgrade succeeded:
    # the session died at session setup, before any audio flowed.
    'soniox_invalid_hint': 'initialization',
}
_CIRCUIT_OPENING_REASONS = frozenset(
    {
        # 402 organization_balance_exhausted: the provider still ACCEPTS the
        # WebSocket upgrade but refuses to serve ANY stream, so the
        # connect-time failure counter provably never accumulates under
        # reconnect load (each dying session's replacement connects fine and
        # calls record_success). Same mechanism record_serve_failure exists
        # for. The other typed shapes are session-scoped — an idle-timeout is
        # this session's VAD pattern and a 413 rotation serves fine on a fresh
        # connection — so they must not bench the provider for everyone.
        'soniox_account_state',
        # Velma's mid-session "Internal server error" / "Unable to complete
        # the request" frames: the provider accepted the stream, served audio,
        # and then failed. This is the dominant live-STT outage shape
        # (backend-listen #3/#10 signatures, 2026-08-31: ×11 and ×5 per 30m),
        # and mid-session failover rescues the session — which is exactly why
        # the death would otherwise stay invisible to selection: the surviving
        # session never runs the terminal funnel that feeds the circuit, and
        # the next session's successful connect resets the counter. One
        # serve-error death opens the circuit for one cooldown window; the
        # half-open probe restores Velma as soon as one stream serves again.
        # Session-scoped shapes (invalid input audio) stay untyped and do not
        # bench the provider.
        'modulate_serve_error',
    }
)

# Terminal reasons that are evidence about the *provider* while it was serving
# audio. ``initialization_failed`` happens at connect time, where the selection
# helper's threshold logic already sees it, and ``socket_unavailable`` is local
# state (no socket exists), not provider behavior.
_SERVE_FAILURE_REASONS = frozenset({'connection_lost', 'send_failed'})


class LiveSTTSession(Protocol):
    active: bool
    close_code: int
    stt_terminal_failure: bool
    live_transcription_attempt: Any
    client_live_transcription_attempt: Any


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


def live_stt_terminal_reason(stt_socket: Any, fallback: str) -> str:
    """Prefer a socket's typed provider rejection over the observing path's fallback.

    Every observer of a dead socket (death monitor, send path) knows only its
    own vantage point ('connection_lost', 'send_failed'); the socket knows why
    the provider actually refused to serve. Providers that answer typed
    in-stream error frames (Soniox) latch that reason at the frame; this keeps
    it bounded and lets every terminal funnel report it instead of collapsing
    a named provider rejection back to generic connection loss.
    """

    try:
        typed = getattr(stt_socket, 'typed_death_reason', None)
    except Exception:
        return fallback
    return typed if typed in _KNOWN_FAILURE_REASONS else fallback


def note_typed_provider_death(stt_socket: Any, provider: str | None) -> bool:
    """Open the selection circuit when a socket died by provider-level rejection.

    A 402 ``organization_balance_exhausted`` stream is served by NO session
    while the provider keeps accepting connects, so the mid-session failover
    path moves each dying session to the next provider and the session
    SURVIVES — which is exactly why the death would otherwise stay invisible
    to selection: the surviving session never runs the terminal path that
    feeds the circuit, and the next new session is handed right back to the
    provider that refuses to serve it. Observing the typed rejection at the
    failover seam gives selection the same one-cooldown skip it already gets
    from a serve-time death. Session-scoped reasons (idle timeout, rotation)
    are deliberately ignored here: they are evidence about one session, not
    the provider.
    """

    try:
        typed = getattr(stt_socket, 'typed_death_reason', None)
    except Exception:
        return False
    if typed not in _CIRCUIT_OPENING_REASONS:
        return False
    return _open_serving_provider_circuit(typed, provider)


def _open_serving_provider_circuit(bounded_reason: str, provider: str | None) -> bool:
    """Open the process-local selection circuit of the provider who died serving.

    Deliberately cheap and fail-open: the terminal close of the client session
    must never be delayed or failed by circuit bookkeeping. Imported lazily
    because ``utils.stt.streaming`` imports the socket implementations this
    module classifies, so a module-level import would be circular.

    Returns whether a known provider's circuit actually opened, mirroring
    ``open_provider_selection_circuit``: unknown provider tokens and internal
    failures report ``False`` so the seam never claims learning that did not
    happen.
    """
    try:
        from utils.stt.streaming import open_provider_selection_circuit

        return open_provider_selection_circuit(provider, reason=bounded_reason)
    except Exception as error:  # noqa: BLE001 — telemetry-adjacent bookkeeping must not fail the terminal path
        logger.warning(
            'Unable to open selection circuit after serve-time death provider=%s error_type=%s',
            bounded_provider(provider),
            type(error).__name__,
        )
        return False


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
    if bounded_reason in _SERVE_FAILURE_REASONS or bounded_reason in _CIRCUIT_OPENING_REASONS:
        # A provider that died while serving audio is terminal evidence for
        # this session, but selection only learns from connect-time outcomes:
        # the next reconnect's successful *connect* would call
        # ``record_success`` and reset the counter, so serve-time deaths never
        # reach the threshold. Open the serving provider's circuit here so
        # reconnecting clients skip straight to a healthy fallback for the
        # cooldown, instead of being handed back to the provider that just
        # died on them (connect -> die -> reconnect -> die under an outage).
        # A typed account-state rejection (402) is the same evidence with a
        # name: the provider accepts connects and refuses every stream.
        _open_serving_provider_circuit(bounded_reason, failure.provider)
    try:
        record_live_stt_failure(
            provider=failure.provider,
            platform=platform,
            outcome=failure.outcome,
            phase=_FAILURE_PHASE_BY_REASON[bounded_reason],
        )
        attempt = getattr(session, 'live_transcription_attempt', None)
        if attempt is not None:
            attempt.finish('failure', phase=_FAILURE_PHASE_BY_REASON[bounded_reason])
        client_attempt = getattr(session, 'client_live_transcription_attempt', None)
        if client_attempt is not None:
            client_attempt.fail('provider_error')
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
    attempt_failover: Callable[[], Awaitable[bool]] | None = None,
) -> bool:
    """Send one audio chunk, terminating the client if the provider is unusable.

    ``attempt_failover`` is the session's chance to swap a dead provider socket
    for the next one in the chain before this path declares the failure
    terminal. The send path observes a provider death on the very next audio
    chunk — hundreds of milliseconds before the 1s death-monitor poll — so
    without the gate here the monitor's failover (#12459) loses that race on
    every session with audio flowing. After a successful failover the chunk is
    reported unsent so the caller retries it against the replacement socket.
    """

    # Observed on every provider, not just Velma: whether production emits frames that
    # are not whole 16-bit samples is otherwise unmeasurable without exposing users to
    # Velma, which rejects them outright. Deepgram tolerates them silently.
    if len(audio) % 2:
        OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL.labels(provider=bounded_provider(provider), stage='buffer').inc()

    async def _recoverable_failure(reason: str) -> None:
        if attempt_failover is not None and await attempt_failover():
            return
        await terminate_live_stt_session(
            websocket,
            session,
            failure=live_stt_upstream_failure(provider),
            reason=reason,
            platform=platform,
        )

    # A None socket means initialization never produced one; there is nothing to
    # fail over from, so this stays terminal.
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
        await _recoverable_failure(live_stt_terminal_reason(stt_socket, 'connection_lost'))
        return False

    try:
        accepted = stt_socket.send(audio)
    except Exception:
        await _recoverable_failure('send_failed')
        return False

    if accepted is not True:
        await _recoverable_failure('send_failed')
        return False

    # Safe socket wrappers report send failures through the death latch instead
    # of raising so every provider must be checked after the send as well.
    if live_stt_socket_is_dead(stt_socket):
        await _recoverable_failure('send_failed')
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
    attempt_failover: Callable[[], Awaitable[bool]] | None = None,
) -> bool:
    """Send and clear a buffer only after the provider accepted its contents."""

    sent = await send_live_stt_audio(
        websocket,
        session,
        stt_socket=stt_socket,
        audio=bytes(buffer),
        provider=provider,
        platform=platform,
        attempt_failover=attempt_failover,
    )
    if sent:
        buffer.clear()
    return sent
