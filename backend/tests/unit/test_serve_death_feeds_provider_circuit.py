"""Regression: a serve-time provider death must feed the selection circuit.

Production loop sensor (backend-listen, 30-min window 2026-08-31T05:30Z)
recorded 62 occurrences of:

    ERROR:utils.stt.streaming:Modulate streaming error: Internal server error

Modulate accepted every WebSocket upgrade, served audio, and then died
mid-session with an internal error. Session teardown handled the dead client
correctly (stt_failed + 1011), but provider *selection* kept choosing
Modulate for every reconnecting client for the whole incident, because
``connect_stt_socket_with_fallback`` only records connect-time outcomes:

- the dying provider still accepts connects, so each reconnect calls
  ``record_success`` and RESETS the failure counter;
- the serve-time death never reached the circuit at all.

So the counter provably never reaches ``failure_threshold`` under reconnect
load (connect -> die -> reconnect -> die), and the fleet hammers the dead
provider for the duration of the outage instead of skipping to the healthy
fallback configured right behind it (#11752 built that chain; this is the
feedback leg it never had).

These tests drive the real ``terminate_live_stt_session`` funnel (not the
individual send paths — all four funnel there) and the real
``ProviderCircuitBreaker`` state machine at the real singleton seam
(``streaming._modulate_circuit`` etc.), so both the classification boundary
and the state transition are exercised for real.

Failure-Class: new — the violated contract is the circuit's learning
boundary: a health signal that gates selection must be fed by every terminal
observation of the thing whose health it claims to track. Serve-time death
was terminal, observed, and invisible to it.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import patch

import pytest

from utils.stt import live_failure, streaming
from utils.stt.live_failure import terminate_live_stt_session
from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.streaming import STTService, open_provider_selection_circuit


@dataclass
class _Session:
    active: bool = True
    close_code: int = 1001
    stt_terminal_failure: bool = False
    live_transcription_attempt: Any = None
    client_live_transcription_attempt: Any = None


class _ClientSocket:
    def __init__(self) -> None:
        self.closed = False

    async def send_json(self, _data: Any) -> None:
        pass

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


def _failure(provider: str) -> TranscriptionFailure:
    return TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider=provider, retryable=True)


def _connect_returning(socket: Any):
    async def _connect() -> Any:
        return socket

    return _connect


def _connect_raising(error: BaseException):
    async def _connect() -> Any:
        raise error

    return _connect


@pytest.fixture(autouse=True)
def _quiet_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **_labels: None)
    monkeypatch.setattr(streaming, 'record_fallback', lambda **_kwargs: None)


@pytest.fixture(autouse=True)
def _fresh_real_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap fresh real breakers into the singleton seam, one per provider.

    The production code paths address ``streaming._<provider>_circuit``
    singletons. Fresh instances keep this file's assertions about circuit
    STATE deterministic regardless of test order inside the file, while still
    exercising the real ProviderCircuitBreaker transitions (open, cooldown,
    half-open probe) rather than a mock's canned answers.
    """
    for service in STTService:
        monkeypatch.setattr(
            streaming,
            f'_{service.value}_circuit',
            ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0),
        )


async def _terminate(provider: str, reason: str) -> _ClientSocket:
    websocket = _ClientSocket()
    await terminate_live_stt_session(websocket, _Session(), failure=_failure(provider), reason=reason, platform='ios')
    return websocket


# --- the incident shape: serve-time death must open the circuit ---------------


@pytest.mark.asyncio
async def test_serve_time_death_opens_the_serving_providers_circuit() -> None:
    await _terminate('modulate', 'connection_lost')

    assert streaming._modulate_circuit.state == 'open'
    # The incident's other providers are untouched: the death is evidence
    # about the provider that was serving, not about its fallbacks.
    assert streaming._deepgram_circuit.state == 'closed'
    assert streaming._parakeet_circuit.state == 'closed'


@pytest.mark.asyncio
async def test_send_phase_death_also_feeds_the_circuit() -> None:
    """A provider that died during send is the same terminal evidence."""
    await _terminate('parakeet', 'send_failed')

    assert streaming._parakeet_circuit.state == 'open'


@pytest.mark.asyncio
async def test_reconnect_skips_the_provider_that_died_serving() -> None:
    """End to end at the selection seam: after a serve-time death the next
    connect must walk straight to the healthy fallback instead of retrying
    the provider that just died.
    """
    await _terminate('modulate', 'connection_lost')
    assert streaming._modulate_circuit.state == 'open'

    healthy_fallback = SimpleNamespace(is_connection_dead=False, death_reason=None)
    with patch('utils.stt.provider_resilience.STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.05):
        socket, service = await streaming.connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=_connect_raising(
                AssertionError('selection must not reconnect to the provider that died serving')
            ),
            connect_deepgram=_connect_returning(healthy_fallback),
        )

    assert socket is healthy_fallback
    assert service == STTService.deepgram


