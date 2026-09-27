"""The Modulate serve-error bench must not cycle under a sustained outage.

Production evidence (backend-listen, GCP, Loop S sensor 2026-09-20 → 09-22):

    ERROR:utils.stt.streaming:Modulate streaming error: Internal server error

ran at ~1.2-3.3k lines per hour for ~5h straight on 09-22 (measured:
~50/minute at 07:00-07:10Z; 194 ``Opening modulate selection circuit``
records in the single minute after the provider recovered at 08:12Z), with
~12k lines on 09-20 and ~33k on 09-21. Every dying session was rescued by
mid-session failover — the sessions survived, the outage burned on.

The 2026-08-31 fix (``test_modulate_serve_error_deaths.py``) latched the
typed death and opened ``_modulate_circuit`` for a flat 180s bench. That
recovery path is the leak this file pins closed: after every window the
breaker re-closed on probe "successes" whose only evidence was the 0.3s
post-connect liveness grace — far shorter than the latency of the provider
fault that killed the previous sessions. So each cycle re-admitted the
failing Velma primary at full session rate: reconnecting clients were handed
to it, served briefly, died mid-session, failed over, and the cycle repeated
~every 3 minutes for the length of the outage.

Failure-Class: FC-typed-failure-collapsed-to-generic — the same class the
2026-08-31 fix closed on the connect side. Its tail clause is the contract
here: the typed serve-error evidence the seam already holds must keep its
class into the recovery decision. Collapsing a stream that later died
serving into a generic connect-time "success" re-opened admission to the
same failing provider, so the same exhausted failure kept firing. This
change keeps the class: re-closing a serve-death bench requires serving
evidence (transcript or done frame) and the bench escalates while the
deaths continue.

These tests drive the REAL breaker state machine with an injected clock, the
REAL ``connect_stt_socket_with_fallback`` legacy path, and the REAL
``SafeModulateSocket`` receive loop with the production frame shapes; only
process-global singletons and the wall clock are patched.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from utils.stt import provider_resilience, streaming
from utils.stt.provider_resilience import (
    SERVE_BENCH_ESCALATION_CAP_EVENTS,
    ProviderCircuitBreaker,
    serve_bench_seconds,
)
from utils.stt.streaming import STTService, SafeModulateSocket, connect_stt_socket_with_fallback

SERVE_ERROR_MESSAGE = 'Internal server error'


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeWebSocket:
    """Provider WebSocket yielding a scripted inbound frame list.

    ``delay`` holds the first frame back so a test can observe the socket in
    the window between the liveness grace and the provider's first answer —
    the exact window where the connect seam attaches serving-evidence
    callbacks.
    """

    def __init__(self, inbound, delay: float = 0.0, tail: float = 0.0):
        self._inbound = list(inbound)
        self._delay = delay
        self._tail = tail
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            if self._delay:
                await asyncio.sleep(self._delay)
            for msg in self._inbound:
                yield json.dumps(msg)
            if self._tail:
                # Hold the stream open past the caller's sample point: without
                # this the async-for exhausts and the clean-close latch marks
                # the socket dead before the liveness grace observes it.
                await asyncio.sleep(self._tail)

        return gen()


def _drive_socket(frames, *, wait: float = 0.05):
    """Run a real SafeModulateSocket over the scripted frames (own loop)."""

    async def main():
        ws = FakeWebSocket(frames)
        sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
        await asyncio.sleep(wait)
        return sock

    return asyncio.run(main())


async def _drive_socket_in_loop(frames, *, wait: float = 0.05, delay: float = 0.0, tail: float = 0.0):
    """Same as ``_drive_socket`` for tests that already hold the event loop."""
    ws = FakeWebSocket(frames, delay=delay, tail=tail)
    sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
    await asyncio.sleep(wait)
    return sock


@pytest.fixture(autouse=True)
def _fresh_real_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    for service in STTService:
        monkeypatch.setattr(
            streaming,
            f'_{service.value}_circuit',
            ProviderCircuitBreaker(
                failure_threshold=3,
                cooldown_seconds=30.0,
                serve_error_cooldown_seconds=180.0,
                serve_error_successes_to_close=3,
            ),
        )


@pytest.fixture(autouse=True)
def _quiet_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(streaming, 'record_fallback', lambda **_kwargs: None)


# ---------------------------------------------------------------------------
# The ladder: pure function, escalation capped.
# ---------------------------------------------------------------------------


def test_ladder_rungs_double_from_the_baseline():
    assert serve_bench_seconds(180.0, 0) == 180.0
    assert serve_bench_seconds(180.0, 1) == 360.0
    assert serve_bench_seconds(180.0, 2) == 720.0
    assert serve_bench_seconds(180.0, 3) == 1440.0


def test_ladder_caps_at_three_escalations():
    assert SERVE_BENCH_ESCALATION_CAP_EVENTS == 3
    assert serve_bench_seconds(180.0, 4) == 1440.0
    assert serve_bench_seconds(180.0, 99) == 1440.0


def test_ladder_never_shrinks_or_zeroes_the_bench():
    assert serve_bench_seconds(180.0, -3) == 180.0
    assert serve_bench_seconds(30.0, 3) == 240.0


def test_the_provider_stays_probeable_at_the_top_of_the_ladder():
    """The cap is the anti-brick: even a full ladder re-probes ~every 24 min."""
    assert serve_bench_seconds(180.0, SERVE_BENCH_ESCALATION_CAP_EVENTS) <= 1440.0


def test_the_circuit_still_opens_after_threshold_with_escalation_fields_present():
    """Construction with the new ladder fields keeps the legacy contract."""
    circuit = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30.0)
    assert circuit.serve_error_bench_seconds == 180.0  # modulate default
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.state == 'open'
    assert circuit.serve_error_bench_seconds == 180.0  # connect open: ladder untouched


# ---------------------------------------------------------------------------
# The real state machine: escalation, evidence-gated close, ladder reset.
# ---------------------------------------------------------------------------


def test_each_serve_death_within_a_cycle_escalates_the_next_bench():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )

    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 180.0
    now[0] = 180.0
    assert circuit.allow_request() is True  # half-open probe
    circuit.record_serve_failure()  # the probe died serving too
    now[0] = 180.0 + 180.0
    assert circuit.allow_request() is False  # 360s window not elapsed
    now[0] = 180.0 + 360.0
    assert circuit.allow_request() is True
    circuit.record_serve_failure()
    now[0] += 360.0
    assert circuit.allow_request() is False
    now[0] += 720.0
    assert circuit.allow_request() is True


def test_the_ladder_climbs_but_never_past_the_cap():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )

    for expected_rung in (60.0, 120.0, 240.0, 480.0, 480.0, 480.0):
        circuit.record_serve_failure()
        assert circuit.serve_error_bench_seconds == expected_rung
        now[0] += expected_rung
        assert circuit.allow_request() is True


def test_a_full_close_resets_the_ladder_to_baseline():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )

    circuit.record_serve_failure()
    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 120.0

    now[0] = 120.0
    assert circuit.allow_request() is True
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'

    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 60.0, 'a genuine recovery resets the ladder'


def test_grace_only_probe_successes_never_close_a_serve_bench():
    """The regression: the connect-time record_success that re-closed the
    breaker onto a failing provider every cycle."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )

    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request() is True

    for _ in range(50):
        circuit.record_success()
        assert circuit.state == 'half_open'
        assert circuit.allow_request() is True

    assert circuit.state != 'closed'


