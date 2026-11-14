"""The pump's four flight-teardown exits run through the custody family.

Each site once booked every exception on the ERROR fault channel; the
wiring now drives ``replay_teardown_refund`` with its closed site row, so
a closed contention loss reports on the row's honest channel (and a lost
live refund replays, silently), while a real fault keeps the historical
line byte-for-byte. These cells drive the real pump flight paths -- the
release call, the GPU-restart refund whose flight still dies, and the
stop refund that only runs when the stop event flips after the claim.

Failure-Class: FC-flight-custody-contention-losses-booked-as-production-faults
"""

import asyncio
import logging
import time

import pytest
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import LeasedWork, PoolCapacity
from utils.batch_pipeline.errors import FatalGpuError
from utils.batch_pipeline.pump import Pump
import utils.batch_pipeline.pump as pump_module
from utils.batch_pipeline.scheduler import Scheduler
from database.firestore_transaction_retry import FirestoreContentionExhausted

FC = 'FC-flight-custody-contention-losses-booked-as-production-faults'


def raised(build):
    """Return the exception as a raise site produced it: real traceback attached."""
    try:
        raise build
    except BaseException as error:  # noqa: BLE001 - a real traceback is the point
        return error


def exhaustion(operation=None, **attrs):
    error = raised(FirestoreContentionExhausted('contention budget burned'))
    if operation is not None:
        attrs['operation'] = operation
    for key, value in attrs.items():
        setattr(error, key, value)
    return error


def lease(segment_id='first'):
    return LeasedWork(item=item(segment_id), token='token', attempt=1, lease_until=time.time() + 120)


class QuietWorker:
    def process_batch(self, items):
        return []


def build_pump(worker=None, **kwargs):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('first'), time.time())
    pump = Pump(queue, worker or QuietWorker(), capacity=lambda: PoolCapacity(time.time(), 8), **kwargs)
    return store, queue, pump


def custody(records, *tokens):
    return [r for r in records if all(token in r.getMessage() for token in tokens)]


# --- the finished-lease release ----------------------------------------------------


@pytest.mark.asyncio
async def test_release_contention_lands_on_the_info_channel(caplog, monkeypatch):
    _, queue, pump = build_pump()

    def contended_release(*args, **kwargs):
        raise exhaustion(operation='batch_release')

    monkeypatch.setattr(queue, 'release', contended_release)
    with caplog.at_level(logging.INFO):
        await pump._release([lease('first')])
    record = custody(caplog.records, 'event=batch_flight outcome=lease_release')[0]
    assert record.levelno == logging.INFO
    assert record.getMessage().startswith(
        'event=batch_flight outcome=lease_release exception_type=FirestoreContentionExhausted operation=batch_release'
    )
    assert ' attempt=1 retry_after_ms=0' in record.getMessage()


@pytest.mark.asyncio
async def test_release_real_fault_keeps_the_historical_error_line(caplog, monkeypatch):
    _, queue, pump = build_pump()

    def broken_release(*args, **kwargs):
        raise RuntimeError('storage unavailable')

    monkeypatch.setattr(queue, 'release', broken_release)
    with caplog.at_level(logging.ERROR):
        await pump._release([lease('first')])
    assert [r.getMessage() for r in caplog.records] == [
        'event=batch_flight outcome=lease_release exception_type=RuntimeError'
    ]


# --- the GPU-restart refund ---------------------------------------------------------


class GpuDyingWorker:
    def process_batch(self, items):
        raise FatalGpuError('synthetic CUDA OOM')


@pytest.mark.asyncio
async def test_gpu_restart_refund_contention_warns_then_the_flight_still_dies(
    caplog, monkeypatch, full_cap_dispatch_rollout
):
    _, queue, pump = build_pump(worker=GpuDyingWorker())
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)

    def contended_defer(*args, **kwargs):
        raise exhaustion(operation='batch_defer')

    monkeypatch.setattr(queue, 'defer', contended_defer)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(FatalGpuError):
            await pump.run_once()
    custody_lines = custody(caplog.records, 'event=batch_gpu_restart outcome=lease_recovery')
    assert custody_lines, 'the GPU-restart refund must report its contention loss'
    assert custody_lines[0].levelno == logging.WARNING
    assert ' operation=batch_defer' in custody_lines[0].getMessage()


