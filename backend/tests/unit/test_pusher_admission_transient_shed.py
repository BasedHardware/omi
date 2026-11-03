"""Pod-start availability blips no longer fail pusher sessions at admission.

Failure-Class: FC-cold-channel-availability-blip-classified-as-failed-session-admission
— instance in backend/routers/pusher.py (pusher 2026-10-31: bursts of uvicorn
``Exception in ASGI application`` tracebacks inside ~60s of pod starts). The
pusher websocket session-admission profile reads (webhook delay, audio-apps
count, private-cloud flag, protection level) are a session's FIRST
Firestore/Redis round trips: a pod that just started reaches them before any
gRPC channel is warm, and a momentarily unavailable data plane answers with
the same availability trio every Firestore boundary in this codebase already
classifies as transient (503 ``ServiceUnavailable``, 504 ``DeadlineExceeded``,
500 ``InternalServerError``, plus the drained-gapic-retry envelope carrying
one of those as its cause). The admission boundary had no transient arm at
all — one blip walked straight into ``except Exception``: journey outcome
``failure``, close 1011, one full uvicorn traceback per dropped session,
while the read had committed nothing.

The fix is the bounded transient shed: each admission read is re-asked (a
strictly faithful retry — admission reads commit nothing) up to
``PUSHER_ADMISSION_TRANSIENT_ATTEMPTS`` times with a short doubling backoff;
a drained shed ends the never-started session cleanly (journey ``cancelled``,
close 1013 Try Again Later, ``pusher_admission_shed_exhausted_total``)
instead of a fault classification and a stack trace. The client's own
reconnect cadence owns the recovery — the same retryable-refusal contract
the listen side's admission fences already speak through ``run_critical_ws``
(transient admission faults close 1013 there), asserted here as a parity
contract so the two ends of the lane cannot drift apart.

Contract under test:

- every availability-trio member — and the drained-retry envelope carrying
  one as its cause — is retried in place and a read that recovers admits the
  session exactly as a healthy read would;
- a drained budget raises ``_AdmissionTransientExhausted`` naming the read
  and chaining the last transient; the handler ends the session with close
  1013 and journey ``cancelled`` — never a failure, never a traceback;
- the shed counts every retry and every exhaustion by read name on
  ``pusher_admission_shed_retries_total`` /
  ``pusher_admission_shed_exhausted_total``;
- permanent refusals (``PermissionDenied`` and friends), quota pressure
  (``TooManyRequests``), unknown failures and cause-less/permanent-cause
  retry envelopes keep the loud first-attempt arm: journey ``failure``, the
  exception escapes the ASGI app exactly as before, shed counters untouched;
- a cancel is never absorbed by the shed: a cancel while serving propagates
  through the shed and the admission boundary untouched, a cancel inside the
  backoff sleep propagates, and a cancel observed during pod drain still
  routes to the existing teardown-absorb boundary (close 1006);
- close 1013 is its own close class ``refused`` in
  ``utils/listen_pusher_session.py`` — distinct from the pinned
  ``restart`` singleton {1012} — logging at INFO with dedupe, because a
  refused session carried no audio and the refusal is the recovery plan;
- ``pusher_session_outcome`` keeps 1013 in the interrupted-session meaning
  (``cancelled``) while a real application failure still wins;
- all four admission reads ride the shed, the conditional protection-level
  read included, and the loud/teardown/refusal arm ordering of the admission
  ``try`` is pinned (cancel first, refusal second, generic Exception last).
"""