def test_serving_successes_close_the_bench():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )

    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request() is True
    circuit.record_success(serving=True)
    circuit.record_success(serving=True)
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'


def test_connect_time_benches_keep_closing_on_the_first_success():
    """A bench the connect path raised was never raised by a serve death, so
    its recovery contract is unchanged."""
    clock = Clock()
    circuit = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30.0, clock=clock)
    circuit.record_failure()
    clock.now = 30.0
    assert circuit.allow_request() is True
    circuit.record_success()
    assert circuit.state == 'closed'


def test_account_cooldown_still_overrides_the_serve_ladder():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
    )
    circuit.record_account_failure(1800)
    assert circuit.cooldown_elapsed() is False
    now[0] = 1799.0
    assert circuit.allow_request(force=True) is False
    now[0] = 1800.0
    assert circuit.allow_request(force=True) is True


def test_a_new_serve_death_resets_the_window_clock_and_escalates():
    """Re-arming on every death is pre-existing behavior this pins — a probe
    dying at second 100 of a 180s window must not admit the next session at
    second 180 measured from the ORIGINAL death. The escalation is what makes
    that re-arm sanitary: the replacement window is longer, not the same."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 100.0
    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 360.0
    now[0] = 270.0
    assert circuit.allow_request() is False
    now[0] = 460.0
    assert circuit.allow_request() is True


def test_open_provider_selection_circuit_logs_the_bench_seconds(caplog):
    import logging

    from utils.stt.streaming import open_provider_selection_circuit

    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: 0.0,
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )

    with (
        caplog.at_level(logging.WARNING, logger='utils.stt.streaming'),
        patch.object(streaming, '_modulate_circuit', circuit),
    ):
        assert open_provider_selection_circuit('modulate', reason='modulate_serve_error') is True
        assert circuit.serve_error_bench_seconds == 180.0
    bench_lines = [r for r in caplog.records if 'bench_seconds=180.0' in r.message]
    assert bench_lines, 'the record must expose the window just armed'


# ---------------------------------------------------------------------------
# The real socket: serving evidence fires exactly on transcript or done.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transcript_frame_is_serving_evidence():
    sock = await _drive_socket_in_loop([{'type': 'utterance', 'text': 'hello there'}])
    assert sock._serving_observed is True


def test_the_done_frame_is_serving_evidence():
    sock = _drive_socket([{'type': 'done', 'duration_ms': 4000}])
    assert sock._serving_observed is True


def test_error_and_partial_frames_are_not_serving_evidence():
    sock = _drive_socket([{'type': 'partial_utterance', 'partial_utterance': {'text': 'hel'}}])
    assert sock._serving_observed is False
    sock = _drive_socket([{'type': 'error', 'error': SERVE_ERROR_MESSAGE}])
    assert sock._serving_observed is False
    assert sock.typed_death_reason == 'modulate_serve_error'


@pytest.mark.asyncio
async def test_the_serving_callback_fires_exactly_once_across_many_utterances():
    calls = []
    frames = [
        {'type': 'utterance', 'text': 'one'},
        {'type': 'utterance', 'text': 'two'},
        {'type': 'done', 'duration_ms': 2000},
    ]
    ws = FakeWebSocket(frames)
    sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
    sock.set_health_callbacks(lambda: calls.append(1), lambda: None)
    await asyncio.sleep(0.05)
    assert calls == [1]


@pytest.mark.asyncio
async def test_a_throwing_health_callback_never_breaks_the_recv_loop():
    frames = [
        {'type': 'utterance', 'text': 'hello'},
        {'type': 'done', 'duration_ms': 1000},
    ]
    ws = FakeWebSocket(frames)
    segments = []
    sock = SafeModulateSocket(ws, segments.append, asyncio.get_running_loop())

    def explode():
        raise RuntimeError('callback bookkeeping must not kill the stream')

    sock.set_health_callbacks(explode, lambda: None)
    await asyncio.sleep(0.05)
    assert len(segments) == 1
    assert sock._serving_observed is True


@pytest.mark.asyncio
async def test_serving_evidence_survives_socket_teardown():
    """The observation latches on the socket: a session that served and is
    finished (or torn down by failover) has already fed its evidence."""
    calls = []
    frames = [
        {'type': 'utterance', 'text': 'words'},
        {'type': 'done', 'duration_ms': 500},
    ]
    ws = FakeWebSocket(frames)
    sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
    sock.set_health_callbacks(lambda: calls.append(1), lambda: None)
    await asyncio.sleep(0.05)
    sock.finish()
    assert calls == [1]


# ---------------------------------------------------------------------------
# Storm-replay pacing: the breaker history under one outage, replayed.
# ---------------------------------------------------------------------------


def test_a_five_hour_outage_replays_with_escalating_not_flat_exposure():
    """Replay of the 2026-09-22 shape: reconnecting sessions retry every
    second, every admitted probe dies serving (the seam re-arms), the
    operator never intervenes. Pre-fix the flat 180s bench re-admitted at
    probe pace forever (~100 admissions in 5h); post-fix the windows
    escalate to the 1440s cap (~13 admissions in 5h)."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )

    admissions = 0
    while now[0] < 5 * 3600.0 and admissions < 500:
        if circuit.allow_request():
            admissions += 1
            # This probe dies serving exactly when it is admitted:
            circuit.record_serve_failure()
            assert circuit.state == 'open'
        else:
            now[0] += 1.0  # the next reconnecting session, one second later

    assert admissions <= 15, f'an outage must shed admission windows, got {admissions}'


