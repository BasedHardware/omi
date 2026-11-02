"""A full flight is evaluated within the spend-admission deadline (batchretune, 2026-11-02).

At 25% (2026-11-02 02:11-03:11Z, ro-prod) 0.27 of 0.84 leases/s came back from
spend admission neither allowed nor held: ``authorize`` checks leases serially
under a 4s deadline (worker-side admission p50 1.48s, p95 4.6s; 304
``TimeoutError`` lines in the hour), and a flight sends up to ``batch_size``
leases in one call. Each unreached lease was deferred on the admission backoff
streak, so ready work waited while GPUs idled. The worker now sends at most
``ADMISSION_LEASES_PER_CALL`` leases per call and the server deadline fits that
many at the measured per-lease cost. The serial, fail-closed checks are unchanged.
"""

import time

import pytest

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import admission, compute_client
from utils.batch_pipeline import pump as module
from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import LEASE_SECONDS, Scheduler

# Measured: 0.84 leases/s over 0.48 receipts/s at a 1.48s p50 receipt.
PER_LEASE_P50_SECONDS = 0.85
MAX_BATCH_SIZE = 32  # Pump's own bound


class Worker:
    def process_batch(self, items, *, authorize_dispatch=None):
        if authorize_dispatch is not None:
            # The dispatch re-check goes through the same capped calls.
            assert authorize_dispatch({v.segment_id for v in items}) == {v.segment_id: None for v in items}
        return [WorkResult(v.segment_id, f'gs://synthetic/{v.segment_id}') for v in items]


def flight(count):
    store = MemoryStore()
    queue = Scheduler(store)
    for n in range(count):
        queue.enqueue(item(f'unit{n}', owner=f'owner{n}'), time.time())
    return store, queue


def test_timeout_ladder_fits_one_capped_call_inside_each_outer_wait():
    cap = module.ADMISSION_LEASES_PER_CALL
    assert 1 <= cap <= 4
    requested = admission.deadline_seconds(compute_client.ADMISSION_DEADLINE_SECONDS)
    # The worker's deadline is granted in full and fits a capped call at twice
    # the measured per-lease cost.
    assert requested == compute_client.ADMISSION_DEADLINE_SECONDS
    assert requested >= 2 * PER_LEASE_P50_SECONDS * cap
    # Server deadline < client HTTP timeout < the pump's wait for one call.
    assert requested < compute_client.AUTHORIZE_TIMEOUT_SECONDS < module.ADMISSION_CALL_TIMEOUT_SECONDS
    # A worker that sends no header keeps the deadline under its old 5s timeout.
    assert admission.deadline_seconds(None) == admission.AUTHORIZE_SECONDS < 5
    # Even the largest flight finishes admission well inside its leases.
    calls = -(-MAX_BATCH_SIZE // cap)
    assert calls * module.ADMISSION_CALL_TIMEOUT_SECONDS < LEASE_SECONDS


@pytest.mark.parametrize(
    'header, expected',
    [(None, 4.0), ('8.0', 8.0), ('6', 6.0), ('1', 4.0), ('3600', 8.0), ('nan', 4.0), ('inf', 4.0), ('soon', 4.0)],
)
def test_advertised_deadline_is_clamped(header, expected):
    assert admission.deadline_seconds(header) == expected


def test_client_advertises_its_deadline_and_waits_longer_than_it():
    import json
    from io import BytesIO

    from utils.batch_pipeline.contracts import LeasedWork

    seen = {}

    def send(request, timeout):
        seen['header'] = request.get_header('X-omi-admission-seconds')
        seen['timeout'] = timeout
        return BytesIO(json.dumps({'allowed': ['unit0'], 'retry_after': {}, 'held_reason': {}}).encode())

    client = compute_client.ComputeClient('https://synthetic.invalid', 'synthetic', 'dev', token=lambda: 't', send=send)
    assert client([LeasedWork(item('unit0'), 'token', 0, 0.0)])['allowed'] == ['unit0']
    assert float(seen['header']) == compute_client.ADMISSION_DEADLINE_SECONDS
    assert seen['timeout'] == compute_client.AUTHORIZE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_full_flight_is_admitted_in_capped_serial_calls(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    calls = []

    def authorize(leases):
        calls.append([v.item.segment_id for v in leases])
        return {'allowed': [v.item.segment_id for v in leases]}

    store, queue = flight(8)
    pump = Pump(queue, Worker(), capacity=lambda: PoolCapacity(time.time(), 8), authorize_compute=authorize)
    assert await pump.run_once() == 8
    flight_calls = calls[: -(-8 // module.ADMISSION_LEASES_PER_CALL)]
    assert all(len(c) <= module.ADMISSION_LEASES_PER_CALL for c in calls)
    assert sorted(s for c in flight_calls for s in c) == sorted(f'unit{n}' for n in range(8))
    assert all(store.rows['jobs', f'unit{n}']['state'] == 'committed' for n in range(8))


@pytest.mark.asyncio
async def test_failed_call_leaves_only_its_own_leases_unevaluated(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    calls = []

    def authorize(leases):
        calls.append([v.item.segment_id for v in leases])
        if len(calls) == 1:
            raise TimeoutError('synthetic admission deadline')
        return {'allowed': [v.item.segment_id for v in leases]}

    store, queue = flight(8)
    pump = Pump(queue, Worker(), capacity=lambda: PoolCapacity(time.time(), 8), authorize_compute=authorize)
    done = await pump.run_once()
    first = set(calls[0])
    assert done == 8 - len(first) and 0 < len(first) <= module.ADMISSION_LEASES_PER_CALL
    for n in range(8):
        job = store.rows['jobs', f'unit{n}']
        if f'unit{n}' in first:
            # Fail closed: no allow, no attempt charge, no false hold.
            assert job['state'] == 'retry' and job['attempt'] == 0
            assert 'compute_admission_token' not in job and 'compute_decision' not in job
        else:
            assert job['state'] == 'committed'
