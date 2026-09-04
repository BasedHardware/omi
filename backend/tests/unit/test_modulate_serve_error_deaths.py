"""Modulate serve-error deaths must keep their type, severity, and fleet effect.

Production evidence (backend-listen, GCP 2026-08-31, Loop S sensor):
``ERROR:utils.stt.streaming:Modulate streaming error: Internal server error``
was the #3 error signature (×11/30m) with ``Unable to complete the request.
Please try again.`` at #10 (×5/30m); over the following day the sensor
recorded 62 and ~5 more per 6h window while every session was rescued by
mid-session failover. Modulate-Velma-2 is the streaming PRIMARY
(``modulate-velma-2,soniox,dg-nova-3,parakeet``), so during such an outage
every new session is handed to Velma, serves briefly, takes the error frame,
and fails over — the session survives, which is exactly why nothing ever
paged beyond the log line:

- the socket latched the death but no typed reason, so the failover seam's
  ``note_typed_provider_death`` (built for the Soniox 402 in
  ``test_soniox_typed_rejections.py``) read ``None`` and returned False —
  ``_modulate_circuit`` never opened;
- the rescued session never runs ``terminate_live_stt_session``, the other
  funnel that feeds the circuit;
- the next session's successful *connect* calls ``record_success`` and resets
  the connect-time counter, so the threshold can never trip either
  (the blindness ``ProviderCircuitBreaker.record_serve_failure`` exists for).

Net effect: selection re-chose the failing primary for every reconnecting
client for the duration of each outage, burning ~150ms+ of dead-stream time
per session and one dropped segment per failover, while a healthy Soniox /
Deepgram / Parakeet chain sat idle behind it.

Failure-Class: FC-serve-time-death-invisible-to-selection — a health signal
that gates provider selection must be fed by every terminal observation of
the thing whose health it claims to track. A mid-session provider error frame
that failover rescues is terminal evidence about the provider, and the seam
that rescues it is the only observer that runs. The typed frame must survive
to every consumer, mirroring the Soniox 402 precedent: the log severity (a
serve error stays ERROR — it IS the outage signal; session-caused frames step
down to WARNING), the bounded terminal-failure reason vocabulary, and the
process-local selection circuit opened at the failover seam.

These tests drive the REAL ``SafeModulateSocket`` receive loop with the
production frame shapes, the REAL failover method on ``ListenReceiver``, the
REAL terminal funnel from ``utils.stt.live_failure``, and the REAL circuit
state machine at its singleton seam — only the process-global circuit opener
is patched, at its lazy-import seam, where observing the call is the point.
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from routers.listen.receiver import ListenReceiver
from utils.stt import live_failure, streaming
from utils.stt.live_failure import (
    LIVE_STT_FAILURE_CLOSE_CODE,
    live_stt_terminal_reason,
    note_typed_provider_death,
    terminate_live_stt_session,
)
from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.streaming import (
    MODULATE_DEATH_SERVE_ERROR,
    STTService,
    SafeModulateSocket,
    connect_stt_socket_with_fallback,
    modulate_death_reason,
)
from utils.stt.vad_gate import GatedSTTSocket

STREAMING_LOGGER = 'utils.stt.streaming'

# The production error samples these tests replay (sensor, 2026-08-31).
SERVE_ERROR_MESSAGE = 'Internal server error'
SERVE_ERROR_MESSAGE_2 = 'Unable to complete the request. Please try again.'
SESSION_SCOPED_MESSAGE = 'Invalid input audio'


class FakeWebSocket:
    """Provider WebSocket yielding a scripted inbound frame list."""

    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)

        return gen()


def _drive_socket(frames, *, wait: float = 0.05):
    """Run a real SafeModulateSocket over the scripted frames and return it."""

    def run():
        captured = []

        async def main():
            ws = FakeWebSocket(frames)
            sock = SafeModulateSocket(ws, captured.append, asyncio.get_running_loop())
            await asyncio.sleep(wait)
            return sock

        return asyncio.run(main())

    return run()


async def _drive_socket_in_loop(frames, *, wait: float = 0.05):
    """Same as ``_drive_socket`` for tests that already hold the event loop."""
    ws = FakeWebSocket(frames)
    sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
    await asyncio.sleep(wait)
    return sock


def _error_frame(message):
    return {'type': 'error', 'error': message}


def _circuit_recorder():
    calls = []

    def fake_opener(provider, *, reason):
        calls.append((provider, reason))
        return True

    return calls, fake_opener


@pytest.fixture(autouse=True)
def _fresh_real_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap fresh real breakers into the singleton seam, one per provider.

    The production paths address ``streaming._<provider>_circuit`` singletons
    through ``_circuit_for_primary``'s call-time lookup. Fresh instances keep
    this file's circuit-state assertions deterministic regardless of test
    order while still exercising the real state machine.
    """
    for service in STTService:
        monkeypatch.setattr(
            streaming,
            f'_{service.value}_circuit',
            ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0),
        )