def test_flat_bench_baseline_is_preserved_for_a_single_death():
    """One serve death behaves exactly as the 2026-08-31 fix shipped it."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()
    now[0] = 179.9
    assert circuit.allow_request() is False
    now[0] = 180.0
    assert circuit.allow_request() is True


def test_mixed_connect_failures_do_not_falsely_escalate_the_serve_ladder():
    """Connect-time failures never touch the serve ladder (their threshold
    path is unchanged); only serve deaths climb it."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_failure()
    circuit.record_failure()
    assert circuit.serve_error_bench_seconds == 60.0
    assert circuit.state == 'open'  # connect-time open, 30s window
    now[0] = 30.0
    assert circuit.allow_request() is True


def test_serving_success_then_grace_successes_order_independent():
    """Evidence order within the same half-open window does not lose count:
    every consecutive serving success counts, grace-only ones are ignored."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=2,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    circuit.record_success()
    assert circuit.state == 'half_open'
    circuit.record_success(serving=True)
    circuit.record_success()
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'


def test_probe_replaced_by_serve_death_between_successes_keeps_climbing():
    """Interleaved deaths and successes: each death re-arms at a longer rung
    (admission stays paced) while each serving success keeps its count."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=2,
    )
    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 60.0
    now[0] = 60.0
    assert circuit.allow_request() is True
    circuit.record_success(serving=True)
    circuit.record_serve_failure()
    assert circuit.serve_error_bench_seconds == 120.0
    now[0] = 180.0
    assert circuit.allow_request() is True
    circuit.record_success(serving=True)
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'


