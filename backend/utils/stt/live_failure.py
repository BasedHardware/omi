"""Terminal handling for live transcription provider failures."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Awaitable, Callable, Protocol, cast

from starlette.websockets import WebSocketState

from models.message_event import MessageServiceStatusEvent
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.metrics import OMI_LISTEN_STT_UNAVAILABLE_TOTAL
from utils.observability.transcription import record_live_stt_failure, record_live_stt_pre_audio_failure
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    bounded_provider,
    failure_from_exception,
)
from utils.observability.fallback import (
    FailureFallbackKwargs,
    FirstTextDeadlineDiagnostics,
    ReplayLagDiagnostics,
    capacity_fallback_kwargs,
    first_text_fallback_kwargs,
    record_fallback,
)
from utils.stt.live_reason import LIVE_STT_FAILURE_REASONS, normalize_live_stt_reason
from config.live_stt_recovery import recovery_enabled, session_recovery_enabled
from utils.stt.recovery_state import current_recovery
from utils.stt.live_outcome import LiveLegOutcome
from utils.stt.stream_close import (
    ACCOUNT_REJECTION_REASONS,
    PROVIDER_AUTH_REJECTED,
    PROVIDER_BUDGET_EXHAUSTED,
    PROVIDER_RATE_LIMITED,
)

logger = logging.getLogger(__name__)

LIVE_STT_FAILURE_CLOSE_CODE = 1011
LIVE_STT_FAILURE_CLOSE_REASON = 'transcription_service_unavailable'


# Chain depth is 3 (velma/soniox/deepgram); allow walking it once, not looping.
# Shared by every live surface so a mid-session failover cannot loop a chain
# forever (#12459, #12469).
MAX_STT_FAILOVERS = 2

_KNOWN_FAILURE_REASONS = LIVE_STT_FAILURE_REASONS
_FAILURE_PHASE_BY_REASON = {
    'initialization_failed': 'initialization',
    'connection_lost': 'connection',
    'socket_unavailable': 'connection',
    'send_failed': 'send',
    # A typed in-stream rejection is the provider closing a connection it had
    # accepted. The bounded phase vocabulary has no 'serve' bucket, and 'send'
    # would claim our send failed, so 'connection' is the truthful bucket.
    'modulate_serve_error': 'connection',
    PROVIDER_BUDGET_EXHAUSTED: 'connection',
    PROVIDER_AUTH_REJECTED: 'connection',
    PROVIDER_RATE_LIMITED: 'connection',
    'soniox_idle_timeout': 'connection',
    'soniox_rotation': 'connection',
    'provider_5xx': 'connection',
    'capacity_full': 'connection',
    'first_text_deadline': 'connection',
    'empty_streak': 'connection',
    # The config frame was rejected after the WebSocket upgrade succeeded:
    # the session died at session setup, before any audio flowed.
    'soniox_invalid_hint': 'initialization',
}
# Diagnostic reasons without a legacy phase are connection-scoped.
for _reason in LIVE_STT_FAILURE_REASONS:
    _FAILURE_PHASE_BY_REASON.setdefault(_reason, 'connection')

_CIRCUIT_OPENING_REASONS = frozenset(
    {
        # 402 organization_balance_exhausted / organization_monthly_budget_exhausted:
        # the provider still ACCEPTS the WebSocket upgrade but refuses to serve
        # ANY stream, so the connect-time failure counter provably never
        # accumulates under reconnect load (each dying session's replacement
        # connects fine and calls record_success). Same mechanism
        # record_serve_failure exists for. The other typed shapes are
        # session-scoped — an idle-timeout is this session's VAD pattern and a
        # 413 rotation serves fine on a fresh connection — so they must not
        # bench the provider for everyone.
        *ACCOUNT_REJECTION_REASONS,
        # Velma's mid-session "Internal server error" / "Unable to complete
        # the request" frames: the provider accepted the stream, served audio,
        # and then failed. This is the dominant live-STT outage shape
        # (backend-listen #3/#10 signatures, 2026-08-31: ×11 and ×5 per 30m),
        # and mid-session failover rescues the session — which is exactly why
        # the death would otherwise stay invisible to selection: the surviving
        # session never runs the terminal funnel that feeds the circuit, and
        # the next session's successful connect resets the counter. One
        # serve-error death opens the circuit for the serve-error cooldown;
        # re-admission needs more than one half-open success so a 5xx storm
        # that still accepts connects cannot flap every 30s.
        # Session-scoped shapes (invalid input audio) stay untyped and do not
        # bench the provider.
        'modulate_serve_error',
    }
)

# Terminal reasons that are evidence about the *provider* while it was serving
# audio. ``initialization_failed`` happens at connect time, where the selection
# helper's threshold logic already sees it, and ``socket_unavailable`` is local
# state (no socket exists), not provider behavior.
# Local VAD/input failures are not evidence against a provider circuit either.
_SERVE_FAILURE_REASONS = frozenset({'connection_lost', 'send_failed'})


def fallback_metric_reason(reason: str | None) -> str:
    """Keep established account labels while sharing bounded source causes."""
    if reason == PROVIDER_BUDGET_EXHAUSTED:
        return 'quota'
    if reason == PROVIDER_AUTH_REJECTED:
        return 'auth'
    return normalize_live_stt_reason(reason)


def _segments_have_transcript(segments: object) -> bool:
    if not isinstance(segments, list):
        return False
    for segment in segments:
        if isinstance(segment, dict) and str(segment.get('text') or '').strip():
            return True
    return False


class PendingLiveFailover:
    """A mid-session hop that is not recovered until the new provider transcribes.

    Connect-time ``record_fallback(..., outcome='recovered')`` counted a Soniox
    socket that the vendor then closed for monthly budget exhaustion as a heal,
    so a 100% dead failover leg looked 100% healthy for 27.5h.
    """

    def __init__(
        self,
        *,
        from_mode: str,
        to_mode: str,
        component: str = 'stt_live_session',
        reason: str,
        capacity_subtype: str | None = None,
        source_outcome: LiveLegOutcome | None = None,
    ) -> None:
        self.component, self.reason = component, normalize_live_stt_reason(reason)
        self.capacity_subtype = capacity_subtype
        self.replay_lag_diagnostics: ReplayLagDiagnostics | None = None
        self.first_text_diagnostics: FirstTextDeadlineDiagnostics | None = None
        self.from_mode = from_mode
        self.to_mode = to_mode
        self._settled = False
        self._settlement_timer: asyncio.TimerHandle | None = None
        self.source_outcome = source_outcome
        pinned = getattr(source_outcome, 'recovery_enabled', None)
        self.recovery_enabled = pinned if type(pinned) is bool else recovery_enabled()
        if source_outcome is not None:
            self.reason = source_outcome.claim(reason, connect=component == 'stt_selection')
            if source_outcome.pending is None:
                source_outcome.pending = self
            if not source_outcome.settled:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass  # Synchronous tests; serving owners run on the listen loop.
                else:
                    # Recovery still requires text. After 30s without proof,
                    # report this hop as degraded, without touching its audio
                    # or connection. Source availability cannot depend on a
                    # silent successor eventually ending its session.
                    self._settlement_timer = loop.call_later(30, self._settle_delayed_hop)

    def _settle_delayed_hop(self) -> None:
        self.note_failure(None, continuing=True)

    def _mark_settled(self) -> None:
        self._settled = True
        if self._settlement_timer is not None:
            self._settlement_timer.cancel()
            self._settlement_timer = None

    @classmethod
    def from_socket(cls, source: object, from_mode: str, to_mode: str) -> 'PendingLiveFailover':
        """Capture the source cause before a successor can change the hop."""
        return cls(
            from_mode=from_mode,
            to_mode=to_mode,
            reason=live_stt_terminal_reason(source, 'connection_lost'),
            source_outcome=getattr(source, 'leg_outcome', None),
        )

    def _emit(self, **kwargs: Any) -> None:
        if self.source_outcome is None:
            record_fallback(**kwargs)
        else:
            self.source_outcome.settle(
                emit_fallback=lambda: record_fallback(**kwargs),
            )

    @property
    def settled(self) -> bool:
        return self._settled

    def capture_window_failure_details(self, source: object) -> None:
        """Carry the immutable pre-cancellation snapshot onto the hop outcome."""
        self.capacity_subtype = getattr(source, 'capacity_subtype', None)
        self.replay_lag_diagnostics = getattr(source, 'replay_lag_diagnostics', None)
        self.first_text_diagnostics = getattr(source, 'first_text_diagnostics', None)

    def note_transcript(self, segments: object | None = None) -> None:
        if self._settled:
            return
        if segments is not None and not _segments_have_transcript(segments):
            return
        self._mark_settled()
        self._emit(
            component=self.component,
            from_mode=self.from_mode,
            to_mode=self.to_mode,
            reason=fallback_metric_reason(self.reason),
            outcome='recovered',
            **first_text_fallback_kwargs(self.first_text_diagnostics),
            **capacity_fallback_kwargs(self.capacity_subtype, self.replay_lag_diagnostics),
        )

    def note_failure(self, typed_reason: str | None, *, continuing: bool = False) -> None:
        if self._settled:
            return
        self._mark_settled()
        # A hop still unproven when its owner departs is degraded recovery,
        # not evidence that we terminated an active client's transcription.
        source = self.source_outcome
        if (
            self.recovery_enabled
            and source is not None
            and (
                getattr(source, 'owner_closing', False)
                or (source.client_has_left is not None and source.client_has_left())
            )
        ):
            continuing = True
        # The hop belongs to the source leg; a successor failure changes the
        # outcome, never the source cause used to reconcile health evidence.
        reason = fallback_metric_reason(self.reason)
        details: FailureFallbackKwargs = {}
        if reason == 'other':
            details['failure_subtype'] = normalize_live_stt_reason(typed_reason)
        self._emit(
            component=self.component,
            from_mode=self.from_mode,
            to_mode=self.to_mode,
            reason=reason,
            outcome='degraded' if continuing else 'exhausted',
            **first_text_fallback_kwargs(self.first_text_diagnostics),
            **capacity_fallback_kwargs(self.capacity_subtype, self.replay_lag_diagnostics),
            **details,
        )


class LiveSTTSession(Protocol):
    active: bool
    close_code: int
    stt_terminal_failure: bool
    live_transcription_attempt: Any
    client_live_transcription_attempt: Any


def settle_terminal_socket(stt_socket: Any, provider: str | None, reason: str, *, departing: bool = False) -> None:
    """Settle a managed serving leg when the owner has exhausted recovery."""
    outcome = getattr(stt_socket, 'leg_outcome', None)
    if outcome is None or outcome.settled or outcome.owner_closing and not outcome.claimed:
        return
    if outcome.pending is not None:
        outcome.pending.note_failure(None, continuing=departing)
        return
    hop = PendingLiveFailover(
        from_mode=provider or 'unknown',
        to_mode='unavailable',
        reason=live_stt_terminal_reason(stt_socket, reason),
        source_outcome=outcome,
    )
    hop.note_failure(None, continuing=departing)


class LiveSTTClientSocket(Protocol):
    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


async def terminate_live_stt_backoff(
    websocket: LiveSTTClientSocket,
    session: LiveSTTSession,
    *,
    reason: str,
    retry_after: int,
) -> bool:
    """Send the existing terminal status and close before session work starts."""

    if reason not in {'provider_unavailable', 'reconnect_budget'}:
        raise ValueError('unsupported live STT backoff reason')
    if session.stt_terminal_failure:
        return False
    session.stt_terminal_failure = True
    session.active = False
    session.close_code = LIVE_STT_FAILURE_CLOSE_CODE
    OMI_LISTEN_STT_UNAVAILABLE_TOTAL.labels(reason=reason).inc()
    event = MessageServiceStatusEvent(
        status='stt_failed',
        status_text='Transcription temporarily unavailable',
        outcome=TranscriptionOutcome.UPSTREAM_ERROR.value,
        retryable=True,
        reason=reason,
        retry_after=max(1, min(int(retry_after), 3600)),
    )
    sent = False
    try:
        await websocket.send_json(event.to_json())
        sent = True
    except Exception as error:
        logger.warning('Unable to deliver terminal live STT status error_type=%s', type(error).__name__)
    try:
        await websocket.close(code=LIVE_STT_FAILURE_CLOSE_CODE, reason=LIVE_STT_FAILURE_CLOSE_REASON)
    except Exception as error:
        logger.info('Unable to close client after terminal live STT backoff error_type=%s', type(error).__name__)
    return sent


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

    # Managed legs latch exactly the cause used by their health observation.
    try:
        normalized = getattr(stt_socket, 'normalized_death_reason', None)
        if normalized is not None:
            return normalize_live_stt_reason(normalized, fallback)
        typed = getattr(stt_socket, 'typed_death_reason', None)
        raw = getattr(stt_socket, 'death_reason', None)
    except Exception:
        return normalize_live_stt_reason(fallback)
    return normalize_live_stt_reason(typed, raw, fallback)


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
    endpoint: str | None = None
    try:
        endpoint = getattr(stt_socket, 'routing_endpoint', None)
    except Exception:
        endpoint = None
    try:
        target_death = getattr(stt_socket, 'record_target_death', None)
        if callable(target_death) and target_death(typed):
            return True
    except Exception as error:
        logger.warning('Unable to record target circuit after provider death error_type=%s', type(error).__name__)
    return _open_serving_provider_circuit(typed, provider, endpoint=endpoint)


def _open_serving_provider_circuit(bounded_reason: str, provider: str | None, *, endpoint: str | None = None) -> bool:
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

        if endpoint:
            return open_provider_selection_circuit(provider, reason=bounded_reason, endpoint=endpoint)
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
    bounded_reason = normalize_live_stt_reason(reason)
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
        failure_phase = _FAILURE_PHASE_BY_REASON[bounded_reason]
        record_live_stt_failure(
            provider=failure.provider,
            platform=platform,
            outcome=failure.outcome,
            phase=failure_phase,
        )
        attempt = getattr(session, 'live_transcription_attempt', None)
        if attempt is not None:
            attempt.finish('failure', phase=failure_phase)
        else:
            record_live_stt_pre_audio_failure(
                provider=failure.provider,
                platform=platform,
                phase=failure_phase,
            )
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
    start_sample: int | None = None,
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
        if session_recovery_enabled(getattr(session, 'receiver', None)):
            # A synchronous enqueue can latch capacity_full before returning
            # False. Preserve that local cause rather than benching a healthy
            # provider as send_failed; OFF retains its original vocabulary.
            reason = live_stt_terminal_reason(stt_socket, reason)
        outcome = getattr(stt_socket, 'leg_outcome', None)
        if outcome is not None and outcome.owner_closing:
            # The final client-tail flush may still send valid audio, but its
            # transport errors cannot launch recovery or bench a provider.
            return
        if attempt_failover is not None and await attempt_failover():
            return
        if outcome is not None and outcome.owner_closing:
            return  # Client teardown can win while replacement admission awaits.
        receiver = getattr(session, 'receiver', None)
        if session_recovery_enabled(receiver):
            shutdown = getattr(session, 'shutdown_event', None)
            if not session.active or shutdown is not None and shutdown.is_set() is True:
                return
            controller = getattr(receiver, 'recovery', None) or current_recovery.get()
            if controller is not None and controller.client_has_left() is True:
                return  # The episode controller latched a departed client.
            if (
                getattr(websocket, 'client_state', None) == WebSocketState.DISCONNECTED
                or getattr(websocket, 'application_state', None) == WebSocketState.DISCONNECTED
            ):
                return
        if session.active and not session.stt_terminal_failure:
            settle_terminal_socket(stt_socket, provider, reason)
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

    receiver = getattr(attempt_failover, '__self__', None)
    retry = getattr(receiver, '_idle_onset_retry', None)
    try:
        if retry is not None:
            admitted = getattr(stt_socket, 'send_admitted_audio', None)
            accepted = admitted(*retry) if callable(admitted) else stt_socket.send(retry[0])
        else:
            accepted = (
                stt_socket.send(audio, start_sample=start_sample)
                if start_sample is not None
                else stt_socket.send(audio)
            )
    except TypeError:
        # A socket that predates the capture-position seam: send without it.
        try:
            accepted = stt_socket.send(audio)
        except Exception:
            await _recoverable_failure('send_failed')
            return False
    except Exception:
        await _recoverable_failure('send_failed')
        return False

    if accepted is not True:
        await _recoverable_failure('send_failed')
        return False

    complete = (
        getattr(stt_socket, 'complete_send', None) if getattr(stt_socket, 'idle_close_enabled', False) is True else None
    )
    try:
        completed = await cast(Callable[[], Awaitable[bool]], complete)() if callable(complete) else True
    except Exception:
        completed = False
    if not completed or live_stt_socket_is_dead(stt_socket):
        take = getattr(stt_socket, 'take_unsent_packet', None)
        if receiver is not None and callable(take):
            packet = take()
            if packet is not None:
                receiver._idle_onset_retry = packet
        await _recoverable_failure(
            live_stt_terminal_reason(stt_socket, 'connection_lost') if not completed else 'send_failed'
        )
        return False

    # Safe socket wrappers report send failures through the death latch instead
    # of raising so every provider must be checked after the send as well.
    if getattr(stt_socket, 'idle_close_enabled', False) is True:
        commit = getattr(stt_socket, 'commit_send', None)
        if callable(commit):
            commit()

    if receiver is not None and retry is not None:
        receiver._idle_onset_retry = None
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
    start_sample: int | None = None,
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
        start_sample=start_sample,
    )
    if sent:
        buffer.clear()
    return sent