@pytest.fixture(autouse=True)
def _quiet_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **_labels: None)
    monkeypatch.setattr(streaming, 'record_fallback', lambda **_kwargs: None)


# ---------------------------------------------------------------------------
# modulate_death_reason: bound the provider's free-text frame, degrading safely.
# ---------------------------------------------------------------------------


def test_the_prod_internal_server_error_shape_is_a_serve_error():
    """The #3 signature verbatim: the provider failed the stream it accepted."""
    assert modulate_death_reason(SERVE_ERROR_MESSAGE) == MODULATE_DEATH_SERVE_ERROR


def test_the_prod_unable_to_complete_shape_is_a_serve_error():
    """The #10 signature verbatim (×5/30m)."""
    assert modulate_death_reason(SERVE_ERROR_MESSAGE_2) == MODULATE_DEATH_SERVE_ERROR


def test_matching_tolerates_provider_casing_and_punctuation():
    assert modulate_death_reason('Internal Server Error.') == MODULATE_DEATH_SERVE_ERROR
    assert modulate_death_reason('  INTERNAL SERVER ERROR ') == MODULATE_DEATH_SERVE_ERROR


def test_account_state_refusals_are_serve_errors():
    """Velma's connect-time over-quota answer: no stream can be served."""
    assert modulate_death_reason('Monthly usage limit reached.') == MODULATE_DEATH_SERVE_ERROR


def test_session_scoped_shapes_stay_untyped():
    """Invalid audio we sent is our fault; a rate limit is this session's.
    Neither may bench the provider for every other client."""
    assert modulate_death_reason(SESSION_SCOPED_MESSAGE) is None
    assert modulate_death_reason('rate limit') is None
    assert modulate_death_reason('connection reset') is None


def test_unknown_and_empty_shapes_stay_untyped():
    """A new provider wording must not grow the bounded vocabulary per message."""
    assert modulate_death_reason(None) is None
    assert modulate_death_reason('') is None
    assert modulate_death_reason('a brand new provider wording') is None


# ---------------------------------------------------------------------------
# The real receive loop: severity follows fault origin; the type is latched.
# ---------------------------------------------------------------------------


def test_a_serve_error_frame_logs_at_error_and_latches_the_typed_reason(caplog):
    with caplog.at_level(logging.WARNING, logger=STREAMING_LOGGER):
        sock = _drive_socket([_error_frame(SERVE_ERROR_MESSAGE)])
    assert sock.is_connection_dead
    assert sock.typed_death_reason == MODULATE_DEATH_SERVE_ERROR
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Modulate streaming error:' in r.message]
    assert errors, 'a serve error is the outage signal: it must stay at ERROR'


def test_a_session_scoped_frame_logs_at_warning_not_error(caplog):
    with caplog.at_level(logging.WARNING, logger=STREAMING_LOGGER):
        sock = _drive_socket([_error_frame(SESSION_SCOPED_MESSAGE)])
    assert sock.is_connection_dead
    assert sock.typed_death_reason is None
    assert [r.levelname for r in caplog.records if 'Modulate stream' in r.message] == ['WARNING']


def test_the_raw_provider_text_stays_on_the_death_latch():
    """The typed reason bounds telemetry; the raw text stays on the latch for logs."""
    sock = _drive_socket([_error_frame(SERVE_ERROR_MESSAGE)])
    assert SERVE_ERROR_MESSAGE in (sock.death_reason or '')