def test_a_probe_dying_within_the_grace_still_rearms_through_the_seam():
    """A probe killed inside the liveness grace never reaches the attach seam;
    the connect path's typed-death handling re-arms the bench instead — and
    at the next rung, since the seam had already escalated once."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()  # outage opens
    circuit.record_serve_failure()  # the first probe died serving too → 360s
    assert circuit.serve_error_bench_seconds == 360.0

    async def connect_and_die_within_grace():
        # Error frame delivered fast: the grace observes the death, the
        # connect path records the failure and walks the chain.
        return await _drive_socket_in_loop([{'type': 'error', 'error': SERVE_ERROR_MESSAGE}], wait=0.05)

    async def scenario():
        with (
            patch.object(streaming, '_modulate_circuit', circuit),
            patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0.5),
            patch.object(streaming, 'record_fallback', lambda **_kw: None),
        ):
            with pytest.raises(Exception, match='fallback|socket'):
                await streaming.connect_stt_socket_with_fallback(
                    primary_service=STTService.modulate,
                    connect_primary=connect_and_die_within_grace,
                    connect_deepgram=AsyncMock(return_value=None),
                    connect_parakeet=AsyncMock(return_value=None),
                )

    asyncio.run(scenario())
    # The grace death went through record_failure (connect-path answer), so
    # the half-open probe failure re-arms WITHOUT doubling, at the 360s rung.
    assert circuit.state == 'open'
    assert circuit.serve_error_bench_seconds == 360.0


def test_generation_guard_still_protects_in_flight_probe_bookkeeping():
    """A deferred batch adapter's probe must not credit a newer admission."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    on_success, _on_close = circuit.deferred_result_callbacks()
    circuit.record_serve_failure()  # the admission's generation is gone
    on_success()
    assert circuit.state == 'open', 'a stale probe must not settle a newer bench'