import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import (
    DeadlineExceeded,
    FailedPrecondition,
    InternalServerError,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import utils.pusher_protocol as pusher_protocol
from utils.listen_pusher_session import (
    PUSHER_CLOSE_CLASS_ABNORMAL,
    PUSHER_CLOSE_CLASS_CLEAN,
    PUSHER_CLOSE_CLASS_KEEPALIVE,
    PUSHER_CLOSE_CLASS_REFUSED,
    PUSHER_CLOSE_CLASS_RESTART,
    PUSHER_EXPECTED_RESTART_CLOSE_CODES,
    classify_pusher_close,
    log_pusher_connection_closed,
)
from utils.pusher_protocol import pusher_session_outcome

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

AVAILABILITY_TRIO = (ServiceUnavailable('x'), DeadlineExceeded('x'), InternalServerError('x'))
PERMANENT_REFUSALS = (
    PermissionDenied('denied'),
    FailedPrecondition('precondition'),
    InvalidArgument('bad'),
    NotFound('gone'),
)


class FakeWebSocket:
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None
        self.close_calls = []

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_calls.append(code)
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        # A session that reached supervision ends like a client drop: the
        # receive task ends (cancelled shape) and the supervisor exits.
        raise asyncio.CancelledError


class _GateStub:
    """Mutable stub over the gate seam the admission boundary reads."""

    def __init__(self):
        self.serving = True
        self.drain_age = None
        self._waiters = []

    def flip_to_draining(self, drain_age=2.0):
        self.serving = False
        self.drain_age = drain_age
        for event in self._waiters:
            event.set()

    def is_serving(self):
        return self.serving

    def drain_age_seconds(self):
        return self.drain_age

    def drain_wait_event(self):
        event = asyncio.Event()
        if not self.serving:
            event.set()
        else:
            self._waiters.append(event)
        return event

    def remove_drain_wait_event(self, event):
        try:
            self._waiters.remove(event)
        except ValueError:
            pass


def _set_gate(monkeypatch) -> _GateStub:
    stub = _GateStub()
    monkeypatch.setattr(pusher, 'ReadinessGate', stub)
    return stub


def _sync_run_blocking(monkeypatch):
    """Pass-through run_blocking: the read runs inline, no event-loop sleep.

    Awaiting the stub is itself a task yield (real ``run_blocking`` yields in
    ``run_in_executor``), so the shed's loop and its backoff sleeps stay fully
    observable without wall-clock delays.
    """

    async def _run_blocking(pool, fn, *args):
        return fn(*args)

    monkeypatch.setattr(pusher, 'run_blocking', _run_blocking)


def _read_that_always_raises(error, name='read'):
    def read(*args):
        raise error

    read.__name__ = name
    return read


def _supervise_that_raises(gate):
    """A supervise whose receive task crashes immediately: the session crosses
    admission (profile reads done, gauge acquired) and then dies loudly —
    proving the shed admitted it, with no supervision internals exercised."""

    async def _supervise(**kwargs):
        assert gate.is_serving(), 'the admit-path proof needs the pod serving (no teardown absorb)'
        raise RuntimeError('receive loop exploded after admission')

    return _supervise


def _read_that_raises_then(error, name='read'):
    state = {'raised': False}

    def read(*args):
        if not state['raised']:
            state['raised'] = True
            raise error
        return 'ok'

    read.__name__ = name
    return read


def _journey_factory():
    attempts = []

    def factory(name):
        attempt = MagicMock()
        attempt.name = name
        attempts.append(attempt)
        return attempt

    factory.attempts = attempts
    return factory


@pytest.fixture
def runtime(monkeypatch):
    """Full-handler harness: healthy profile reads, counters and journeys stubbed."""
    gate = _set_gate(monkeypatch)
    _sync_run_blocking(monkeypatch)
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPS', MagicMock())
    monkeypatch.setattr(pusher_protocol, 'PUSHER_QUEUE_DROPPED_BYTES', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_RETRIES_TOTAL', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL', MagicMock())
    return gate


class TestShedRetryContract:
    """The shed helper alone: what sheds, what stays loud, how it paces."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('error', AVAILABILITY_TRIO)
    async def test_trio_member_is_retried_until_success(self, monkeypatch, error):
        _sync_run_blocking(monkeypatch)
        read = _read_that_raises_then(error, name='get_audio_bytes_webhook_seconds')

        assert await pusher._admission_read_with_transient_shed(object(), read, 'uid') == 'ok'

    @pytest.mark.asyncio
    async def test_drained_budget_raises_exhaustion_after_all_attempts(self, monkeypatch):
        _sync_run_blocking(monkeypatch)
        attempts = []

        def read(*args):
            attempts.append(1)
            raise ServiceUnavailable('x')

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert len(attempts) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS

    @pytest.mark.asyncio
    async def test_exhaustion_names_the_read_and_chains_last_transient(self, monkeypatch):
        _sync_run_blocking(monkeypatch)

        def get_user_private_cloud_sync_enabled(*args):
            raise DeadlineExceeded('x')

        with pytest.raises(pusher._AdmissionTransientExhausted) as info:
            await pusher._admission_read_with_transient_shed(object(), get_user_private_cloud_sync_enabled, 'uid')
        assert info.value.read == 'get_user_private_cloud_sync_enabled'
        assert isinstance(info.value.__cause__, DeadlineExceeded)

    @pytest.mark.asyncio
    async def test_drained_retry_envelope_sheds(self, monkeypatch):
        """The SDK's drained-retry envelope carrying a trio member is the same
        transient one layer up — the shed reads the cause, like every
        Firestore boundary that already retries this set."""
        _sync_run_blocking(monkeypatch)
        envelope = RetryError('retry budget drained', ServiceUnavailable('x'))
        calls = []

        def read(*args):
            calls.append(1)
            raise envelope

        with pytest.raises(pusher._AdmissionTransientExhausted) as info:
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert len(calls) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS
        assert info.value.__cause__ is envelope

    @pytest.mark.asyncio
    async def test_causeless_retry_envelope_is_loud(self, monkeypatch):
        """A cause-less RetryError carries no transient evidence — the shared
        classifier keeps it loud and the shed never retries it."""
        _sync_run_blocking(monkeypatch)
        calls = []

        def read(*args):
            calls.append(1)
            raise RetryError('no cause recorded', None)

        with pytest.raises(RetryError):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert calls == [1]  # first attempt, no shed

    @pytest.mark.asyncio
    async def test_permanent_refusal_envelope_is_loud(self, monkeypatch):
        """A drained envelope whose cause is a permanent refusal stays loud
        verbatim: the envelope is re-raised unwrapped-by-nothing — the
        classifier refused it and the shed never retried it."""
        _sync_run_blocking(monkeypatch)
        calls = []

        def read(*args):
            calls.append(1)
            raise RetryError('drained', PermissionDenied('denied'))

        with pytest.raises(RetryError):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_backoff_schedule_is_doubling_from_the_declared_base(self, monkeypatch):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)
        _sync_run_blocking(monkeypatch)

        def read(*args):
            raise ServiceUnavailable('x')

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')

        assert len(sleeps) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS - 1
        assert sleeps[0] == pusher.PUSHER_ADMISSION_TRANSIENT_BACKOFF_SECONDS
        assert sleeps[1] == sleeps[0] * 2

    @pytest.mark.asyncio
    async def test_shed_never_sleeps_after_the_last_attempt(self, monkeypatch):
        """The budget is attempts, not sleeps: a drain ends the moment the
        last attempt fails, with no trailing backoff before the refusal."""
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)
        _sync_run_blocking(monkeypatch)

        def read(*args):
            raise DeadlineExceeded('x')

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert len(sleeps) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS - 1

    @pytest.mark.asyncio
    async def test_first_attempt_success_never_backs_off(self, monkeypatch):
        async def fake_sleep(seconds):
            raise AssertionError('a healthy read must not back off')

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)
        _sync_run_blocking(monkeypatch)

        def read(*args):
            return 'ok'

        assert await pusher._admission_read_with_transient_shed(object(), read, 'uid') == 'ok'

    @pytest.mark.asyncio
    async def test_retry_counter_increments_per_blip_not_per_attempt(self, monkeypatch):
        _sync_run_blocking(monkeypatch)
        retries = MagicMock()
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_RETRIES_TOTAL', retries)
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL', MagicMock())
        read = _read_that_raises_then(ServiceUnavailable('x'))

        await pusher._admission_read_with_transient_shed(object(), read, 'uid')

        retries.labels.return_value.inc.assert_called_once_with()
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_exhaustion_counter_increments_exactly_once(self, monkeypatch):
        _sync_run_blocking(monkeypatch)
        exhausted = MagicMock()
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_RETRIES_TOTAL', MagicMock())
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL', exhausted)

        def read(*args):
            raise ServiceUnavailable('x')

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        exhausted.labels.return_value.inc.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_counters_are_labelled_by_read_name(self, monkeypatch):
        _sync_run_blocking(monkeypatch)
        retries = MagicMock()
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_RETRIES_TOTAL', retries)
        read = _read_that_raises_then(InternalServerError('x'), name='get_audio_bytes_webhook_seconds')

        await pusher._admission_read_with_transient_shed(object(), read, 'uid')

        retries.labels.assert_called_once_with(read='get_audio_bytes_webhook_seconds')

    @pytest.mark.asyncio
    async def test_pool_identity_is_preserved_on_every_retry(self, monkeypatch):
        """Every re-ask goes back through run_blocking with the pool the
        handler passed — the shed never pulls a Firestore read onto the
        event loop (backend AGENTS.md blocking-work rule)."""
        pools = []
        marker = object()

        async def fake_run_blocking(pool, fn, *args):
            pools.append(pool)
            raise ServiceUnavailable('x')

        monkeypatch.setattr(pusher, 'run_blocking', fake_run_blocking)
        monkeypatch.setattr(pusher.asyncio, 'sleep', async_noop := _make_noop_sleep())

        def read(*args):
            return 'ok'

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(marker, read, 'uid')
        assert len(pools) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS
        assert all(p is marker for p in pools)

    @pytest.mark.asyncio
    async def test_nameless_callable_gets_the_generic_read_label(self, monkeypatch):
        """A read without a ``__name__`` (functools.partial, callable object)
        must still shed and count under the generic label, not crash the
        admission path."""
        _sync_run_blocking(monkeypatch)
        retries = MagicMock()
        monkeypatch.setattr(pusher, 'PUSHER_ADMISSION_SHED_RETRIES_TOTAL', retries)

        class _NamelessRead:
            def __call__(self, *args):
                raise ServiceUnavailable('x')

        nameless = _NamelessRead()

        with pytest.raises(pusher._AdmissionTransientExhausted) as info:
            await pusher._admission_read_with_transient_shed(object(), nameless, 'uid')
        assert info.value.read == 'admission_read'
        retries.labels.assert_called_with(read='admission_read')

    @pytest.mark.asyncio
    async def test_envelope_blip_then_success_admits(self, monkeypatch):
        """A drained-retry envelope on attempt one, a healthy answer on
        attempt two: the envelope member of the shed vocabulary recovers the
        same way a bare trio member does."""
        _sync_run_blocking(monkeypatch)
        state = {'n': 0}

        def read(*args):
            state['n'] += 1
            if state['n'] == 1:
                raise RetryError('pod-start gapic retry drained', ServiceUnavailable('x'))
            return 'ok'

        assert await pusher._admission_read_with_transient_shed(object(), read, 'uid') == 'ok'
        assert state['n'] == 2

    @pytest.mark.asyncio
    async def test_success_on_the_last_budget_attempt_still_admits(self, monkeypatch):
        """The budget is inclusive: a read that answers on exactly the last
        allowed attempt admits, never refuses."""
        _sync_run_blocking(monkeypatch)
        state = {'n': 0}

        async def fake_sleep(seconds):
            return None

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)

        def read(*args):
            state['n'] += 1
            if state['n'] < pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS:
                raise ServiceUnavailable('x')
            return 'ok'

        assert await pusher._admission_read_with_transient_shed(object(), read, 'uid') == 'ok'
        assert state['n'] == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS

    @pytest.mark.asyncio
    async def test_two_blips_then_success_stays_within_budget(self, monkeypatch):
        _sync_run_blocking(monkeypatch)
        state = {'n': 0}

        def read(*args):
            state['n'] += 1
            if state['n'] < 3:
                raise DeadlineExceeded('x')
            return 'ok'

        assert await pusher._admission_read_with_transient_shed(object(), read, 'uid') == 'ok'
        assert state['n'] == 3

    @pytest.mark.asyncio
    async def test_concurrent_shed_reads_have_independent_budgets(self, monkeypatch):
        """Two admission reads failing at once each get their own budget: the
        shed carries no global counter that one noisy read could drain for
        its siblings (per-call state, never module-level)."""
        monkeypatch.setattr(pusher.asyncio, 'sleep', _make_noop_sleep())

        async def slow_run_blocking(pool, fn, *args):
            await asyncio.sleep(0)
            raise ServiceUnavailable('x')

        monkeypatch.setattr(pusher, 'run_blocking', slow_run_blocking)

        async def one_read(name):
            def read(*args):
                raise ServiceUnavailable('x')

            read.__name__ = name
            with pytest.raises(pusher._AdmissionTransientExhausted) as info:
                await pusher._admission_read_with_transient_shed(object(), read, 'uid')
            return info.value.read

        reads = await asyncio.gather(one_read('read_a'), one_read('read_b'))
        assert sorted(reads) == ['read_a', 'read_b']


class TestAdmissionBoundaryLoudness:
    """Permanent refusals and unknown failures keep the loud first-attempt arm."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('error', [*PERMANENT_REFUSALS, TooManyRequests('quota'), RuntimeError('unknown failure')])
    async def test_loud_failure_propagates_on_first_attempt(self, runtime, monkeypatch, error):
        calls = []

        def read(*args):
            calls.append(1)
            raise error

        monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', read)
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        websocket = FakeWebSocket()
        with pytest.raises(type(error)):
            await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert calls == [1]  # exactly one attempt — the shed never absorbed it
        assert websocket.close_calls == []  # re-raise path: no clean close
        journeys.attempts[0].finish.assert_called_once_with('failure')
        pusher.PUSHER_ADMISSION_SHED_RETRIES_TOTAL.labels.assert_not_called()
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_read_that_recovers_admits_session(self, runtime, monkeypatch):
        """One 503 on the first read is a blip: the read is re-asked, the
        session crosses admission (profile reads done, gauge acquired, the
        supervised section's crash classifies 1011) and the shed never
        refuses."""
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_raises_then(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_raises(runtime))

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_code == 1011
        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.inc.assert_called_once_with()
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_series_with_mixed_blips_admits(self, runtime, monkeypatch):
        """Blips scattered across different reads answer the same way: the
        budget is per read, and every recovered read admits its session."""
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_raises_then(DeadlineExceeded('x'), name='get_audio_bytes_webhook_seconds'),
        )
        monkeypatch.setattr(
            pusher,
            'is_audio_bytes_app_enabled',
            _read_that_raises_then(ServiceUnavailable('x'), name='is_audio_bytes_app_enabled'),
        )
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_raises(runtime))

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_code == 1011

    @pytest.mark.asyncio
    async def test_recovered_blip_counts_a_retry_not_a_refusal(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_raises_then(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        pusher.PUSHER_ADMISSION_SHED_RETRIES_TOTAL.labels.assert_called_once_with(
            read='get_audio_bytes_webhook_seconds'
        )
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_recovered_session_records_no_exhaustion(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'is_audio_bytes_app_enabled',
            _read_that_raises_then(ServiceUnavailable('x'), name='is_audio_bytes_app_enabled'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_loud_arm_does_not_touch_shed_counters(self, runtime, monkeypatch):
        def read(*args):
            raise PermissionDenied('denied')

        monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', read)

        websocket = FakeWebSocket()
        with pytest.raises(PermissionDenied):
            await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        pusher.PUSHER_ADMISSION_SHED_RETRIES_TOTAL.labels.assert_not_called()
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_teardown_cancel_records_no_shed_counters(self, runtime, monkeypatch):
        """A cancel absorbed at the admission boundary is platform churn —
        the shed never counted it as a transient."""
        gate = runtime

        async def read(pool, fn, *args):
            gate.flip_to_draining(drain_age=0.5)
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

        monkeypatch.setattr(pusher, 'run_blocking', read)

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_calls == [1006]
        pusher.PUSHER_ADMISSION_SHED_RETRIES_TOTAL.labels.assert_not_called()
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_blip_warning_mentions_the_retry(self, runtime, monkeypatch, caplog):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_raises_then(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        with caplog.at_level(logging.WARNING, logger='routers.pusher'):
            websocket = FakeWebSocket()
            await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        blip_lines = [r for r in caplog.records if 'transient availability blip' in r.getMessage()]
        assert blip_lines, 'a shed retry must be visible at glance level'
        assert blip_lines[0].levelno == logging.WARNING
        assert 'retrying' in blip_lines[0].getMessage()
        assert 'get_audio_bytes_webhook_seconds' in blip_lines[0].getMessage()


class TestAdmissionCleanRefusal:
    """A drained shed ends the never-started session cleanly — never a fault."""

    @pytest.mark.asyncio
    async def test_exhausted_shed_ends_session_with_1013(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)  # absorbed, no escape

        assert websocket.close_calls == [1013]
        assert websocket.close_code == 1013
        journeys.attempts[0].finish.assert_called_once_with('cancelled')

    @pytest.mark.asyncio
    async def test_refusal_is_never_a_journey_failure(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(DeadlineExceeded('x'), name='get_audio_bytes_webhook_seconds'),
        )
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        await pusher._websocket_util_trigger(FakeWebSocket(), 'uid', 8000)

        finish_outcomes = [call.args[0] for call in journeys.attempts[0].finish.call_args_list]
        assert finish_outcomes == ['cancelled']
        assert 'failure' not in finish_outcomes

    @pytest.mark.asyncio
    async def test_exhaustion_counters_attributed_to_failing_read(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_called_with(read='get_audio_bytes_webhook_seconds')
        pusher.PUSHER_ADMISSION_SHED_RETRIES_TOTAL.labels.assert_called_with(read='get_audio_bytes_webhook_seconds')

    @pytest.mark.asyncio
    async def test_exhaustion_on_second_read_refuses_before_the_third(self, runtime, monkeypatch):
        monkeypatch.setattr(
            pusher,
            'is_audio_bytes_app_enabled',
            _read_that_always_raises(InternalServerError('x'), name='is_audio_bytes_app_enabled'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_calls == [1013]

    @pytest.mark.asyncio
    async def test_exhaustion_on_later_read_still_refuses_cleanly(self, runtime, monkeypatch):
        """The private-cloud flag blipping past the budget — after the
        earlier reads answered — is the same clean 1013 ending: every
        admission read carries its own shed."""
        monkeypatch.setattr(
            pusher.users_db,
            'get_user_private_cloud_sync_enabled',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_user_private_cloud_sync_enabled'),
        )
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_calls == [1013]
        journeys.attempts[0].finish.assert_called_once_with('cancelled')
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_called_with(
            read='get_user_private_cloud_sync_enabled'
        )

    @pytest.mark.asyncio
    async def test_fourth_read_beyond_its_budget_leaves_session_intact(self, runtime, monkeypatch):
        """The protection-level read is conditional but not second-class: with
        sync enabled it rides the shed, and a session whose reads answer
        crosses admission normally (supervised crash classifies 1011, no
        refusal)."""
        monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_raises(runtime))

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_code == 1011
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_four_reads_ride_the_shed_in_one_session(self, runtime, monkeypatch):
        """The complete admission surface: exactly the four profile reads are
        re-asked through the shed, nothing else on the admitted path."""
        seen = []

        real_shed = pusher._admission_read_with_transient_shed

        async def recording_shed(pool, fn, *args):
            seen.append(getattr(fn, '__name__', '?'))
            return await real_shed(pool, fn, *args)

        monkeypatch.setattr(pusher, '_admission_read_with_transient_shed', recording_shed)
        monkeypatch.setattr(pusher, 'supervise_tasks', _supervise_that_raises(runtime))

        named_reads = {
            'get_audio_bytes_webhook_seconds': lambda uid: None,
            'is_audio_bytes_app_enabled': lambda uid: False,
            'get_user_private_cloud_sync_enabled': lambda uid: True,
            'get_data_protection_level': lambda uid: 'standard',
        }
        for name, read in named_reads.items():
            read.__name__ = name
            if name == 'get_audio_bytes_webhook_seconds':
                monkeypatch.setattr(pusher, name, read)
            elif name == 'is_audio_bytes_app_enabled':
                monkeypatch.setattr(pusher, name, read)
            else:
                monkeypatch.setattr(pusher.users_db, name, read)

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert seen == [
            'get_audio_bytes_webhook_seconds',
            'is_audio_bytes_app_enabled',
            'get_user_private_cloud_sync_enabled',
            'get_data_protection_level',
        ]

    @pytest.mark.asyncio
    async def test_refusal_gauge_is_never_acquired(self, runtime, monkeypatch):
        """The active-connections gauge is acquired after admission: a refused
        session must not leak a connection slot."""
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.inc.assert_not_called()
        pusher.PUSHER_ACTIVE_WS_CONNECTIONS.dec.assert_not_called()

    @pytest.mark.asyncio
    async def test_refusal_warning_is_attributed_and_not_an_error(self, runtime, monkeypatch, caplog):
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        with caplog.at_level(logging.WARNING, logger='routers.pusher'):
            await pusher._websocket_util_trigger(FakeWebSocket(), 'uid', 8000)

        refusal_lines = [r for r in caplog.records if 'shed exhausted' in r.getMessage()]
        assert refusal_lines, 'the refusal must be logged for attribution'
        assert refusal_lines[0].levelno == logging.WARNING
        assert 'get_audio_bytes_webhook_seconds' in refusal_lines[0].getMessage()
        assert 'ServiceUnavailable' in refusal_lines[0].getMessage()
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    @pytest.mark.asyncio
    async def test_refusal_is_repeatable_per_session(self, runtime, monkeypatch):
        """Two identical cold-pod sessions refuse identically: the refusal is
        a deterministic classification, not ordering luck."""
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(DeadlineExceeded('x'), name='get_audio_bytes_webhook_seconds'),
        )
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        for _ in range(2):
            websocket = FakeWebSocket()
            await pusher._websocket_util_trigger(websocket, 'uid', 8000)
            assert websocket.close_calls == [1013]
        assert journeys.attempts[0].finish.call_args[0][0] == 'cancelled'
        assert journeys.attempts[1].finish.call_args[0][0] == 'cancelled'

    @pytest.mark.asyncio
    async def test_blip_log_names_attempt_fraction_and_backoff(self, runtime, monkeypatch, caplog):
        async def fake_sleep(seconds):
            return None

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        with caplog.at_level(logging.WARNING, logger='routers.pusher'):
            await pusher._websocket_util_trigger(FakeWebSocket(), 'uid', 8000)

        blips = [r for r in caplog.records if 'transient availability blip' in r.getMessage()]
        assert len(blips) == pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS - 1
        assert '1/3' in blips[0].getMessage()
        assert f"{pusher.PUSHER_ADMISSION_TRANSIENT_BACKOFF_SECONDS:.2f}" in blips[0].getMessage()
        assert '2/3' in blips[1].getMessage()

    @pytest.mark.asyncio
    async def test_refusal_log_carries_no_traceback(self, runtime, monkeypatch, caplog):
        """The refusal's whole point: the log line keeps the last fault TYPE
        via the chained cause's name — without the multi-hundred-line uvicorn
        traceback the loud arm produces."""
        monkeypatch.setattr(
            pusher,
            'get_audio_bytes_webhook_seconds',
            _read_that_always_raises(ServiceUnavailable('x'), name='get_audio_bytes_webhook_seconds'),
        )

        with caplog.at_level(logging.WARNING, logger='routers.pusher'):
            await pusher._websocket_util_trigger(FakeWebSocket(), 'uid', 8000)

        refusals = [r for r in caplog.records if 'shed exhausted' in r.getMessage()]
        assert len(refusals) == 1
        assert refusals[0].exc_info is None
        assert 'ServiceUnavailable' in refusals[0].getMessage()
        # The blip warnings stay in the stream, but no line carries a stack.
        assert all(r.exc_info is None for r in caplog.records)

    @pytest.mark.asyncio
    async def test_protection_level_refusal_is_attributed_to_that_read(self, runtime, monkeypatch):
        monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
        monkeypatch.setattr(
            pusher.users_db,
            'get_data_protection_level',
            _read_that_always_raises(DeadlineExceeded('x'), name='get_data_protection_level'),
        )

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_calls == [1013]
        pusher.PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL.labels.assert_called_with(read='get_data_protection_level')


class TestCancelOwnership:
    """The shed never absorbs a cancel — teardown keeps its boundary."""

    @pytest.mark.asyncio
    async def test_cancel_inside_read_propagates_through_shed(self, runtime, monkeypatch):
        """A cancel while serving has no platform owner in this handler; the
        shed must hand it through untouched (journey cancelled, re-raised),
        never absorb it as a retryable blip."""
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        def read(*args):
            raise asyncio.CancelledError()

        monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', read)

        websocket = FakeWebSocket()
        with pytest.raises(asyncio.CancelledError):
            await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        journeys.attempts[0].finish.assert_called_once_with('cancelled')
        assert websocket.close_calls == []

    @pytest.mark.asyncio
    async def test_cancel_inside_shed_backoff_propagates(self, monkeypatch):
        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        monkeypatch.setattr(pusher.asyncio, 'sleep', fake_sleep)
        _sync_run_blocking(monkeypatch)

        def read(*args):
            raise ServiceUnavailable('x')

        with pytest.raises(asyncio.CancelledError):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')

    @pytest.mark.asyncio
    async def test_transient_then_cancel_still_propagates_the_cancel(self, monkeypatch):
        """One shed retry followed by a cancel: the cancel wins — a retry
        budget never converts platform teardown into more retries."""
        _sync_run_blocking(monkeypatch)
        state = {'n': 0}

        def read(*args):
            state['n'] += 1
            if state['n'] == 1:
                raise ServiceUnavailable('x')
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert state['n'] == 2

    @pytest.mark.asyncio
    async def test_teardown_cancel_during_admission_is_still_absorbed(self, runtime, monkeypatch):
        """A cancel observed while the pod is draining is platform churn: the
        existing teardown boundary absorbs it (close 1006, journey
        cancelled) — the shed must not have changed that owner."""
        gate = runtime

        async def read(pool, fn, *args):
            gate.flip_to_draining(drain_age=2.0)
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

        monkeypatch.setattr(pusher, 'run_blocking', read)
        journeys = _journey_factory()
        monkeypatch.setattr(pusher, 'JourneyAttempt', journeys)

        websocket = FakeWebSocket()
        await pusher._websocket_util_trigger(websocket, 'uid', 8000)

        assert websocket.close_calls == [1006]
        journeys.attempts[0].finish.assert_called_once_with('cancelled')


class TestRefusedCloseClass:
    """Close 1013 is its own class in the shared close vocabulary."""

    class _Close:
        def __init__(self, code):
            self.rcvd = MagicMock()
            self.rcvd.code = code
            self.rcvd.reason = ''

    def test_1013_classifies_as_refused(self):
        assert classify_pusher_close(self._Close(1013)) == PUSHER_CLOSE_CLASS_REFUSED

    def test_refused_is_distinct_from_restart_and_clean(self):
        assert classify_pusher_close(self._Close(1012)) == PUSHER_CLOSE_CLASS_RESTART
        assert classify_pusher_close(self._Close(1000)) == PUSHER_CLOSE_CLASS_CLEAN
        assert PUSHER_CLOSE_CLASS_REFUSED not in {PUSHER_CLOSE_CLASS_RESTART, PUSHER_CLOSE_CLASS_CLEAN}

    def test_generic_abnormal_codes_stay_abnormal(self):
        for code in (1006, 1011, 1015, 3000, 4000):
            assert classify_pusher_close(self._Close(code)) == PUSHER_CLOSE_CLASS_ABNORMAL

    def test_restart_singleton_unchanged(self):
        """The restart class is exactly {1012}: adding the refusal class must
        not widen it (three landed suites pin this singleton)."""
        assert PUSHER_EXPECTED_RESTART_CLOSE_CODES == frozenset({1012})

    def test_refused_class_label_vocabulary_matches_counter(self):
        """The class string is a Prometheus label value: it must stay stable
        and be declared in the counter's help text."""
        assert PUSHER_CLOSE_CLASS_REFUSED == 'refused'
        metrics_source = (BACKEND_DIR / 'utils' / 'metrics.py').read_text()
        counter_block = metrics_source[metrics_source.index('PUSHER_CLOSE_EVENTS_TOTAL = Counter(') :]
        counter_block = counter_block[: counter_block.index(')', counter_block.index("['close_class', 'deduped']"))]
        assert 'refused' in counter_block

    def test_refused_severity_is_info(self, caplog):
        logger = logging.getLogger('pusher_test_refused')
        with caplog.at_level(logging.INFO, logger='pusher_test_refused'):
            log_pusher_connection_closed(
                logger, ConnectionShapedClose(1013), 'Pusher audio_bytes Connection closed', uid='u', session_id='s'
            )
        records = [r for r in caplog.records if 'Pusher audio_bytes Connection closed' in r.getMessage()]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO

    def test_refused_dedupes_to_info(self, caplog):
        e = ConnectionShapedClose(1013)
        session = MagicMock()
        session.has_armed_reconnect.return_value = True
        logger = MagicMock()
        log_pusher_connection_closed(
            logger, e, 'Pusher audio_bytes Connection closed', uid='u', session_id='s', session=session
        )
        logger.log.assert_called_once()
        assert logger.log.call_args[0][0] == logging.INFO

    def test_refused_first_observation_without_session_is_info(self):
        logger = MagicMock()
        log_pusher_connection_closed(
            logger, ConnectionShapedClose(1013), 'Pusher audio_bytes Connection closed', uid='u', session_id='s'
        )
        logger.log.assert_called_once()
        assert logger.log.call_args[0][0] == logging.INFO


class ConnectionShapedClose(Exception):
    """A ``ConnectionClosed``-shaped object for the classifier."""

    def __init__(self, code):
        self.rcvd = MagicMock()
        self.rcvd.code = code
        self.rcvd.reason = ''


class TestSessionOutcomeContract:
    """1013 keeps the interrupted-session meaning; application failure wins."""

    def test_1013_outcome_is_cancelled(self):
        assert pusher_session_outcome(1013) == 'cancelled'

    def test_1013_outcome_is_not_failure(self):
        assert pusher_session_outcome(1013) != 'failure'

    def test_application_failure_wins_over_1013(self):
        assert pusher_session_outcome(1013, application_failed=True) == 'failure'

    def test_outcome_ladder_unchanged_for_other_codes(self):
        assert pusher_session_outcome(1011) == 'failure'
        assert pusher_session_outcome(1011, peer_keepalive_timeout=True) == 'cancelled'
        assert pusher_session_outcome(1000) == 'success'
        assert pusher_session_outcome(1001) == 'success'
        assert pusher_session_outcome(1006) == 'cancelled'

    def test_outcome_1013_with_peer_keepalive_stays_cancelled(self):
        """No peer interaction exists on a refused session, so the keepalive
        override cannot apply — but the outcome contract must stay monotone
        if a future close path ever carries one."""
        assert pusher_session_outcome(1013, peer_keepalive_timeout=True) == 'cancelled'


class TestShedConfigurationInvariants:
    def test_attempt_budget_is_positive_and_bounded(self):
        assert 2 <= pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS <= 5

    def test_backoff_is_positive_and_total_drain_is_bounded(self):
        base = pusher.PUSHER_ADMISSION_TRANSIENT_BACKOFF_SECONDS
        assert base > 0
        total = sum(base * (2**i) for i in range(pusher.PUSHER_ADMISSION_TRANSIENT_ATTEMPTS - 1))
        assert total < 1.0  # a reconnecting client is refused promptly, not parked

    def test_exhaustion_exception_is_an_exception_not_a_base_exception(self):
        """The refusal must be catchable by the handler's ``except`` arms —
        subclassing ``BaseException`` directly would bypass them."""
        assert issubclass(pusher._AdmissionTransientExhausted, Exception)
        assert not issubclass(pusher._AdmissionTransientExhausted, asyncio.CancelledError)


class TestAdmissionModuleSurface:
    """The wiring pins: which reads ride the shed, in which arm order."""

    def test_shed_applied_to_all_four_admission_reads(self):
        source = Path(pusher.__file__).read_text()
        admission = source[
            source.index('Session-admission profile reads') : source.index(
                'except asyncio.CancelledError:', source.index('Session-admission profile reads')
            )
        ]
        for read in (
            'get_audio_bytes_webhook_seconds',
            'is_audio_bytes_app_enabled',
            'get_user_private_cloud_sync_enabled',
            'get_data_protection_level',
        ):
            assert f'_admission_read_with_transient_shed(' in admission and read in admission

    def test_shed_helper_uses_the_shared_transient_classifier(self):
        source = Path(pusher.__file__).read_text()
        shed = source[
            source.index('async def _admission_read_with_transient_shed') : source.index(
                'async def _dispatch_transcript_item'
            )
        ]
        assert 'is_transient_availability_error' in shed
        assert 'run_blocking' in shed

    def test_shed_re_raises_cancel_before_classifying(self):
        """Order inside the shed: the cancel arm must precede the classifier,
        or a cancel could be misread as a transient blip."""
        source = Path(pusher.__file__).read_text()
        shed = source[
            source.index('async def _admission_read_with_transient_shed') : source.index(
                'async def _dispatch_transcript_item'
            )
        ]
        assert shed.index('except asyncio.CancelledError') < shed.index('is_transient_availability_error')

    def test_refusal_arm_sits_between_teardown_and_loud_arms(self):
        """Arm order at the admission boundary: cancel (teardown) first, the
        clean refusal second, the generic loud ``except Exception`` last."""
        source = Path(pusher.__file__).read_text()
        admission = source[source.index('journey_attempt = JourneyAttempt') : source.index('# Bounded queues')]
        i_cancel = admission.index('except asyncio.CancelledError')
        i_refuse = admission.index('except _AdmissionTransientExhausted')
        i_loud = admission.index('except Exception:')
        assert i_cancel < i_refuse < i_loud

    def test_refusal_close_rides_the_best_effort_close(self):
        """The 1013 close must go through ``_close_websocket_best_effort`` —
        a close fault on a refused session must never escape the ASGI app."""
        source = Path(pusher.__file__).read_text()
        refusal = source[
            source.index('except _AdmissionTransientExhausted') : source.index(
                'except Exception:', source.index('except _AdmissionTransientExhausted')
            )
        ]
        assert '_close_websocket_best_effort(websocket, 1013, uid)' in refusal
        assert refusal.index('journey_attempt.finish') < refusal.index('_close_websocket_best_effort')

    def test_refusal_closes_before_supervision_begins(self):
        """Grounding the harness: the refusal arm sits in the admission try,
        before the supervised section that acquires the gauge — a refused
        session never starts background tasks."""
        source = Path(pusher.__file__).read_text()
        refusal_index = source.index('except _AdmissionTransientExhausted')
        supervision_index = source.index('supervise_tasks(')
        gauge_index = source.index('PUSHER_ACTIVE_WS_CONNECTIONS.inc()')
        assert refusal_index < supervision_index
        assert refusal_index < gauge_index

    def test_counters_are_module_level_and_labelled(self):
        source = (BACKEND_DIR / 'utils' / 'metrics.py').read_text()
        assert "PUSHER_ADMISSION_SHED_RETRIES_TOTAL = Counter(" in source
        assert "PUSHER_ADMISSION_SHED_EXHAUSTED_TOTAL = Counter(" in source
        assert source.count("['read']") >= 2


class TestDocsAndParityContracts:
    """The documentation and the listen-side precedent must move together."""

    def test_shed_is_documented_in_the_pipeline_contract(self):
        mdx = (REPO_DIR / 'backend' / 'docs' / 'listen_pusher_pipeline.mdx').read_text()
        assert 'Session-admission transient shed (pusher)' in mdx
        assert '1013' in mdx
        assert 'pusher_admission_shed_exhausted_total' in mdx

    def test_listen_side_parity_fences_close_1013(self):
        """The pusher refusal is the same retryable-refusal contract the
        listen side's admission fences already speak — the precedent suite
        must keep asserting it, so the two ends cannot drift."""
        source = (BACKEND_DIR / 'tests' / 'unit' / 'test_listen_admission_fence_containment.py').read_text()
        assert 'closes 1013' in source
        assert 'run_critical_ws' in source
        assert 'Failure-Class:' in source

    def test_listen_side_transient_set_matches_the_shed_classifier(self):
        """Both ends classify the same bounded transient set: the fence suite's
        docstring names the trio plus the retry envelope, the shed delegates
        to the shared ``database._client`` classifier."""
        source = (BACKEND_DIR / 'tests' / 'unit' / 'test_listen_admission_fence_containment.py').read_text()
        for token in ('ServiceUnavailable', 'DeadlineExceeded', 'InternalServerError', 'RetryError'):
            assert token in source
        from database._client import is_transient_availability_error

        assert callable(is_transient_availability_error)

    def test_docs_mention_the_refusal_class_severity(self):
        """The INFO severity of a refused close is part of the documented
        contract (the operator-facing meaning of the log stream)."""
        source = Path(BACKEND_DIR / 'utils' / 'listen_pusher_session.py').read_text()
        assert 'refused session' in source


class TestAdmissionShedProperties:
    """Property-shaped sweeps over the exception vocabulary."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('error', list(AVAILABILITY_TRIO))
    async def test_property_every_trio_member_sheds(self, monkeypatch, error):
        _sync_run_blocking(monkeypatch)

        def read(*args):
            raise type(error)('m')

        with pytest.raises(pusher._AdmissionTransientExhausted):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')

    @pytest.mark.asyncio
    @pytest.mark.parametrize('error', list(PERMANENT_REFUSALS))
    async def test_property_every_permanent_refusal_stays_loud(self, monkeypatch, error):
        _sync_run_blocking(monkeypatch)

        def read(*args):
            raise type(error)('m')

        with pytest.raises(type(error)):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')

    @pytest.mark.asyncio
    async def test_property_mixed_transient_then_permanent_stays_loud(self, monkeypatch):
        """A shed that retried once and then met a permanent refusal must
        surface the permanent fault, not absorb it into the budget."""
        _sync_run_blocking(monkeypatch)
        state = {'n': 0}

        def read(*args):
            state['n'] += 1
            if state['n'] == 1:
                raise ServiceUnavailable('x')
            raise PermissionDenied('denied')

        with pytest.raises(PermissionDenied):
            await pusher._admission_read_with_transient_shed(object(), read, 'uid')
        assert state['n'] == 2

    def test_property_exhaustion_message_always_names_the_read(self):
        for name in ('read_a', 'users_db.get_data_protection_level', 'x' * 80):
            exhausted = pusher._AdmissionTransientExhausted(name)
            assert name in str(exhausted)
            assert exhausted.read == name


def _make_noop_sleep():
    async def noop_sleep(seconds):
        return None

    return noop_sleep