def test_the_serve_error_still_flushes_partial_text_and_sets_done():
    """The reclassification must not change finalization: an error frame still
    flushes any pending partial and sets done_event so drain does not hang."""
    partial = {'type': 'partial_utterance', 'partial_utterance': {'text': 'hello world', 'start_ms': 0}}
    captured = []
    frames = [partial, _error_frame(SERVE_ERROR_MESSAGE)]

    async def main():
        sock = SafeModulateSocket(FakeWebSocket(frames), captured.append, asyncio.get_running_loop())
        await asyncio.sleep(0.05)
        return sock

    sock = asyncio.run(main())
    assert sock._done_event.is_set()
    assert [seg['text'] for batch in captured for seg in batch] == ['hello world']


def test_a_live_socket_reports_no_typed_reason():
    sock = _drive_socket(
        [
            {
                'type': 'utterance',
                'utterance': {'text': 'hello', 'start_ms': 0, 'duration_ms': 1000, 'speaker': 1},
            },
            {'type': 'done', 'duration_ms': 5000},
        ]
    )
    assert not sock.is_connection_dead
    assert sock.typed_death_reason is None


def test_the_vad_gate_proxies_the_modulate_typed_reason():
    """The listen path wraps the socket in GatedSTTSocket; the type must survive."""
    dead = _drive_socket([_error_frame(SERVE_ERROR_MESSAGE)])
    gated = GatedSTTSocket(dead)
    assert gated.is_connection_dead
    assert gated.typed_death_reason == MODULATE_DEATH_SERVE_ERROR


def test_the_gate_reports_none_for_an_untyped_modulate_death():
    """A session-scoped death wrapped by the gate must read as untyped too."""
    dead = _drive_socket([_error_frame(SESSION_SCOPED_MESSAGE)])
    gated = GatedSTTSocket(dead)
    assert gated.is_connection_dead
    assert gated.typed_death_reason is None


# ---------------------------------------------------------------------------
# The terminal vocabulary: every funnel reports the provider's type.
# ---------------------------------------------------------------------------


def test_the_typed_reason_is_in_the_bounded_terminal_vocabulary():
    assert MODULATE_DEATH_SERVE_ERROR in live_failure._KNOWN_FAILURE_REASONS
    assert live_failure._FAILURE_PHASE_BY_REASON[MODULATE_DEATH_SERVE_ERROR] == 'connection'


def test_a_terminal_funnel_prefers_the_typed_rejection_over_its_vantage_point():
    sock = SimpleNamespace(typed_death_reason=MODULATE_DEATH_SERVE_ERROR)
    assert live_stt_terminal_reason(sock, 'connection_lost') == MODULATE_DEATH_SERVE_ERROR


def test_the_bounded_vocabulary_stays_bounded():
    """The typed vocabulary must not grow per provider message: every reason a
    terminal funnel can report is known up front, and the serve-error token is
    a single stable string."""
    assert MODULATE_DEATH_SERVE_ERROR == 'modulate_serve_error'
    assert len(live_failure._KNOWN_FAILURE_REASONS) == len(set(live_failure._KNOWN_FAILURE_REASONS))
    for reason in live_failure._KNOWN_FAILURE_REASONS:
        assert reason in live_failure._FAILURE_PHASE_BY_REASON


def test_the_serve_error_is_circuit_opening_but_connection_lost_is_not():
    """Only the typed serve error benches the provider at the seam; the generic
    observer vantage point (connection_lost) must keep passing through."""
    assert MODULATE_DEATH_SERVE_ERROR in live_failure._CIRCUIT_OPENING_REASONS
    assert 'connection_lost' not in live_failure._CIRCUIT_OPENING_REASONS
    assert 'soniox_idle_timeout' not in live_failure._CIRCUIT_OPENING_REASONS


def test_note_typed_death_ignores_an_unlatched_socket():
    """Sockets without the property (older wrappers, mocks) pass through safely."""
    assert note_typed_provider_death(object(), 'modulate') is False
    assert note_typed_provider_death(SimpleNamespace(typed_death_reason=None), 'modulate') is False


def test_note_typed_death_ignores_an_unknown_provider_name():
    """The seam tolerates provider tokens it cannot map, same shape as
    open_provider_selection_circuit."""
    dead = SimpleNamespace(typed_death_reason=MODULATE_DEATH_SERVE_ERROR)
    assert note_typed_provider_death(dead, 'not-a-provider') is False