def test_the_client_preflight_mirrors_the_escalated_window():
    """``/v3/speech-profile/stt-availability`` answers through
    ``is_stt_available`` → ``cooldown_elapsed``: mid-window it reports the
    primary down (the client shows its upfront dialog instead of a dead
    recorder), and the moment the (escalated) window lapses it flips true so
    the provider stays reachable and the UI unblocks."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    with patch.object(streaming, '_modulate_circuit', circuit):
        assert streaming.is_stt_available() is True
        circuit.record_serve_failure()
        assert streaming.is_stt_available() is False, 'mid-window the pre-flight must report the outage'
        now[0] = 180.0
        assert streaming.is_stt_available() is True, 'an elapsed window must not strand the pre-flight'


# ---------------------------------------------------------------------------
# Admission pacing: half-open stays a one-probe gate while the bench stands.
# ---------------------------------------------------------------------------


def test_a_single_probe_slot_is_preserved_while_the_bench_is_half_open():
    """Concurrent admission attempts during recovery must stay paced to ONE
    probe — the storm's re-admission pressure must not stampede the gate."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request() is True
    assert circuit.allow_request() is False
    assert circuit.allow_request() is False
    circuit.record_success()  # grace-only: probe slot released, still half-open
    assert circuit.allow_request() is True, 'a settled grace-only probe frees the slot'


def test_escalated_window_is_reflected_in_cooldown_elapsed():
    """``cooldown_elapsed`` (the read-only pre-flight) must honor the armed
    rung, not the baseline, or readiness flaps open mid-window."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    circuit.record_serve_failure()  # escalated to 360s
    now[0] = 180.0
    assert circuit.cooldown_elapsed() is False
    now[0] = 360.0
    assert circuit.cooldown_elapsed() is True


def test_max_probes_is_ignored_for_serve_benches_via_the_account_shape_only():
    """Account benches hard-pin one probe; serve benches keep the caller's
    max_probes (the chain passes STT_CIRCUIT_HALF_OPEN_PROBES there)."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_account_failure(1800)
    now[0] = 1800.0
    assert circuit.allow_request(max_probes=4) is True
    assert circuit.allow_request(max_probes=4) is False


def test_release_probe_frees_the_slot_without_settling():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request() is True
    circuit.release_probe()
    assert circuit.allow_request() is True


def test_half_open_failure_during_a_serve_bench_rearms_at_the_current_rung():
    """A half-open probe that fails on the CONNECT path (record_failure) must
    re-open without climbing the serve ladder — the provider answered this
    probe at connect time, not by dying mid-serve."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    circuit.record_failure()  # connect-path failure of the half-open probe
    assert circuit.state == 'open'
    assert circuit.serve_error_bench_seconds == 60.0, 'connect failures do not escalate the serve ladder'
    now[0] = 120.0
    assert circuit.allow_request() is True, 're-armed at the CURRENT rung, not doubled'


def test_serving_success_after_bench_close_is_a_plain_success():
    """Once closed, serving evidence must not re-open or wedge anything."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'
    circuit.record_success(serving=True)
    assert circuit.state == 'closed'