# --- the boundary: what must NOT open the circuit -----------------------------


@pytest.mark.asyncio
async def test_initialization_failure_does_not_open_the_circuit() -> None:
    """Connect-phase failures already flow through the threshold in the selection helper.

    Recording them here too would double-count one failure and bypass the
    threshold entirely for config errors at startup.
    """
    await _terminate('modulate', 'initialization_failed')

    assert streaming._modulate_circuit.state == 'closed'


@pytest.mark.asyncio
async def test_unavailable_socket_does_not_open_the_circuit() -> None:
    """``socket_unavailable`` is local state (no socket exists), not provider behavior."""
    await _terminate('modulate', 'socket_unavailable')

    assert streaming._modulate_circuit.state == 'closed'


@pytest.mark.asyncio
async def test_unbounded_reason_does_not_open_the_circuit() -> None:
    """``_bounded_reason`` maps anything unknown to connection_lost — pinned so
    the mapping cannot silently start tripping circuits for new reasons."""
    websocket = _ClientSocket()
    await terminate_live_stt_session(
        websocket,
        _Session(),
        failure=_failure('modulate'),
        reason='something_new',
        platform='ios',
    )

    assert websocket.closed is True
    assert streaming._modulate_circuit.state == 'open'  # bounded to connection_lost


@pytest.mark.asyncio
async def test_idempotent_terminal_runs_the_circuit_leg_once() -> None:
    websocket = _ClientSocket()
    session = _Session()

    await terminate_live_stt_session(
        websocket, session, failure=_failure('modulate'), reason='connection_lost', platform='ios'
    )
    # A second observer (teardown, another channel) sees stt_terminal_failure
    # already latched and must not run the terminal path again.
    await terminate_live_stt_session(
        websocket, session, failure=_failure('modulate'), reason='connection_lost', platform='ios'
    )

    assert streaming._modulate_circuit.state == 'open'
    # Still inside the 30s cooldown: the second call did not re-open with a
    # later timestamp (which would extend the outage window).
    assert streaming._modulate_circuit.allow_request() is False


# --- unknown provider names must not break the terminal path ------------------


@pytest.mark.asyncio
async def test_unknown_provider_name_terminates_normally() -> None:
    """The terminal close is the contract; circuit bookkeeping is best-effort.

    ``provider`` can be None or a future name STTService does not know; the
    session must still terminate exactly as before.
    """
    websocket = await _terminate('not-a-provider', 'connection_lost')

    assert websocket.closed is True


def test_open_provider_selection_circuit_rejects_unknown_names() -> None:
    assert open_provider_selection_circuit(None, reason='connection_lost') is False
    assert open_provider_selection_circuit('not-a-provider', reason='connection_lost') is False


def test_open_provider_selection_circuit_opens_the_named_provider() -> None:
    assert open_provider_selection_circuit('soniox', reason='send_failed') is True
    assert streaming._soniox_circuit.state == 'open'


# --- the state machine: recovery still exists ---------------------------------


def test_circuit_recovers_through_the_half_open_probe() -> None:
    """Opening on serve-death must not brick the provider forever.

    After the cooldown the breaker offers exactly one probe; a successful
    probe closes the circuit again. This pins the recovery half of the new
    transition against future "safety" additions.
    """
    now: List[float] = [0.0]
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0, clock=lambda: now[0])

    circuit.record_serve_failure()
    assert circuit.state == 'open'
    assert circuit.allow_request() is False  # inside cooldown

    now[0] = 31.0
    assert circuit.state == 'open'
    assert circuit.allow_request() is True  # the single half-open probe
    assert circuit.allow_request() is False  # and only one

    circuit.record_success()
    assert circuit.state == 'closed'
    assert circuit.allow_request() is True


# --- ProviderCircuitBreaker.record_serve_failure unit contract ----------------


def test_record_serve_failure_opens_immediately_regardless_of_counter() -> None:
    """The whole point: serve deaths cannot accumulate through record_failure.

    With threshold 3, two connect failures leave the counter at 2. A
    serve-time death must open the circuit NOW — waiting for a third event
    that the reconnect/reset cycle provably never delivers is the bug.
    """
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.state == 'closed'

    circuit.record_serve_failure()
    assert circuit.state == 'open'


def test_record_failure_counter_is_reset_by_connect_success_between_deaths() -> None:
    """Documents the mechanism the incident exposed (no behavior change here).

    Threshold 3, but under reconnect load each serve death is followed by the
    next session's successful CONNECT before that session dies too: the
    counter oscillates 1 -> 0 -> 1 and never opens. This is why serve deaths
    need their own transition instead of reusing record_failure.
    """
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    for _ in range(10):
        circuit.record_failure()  # a session died; the client reconnects...
        circuit.record_success()  # ...and the dying provider ACCEPTS the connect
    assert circuit.state == 'closed'