@pytest.mark.asyncio
async def test_terminate_with_a_serve_error_opens_the_circuit_and_reports_the_reason():
    """When the chain is exhausted the session dies; the circuit must still learn."""
    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001, live_transcription_attempt=None)
    failure = TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='modulate', retryable=True)
    recorded = []
    with patch.object(live_failure, 'record_live_stt_failure', lambda **labels: recorded.append(labels)):
        calls, opener = _circuit_recorder()
        with patch('utils.stt.streaming.open_provider_selection_circuit', side_effect=opener):
            await terminate_live_stt_session(
                websocket, session, failure=failure, reason=MODULATE_DEATH_SERVE_ERROR, platform='ios'
            )

    assert session.stt_terminal_failure is True
    assert session.close_code == LIVE_STT_FAILURE_CLOSE_CODE
    event = websocket.send_json.await_args.args[0]
    assert event['reason'] == MODULATE_DEATH_SERVE_ERROR
    assert event['provider'] == 'modulate'
    assert recorded[0]['phase'] == 'connection'
    assert calls == [('modulate', MODULATE_DEATH_SERVE_ERROR)]


# ---------------------------------------------------------------------------
# The failover seam — the actual incident: the session SURVIVES, selection learns.
# ---------------------------------------------------------------------------


class HealthyReplacement:
    def __init__(self) -> None:
        self.finished = False

    @property
    def is_connection_dead(self) -> bool:
        return False

    @property
    def death_reason(self):
        return None

    def send(self, audio):  # pragma: no cover - never sent to in these tests
        return True

    def finish(self) -> None:
        self.finished = True


def _receiver_with_dead_modulate(dead_socket):
    host = MagicMock()
    host.is_multi_channel = False
    host.use_custom_stt = False
    host.state.active = True
    host.state.stt_terminal_failure = False
    host.language = 'en'
    host.multi_lang_enabled = True
    host.stt_service = STTService.modulate

    receiver = ListenReceiver(host, [], {})
    receiver.stt_socket = dead_socket
    receiver.vad_gate = None
    receiver._stt_rebuild = (lambda _s: None, lambda _s: None, 16000)
    receiver._create_stt_socket = AsyncMock(return_value=HealthyReplacement())
    return receiver


@pytest.mark.asyncio
async def test_a_serve_error_death_surviving_failover_opens_the_selection_circuit():
    """The regression this file exists for.

    A REAL SafeModulateSocket that died on the production ``Internal server
    error`` frame, and the REAL failover method: the session must move to the
    next provider AND the modulate circuit must open. Before the fix the socket
    latched no typed reason, ``note_typed_provider_death`` returned False at
    this exact seam, and selection kept choosing the failing primary.
    """
    dead = await _drive_socket_in_loop([_error_frame(SERVE_ERROR_MESSAGE)])
    assert dead.typed_death_reason == MODULATE_DEATH_SERVE_ERROR
    receiver = _receiver_with_dead_modulate(dead)
    calls, opener = _circuit_recorder()

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ), patch('utils.stt.provider_resilience.STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.02), patch(
        'utils.stt.streaming.open_provider_selection_circuit', side_effect=opener
    ):
        assert await receiver._failover_stt_socket() is True

    assert receiver.host.stt_service == STTService.soniox
    assert calls == [('modulate', MODULATE_DEATH_SERVE_ERROR)], (
        'the failover seam is the only observer that runs when the session survives; '
        'it must hand the serve-error death to selection'
    )


@pytest.mark.asyncio
async def test_a_session_scoped_death_surviving_failover_does_not_bench_the_provider():
    """Invalid audio we sent killed THIS stream; other clients keep Velma."""
    dead = await _drive_socket_in_loop([_error_frame(SESSION_SCOPED_MESSAGE)])
    assert dead.typed_death_reason is None
    receiver = _receiver_with_dead_modulate(dead)
    calls, opener = _circuit_recorder()

    with patch(
        'routers.listen.receiver.get_stt_service_for_language',
        return_value=(STTService.soniox, 'en', 'soniox'),
    ), patch('utils.stt.provider_resilience.STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.02), patch(
        'utils.stt.streaming.open_provider_selection_circuit', side_effect=opener
    ):
        assert await receiver._failover_stt_socket() is True

    assert calls == []