# ---------------------------------------------------------------------------
# Chain-mode adapters under a serve bench.
# ---------------------------------------------------------------------------


def test_deferred_result_callbacks_count_as_serving_evidence():
    """The configured chain's batch adapter proves health on the first POST —
    that IS serving evidence, so it closes a serve bench."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    on_success, _on_close = circuit.deferred_result_callbacks()
    on_success()
    assert circuit.state == 'closed'


def test_deferred_close_releases_the_serve_probe_slot_without_failure():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    _on_success, on_close = circuit.deferred_result_callbacks()
    on_close()
    assert circuit.state == 'half_open', 'a probe close is not evidence either way; the bench stands'
    assert circuit.allow_request() is True, 'the slot was released for a fresh probe'


def test_replacement_callbacks_settle_serving_evidence_once():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    on_serving, _on_released = circuit.replacement_callbacks(serving=True)
    on_serving()
    on_serving()  # idempotent
    assert circuit.state == 'closed'


def test_replacement_callbacks_from_a_stale_generation_are_ignored():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    on_serving, _on_released = circuit.replacement_callbacks(serving=True)
    circuit.record_serve_failure()  # bench re-armed after this admission
    on_serving()
    assert circuit.state == 'open', 'a superseded admission must not settle the newer bench'


def test_serving_false_replacement_callback_never_closes_a_serve_bench():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=60.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 60.0
    assert circuit.allow_request() is True
    on_serving, _on_released = circuit.replacement_callbacks(serving=False)
    on_serving()
    assert circuit.state == 'half_open'


# ---------------------------------------------------------------------------
# Per-provider ladders: fresh breakers climb from their own baseline.
# ---------------------------------------------------------------------------


def test_each_provider_circuit_carries_its_own_ladder():
    """A Modulate outage must never pre-escalate the Deepgram or Parakeet
    bench: the ladder is per breaker instance, never process-global."""
    now = [0.0]
    modulate = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    deepgram = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    modulate.record_serve_failure()
    modulate.record_serve_failure()
    modulate.record_serve_failure()
    assert modulate.serve_error_bench_seconds == 720.0
    assert deepgram.serve_error_bench_seconds == 180.0
    assert deepgram.state == 'closed'


def test_default_serve_error_baseline_is_180s():
    """The singleton construction path (no explicit serve cooldown) keeps the
    2026-08-31 baseline rung."""
    circuit = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    assert circuit.serve_error_bench_seconds == 180.0


def test_expected_rejection_during_a_serve_bench_releases_the_slot():
    """A capacity_full answer on a half-open probe is the provider answering,
    not evidence of serve health: the slot is released, the bench stands."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request() is True
    circuit.record_rejection('capacity_full')
    assert circuit.state == 'half_open'
    assert circuit.allow_request() is True


def test_force_probe_is_available_on_a_serve_bench_for_the_last_resort():
    """The chain's last-resort force must still be able to claim the probe on
    an elapsed serve bench (force bypasses cooldown, never account state)."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=1,
    )
    circuit.record_serve_failure()
    now[0] = 180.0
    assert circuit.allow_request(force=True) is True
    assert circuit.allow_request(force=True) is False, 'one probe at a time, even forced'


# ---------------------------------------------------------------------------
# End to end: the storm cycle through the REAL legacy connect path.
# ---------------------------------------------------------------------------


async def _admit_probe(circuit, *, connect_primary, grace: float = 0.02):
    with (
        patch.object(streaming, '_modulate_circuit', circuit),
        patch.object(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', grace),
    ):
        return await connect_stt_socket_with_fallback(
            primary_service=STTService.modulate,
            connect_primary=connect_primary,
            connect_deepgram=AsyncMock(return_value=None),
            connect_parakeet=AsyncMock(return_value=None),
        )


@pytest.mark.asyncio
async def test_grace_passing_probes_never_reopen_full_admission():
    """RED on the pre-fix code: the grace-passing probe's record_success
    re-closed the breaker, so unlimited later sessions hit the PRIMARY again.
    Post-fix the breaker stays half-open — admissions stay paced to the probe
    slot — until real serving evidence (or another serve death) lands."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()

    calls = []

    async def connect_primary():
        calls.append('primary')
        # Held past the grace so the probe survives connect; its stream then
        # ends without a done frame (the clean-close latch latches dead, as a
        # doomed-but-not-yet-dead stream does in prod until the fault lands).
        return await _drive_socket_in_loop([{'type': 'done', 'duration_ms': 1000}], delay=0.3, wait=0.02)

    now[0] = 180.0
    _socket, service = await _admit_probe(circuit, connect_primary=connect_primary)
    assert service is STTService.modulate

    # A grace-only probe later, the breaker is still holding the gate shut:
    assert circuit.state == 'half_open'
    now[0] = 360.0
    _socket2, service2 = await _admit_probe(circuit, connect_primary=connect_primary)
    assert service2 is STTService.modulate  # half-open probes continue
    assert circuit.state == 'half_open', 'grace-only successes must never close the bench'