@pytest.mark.asyncio
async def test_gpu_restart_refund_real_fault_keeps_the_historical_error_line(
    caplog, monkeypatch, full_cap_dispatch_rollout
):
    _, queue, pump = build_pump(worker=GpuDyingWorker())
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)

    def broken_defer(*args, **kwargs):
        raise RuntimeError('storage unavailable')

    monkeypatch.setattr(queue, 'defer', broken_defer)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FatalGpuError):
            await pump.run_once()
    refunds = custody(caplog.records, 'event=batch_gpu_restart outcome=lease_recovery')
    assert refunds
    assert refunds[0].getMessage() == 'event=batch_gpu_restart outcome=lease_recovery exception_type=RuntimeError'
    assert refunds[0].levelno == logging.ERROR


@pytest.mark.asyncio
async def test_gpu_restart_refund_never_replays_one_loss_one_line(caplog, monkeypatch, full_cap_dispatch_rollout):
    _, queue, pump = build_pump(worker=GpuDyingWorker())
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)
    calls = []

    def contended_defer(*args, **kwargs):
        calls.append(1)
        raise exhaustion(retry_after=4.0)

    monkeypatch.setattr(queue, 'defer', contended_defer)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(FatalGpuError):
            await pump.run_once()
    assert len(calls) == 1, 'the process is ending: no replay'
    assert len(custody(caplog.records, 'event=batch_gpu_restart')) == 1


# --- the stop refund (claimed behind a sibling's chain on SIGTERM) ------------------


class StopFlippingWorker:
    """Claims its lease first, then flips the stop event mid-flight.

    The pump's stop refund is the "claimed behind a sibling's chain when
    SIGTERM arrived" branch: it only runs when the stop event turns set
    after the claim, so the worker flips it in ``prepare_first`` -- the
    hook that runs between the claim and the flight's teardown gate.
    """

    def __init__(self, stop_event):
        self.stop_event = stop_event

    def prepare_first(self, items):
        self.stop_event.set()
        return None

    def process_batch(self, items):
        return []


@pytest.mark.asyncio
async def test_stop_refund_contention_replays_and_converges_without_error_lines(caplog, monkeypatch):
    stop = asyncio.Event()
    _, queue, pump = build_pump(flights=2, worker=StopFlippingWorker(stop))
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)
    calls = []

    def contended_once_defer(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise exhaustion(operation='batch_defer', retry_after=0.1)

    monkeypatch.setattr(queue, 'defer', contended_once_defer)
    with caplog.at_level(logging.INFO):
        assert await pump.run_once(stop_event=stop) == 0
    assert len(calls) == 2, 'the lost refund must replay once and converge'
    faults = [r for r in caplog.records if r.levelno == logging.ERROR and 'outcome=lease_recovery' in r.getMessage()]
    assert faults == [], 'a converged replay books no fault line'


@pytest.mark.asyncio
async def test_stop_refund_exhausted_budget_warns_and_still_returns_cleanly(caplog, monkeypatch):
    stop = asyncio.Event()
    _, queue, pump = build_pump(flights=2, worker=StopFlippingWorker(stop))
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)

    def always_contended_defer(*args, **kwargs):
        raise exhaustion(operation='batch_defer', retry_after=0.1)

    monkeypatch.setattr(queue, 'defer', always_contended_defer)
    with caplog.at_level(logging.INFO):
        assert await pump.run_once(stop_event=stop) == 0
    custody_lines = custody(caplog.records, 'event=batch_flight outcome=lease_recovery')
    assert custody_lines
    assert custody_lines[0].levelno == logging.WARNING
    assert ' attempt=3' in custody_lines[0].getMessage()
    faults = [r for r in caplog.records if r.levelno == logging.ERROR and 'outcome=lease_recovery' in r.getMessage()]
    assert faults == []


@pytest.mark.asyncio
async def test_stop_refund_real_fault_stays_on_the_historical_error_line(caplog, monkeypatch):
    stop = asyncio.Event()
    _, queue, pump = build_pump(flights=2, worker=StopFlippingWorker(stop))
    monkeypatch.setattr(pump_module, 'cap_dispatch_enabled', lambda *args, **kwargs: False)
    calls = []

    def broken_defer(*args, **kwargs):
        calls.append(1)
        raise PermissionError('revoked owner')

    monkeypatch.setattr(queue, 'defer', broken_defer)
    with caplog.at_level(logging.ERROR):
        assert await pump.run_once(stop_event=stop) == 0
    assert calls == [1], 'a real fault never replays'
    assert [r.getMessage() for r in caplog.records if 'outcome=lease_recovery' in r.getMessage()] == [
        'event=batch_flight outcome=lease_recovery exception_type=PermissionError'
    ]