def test_note_typed_provider_death_opens_the_real_modulate_circuit():
    """End to end without patching the opener: the typed latch reaches the
    real circuit singleton (swapped fresh by the fixture) through the real
    lazy-import seam."""
    dead = _drive_socket([_error_frame(SERVE_ERROR_MESSAGE)])
    assert note_typed_provider_death(dead, 'modulate') is True
    assert streaming._modulate_circuit.state == 'open'
    assert streaming._soniox_circuit.state == 'closed'
    assert streaming._deepgram_circuit.state == 'closed'


@pytest.mark.asyncio
async def test_the_audio_send_path_terminates_with_the_typed_reason():
    """The send path is often the first observer of death (it polls the latch on
    every chunk); it must not collapse the type when the chain is exhausted."""

    dead = await _drive_socket_in_loop([_error_frame(SERVE_ERROR_MESSAGE)])

    websocket = AsyncMock()
    session = SimpleNamespace(active=True, stt_terminal_failure=False, close_code=1001)
    with patch.object(live_failure, 'record_live_stt_failure'):
        sent = await live_failure.send_live_stt_audio(
            websocket,
            session,
            stt_socket=dead,
            audio=b'\x01\x00',
            provider='modulate',
            platform='ios',
        )

    assert sent is False
    assert session.stt_terminal_failure is True
    event = websocket.send_json.await_args.args[0]
    assert event['reason'] == MODULATE_DEATH_SERVE_ERROR
    assert event['provider'] == 'modulate'


def test_a_burst_of_serve_error_deaths_leaves_the_vocabulary_stable():
    """The incident restated: repeated prod-shaped frames must latch the same
    bounded token every time — no per-message drift, no cardinality growth."""
    for message in (SERVE_ERROR_MESSAGE, SERVE_ERROR_MESSAGE_2, 'Internal Server Error.'):
        sock = _drive_socket([_error_frame(message)])
        assert sock.typed_death_reason == MODULATE_DEATH_SERVE_ERROR


def test_the_serve_error_maps_to_quota_aware_fallback_telemetry():
    """``_fallback_failure_reason`` reads the death text at the selection seam;
    an account-state refusal must classify as quota, not provider_5xx."""
    assert streaming._fallback_failure_reason(RuntimeError('Monthly usage limit reached.')) == 'quota'
    assert streaming._fallback_failure_reason(RuntimeError('Internal server error')) == 'provider_5xx'


def test_connection_closed_deaths_stay_untyped():
    """Transport-level deaths (no error frame) never carried provider intent;
    they must not gain a typed reason from this change."""
    sock = _drive_socket([])
    assert sock.is_connection_dead
    assert 'closed cleanly' in (sock.death_reason or '')
    assert sock.typed_death_reason is None


@pytest.mark.asyncio
async def test_selection_skips_the_benched_modulate_primary_on_the_next_connect():
    """The point of the circuit: after the seam learns, the NEXT session walks
    straight to a healthy fallback instead of retrying the failing primary."""
    dead = await _drive_socket_in_loop([_error_frame(SERVE_ERROR_MESSAGE)])
    assert note_typed_provider_death(dead, 'modulate') is True
    assert streaming._modulate_circuit.state == 'open'

    healthy_fallback = HealthyReplacement()

    async def _refuse_primary():
        raise AssertionError('selection must not reconnect to the provider that died serving')

    async def _connect_fallback():
        return healthy_fallback

    with patch('utils.stt.provider_resilience.STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.02):
        socket, service = await connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=_refuse_primary,
            connect_deepgram=_connect_fallback,
        )

    assert socket is healthy_fallback
    assert service == STTService.deepgram


def test_the_circuit_recovers_through_the_half_open_probe():
    """Benching Velma must not brick it: after the cooldown exactly one probe
    is offered, and a probe that serves closes the circuit again."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0, clock=lambda: now[0])

    circuit.record_serve_failure()
    assert circuit.state == 'open'
    assert circuit.allow_request() is False

    now[0] = 31.0
    assert circuit.allow_request() is True  # the single half-open probe
    assert circuit.allow_request() is False

    circuit.record_success()
    assert circuit.state == 'closed'