@pytest.mark.asyncio
async def test_a_probe_death_through_the_seam_escalates_and_slams_the_gate():
    """The probe died serving (as every doomed probe does): the death seam
    re-arms the bench at the escalated rung, measured from the death."""
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()

    async def connect_primary():
        # Held past the grace so the probe survives connect while still doomed.
        return await _drive_socket_in_loop([], delay=10.0, wait=0.02)

    now[0] = 180.0
    await _admit_probe(circuit, connect_primary=connect_primary)
    assert circuit.state == 'half_open'

    # The failover seam observes the probe's death (the record re-arms the
    # window and escalates it); admission stays shut for the doubled window.
    with patch.object(streaming, '_modulate_circuit', circuit):
        from utils.stt.streaming import open_provider_selection_circuit

        assert open_provider_selection_circuit('modulate', reason='modulate_serve_error') is True
    assert circuit.serve_error_bench_seconds == 360.0
    now[0] = 360.0
    assert circuit.allow_request() is False, 'the escalated window runs from the death'
    now[0] = 540.0
    assert circuit.allow_request() is True


@pytest.mark.asyncio
async def test_recovery_adopts_on_serving_probes_and_resets_the_ladder():
    now = [0.0]
    circuit = ProviderCircuitBreaker(
        failure_threshold=3,
        cooldown_seconds=30.0,
        clock=lambda: now[0],
        serve_error_cooldown_seconds=180.0,
        serve_error_successes_to_close=3,
    )
    circuit.record_serve_failure()

    async def connect_primary():
        # The wait happens BEFORE returning (as a real connect's handshake
        # would); the utterance delay runs from socket construction and lands
        # AFTER the connect seam has attached the evidence callback (attach is
        # synchronous with connect resolution in prod, so no frame can fire
        # into the noop there). The tail keeps the generator open so the
        # liveness grace samples a stream that is still alive.
        async def connect():
            ws = FakeWebSocket([{'type': 'utterance', 'text': 'recovered'}], delay=0.35, tail=5.0)
            sock = SafeModulateSocket(ws, lambda _segments: None, asyncio.get_running_loop())
            await asyncio.sleep(0.15)
            return sock

        return await connect()

    async def admit_and_settle():
        """Admit, then give the probe's transcript time to land (0.35s)."""
        result = await _admit_probe(circuit, connect_primary=connect_primary)
        await asyncio.sleep(0.3)
        return result

    now[0] = 180.0
    _socket, service = await admit_and_settle()
    assert service is STTService.modulate

    # Each serving probe contributes one consecutive evidence success; the
    # third closes the breaker and resets the ladder for the next outage.
    await admit_and_settle()
    assert circuit.state == 'half_open'
    await admit_and_settle()
    assert circuit.state == 'closed'
    assert circuit.serve_error_bench_seconds == 180.0
