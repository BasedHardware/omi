# LIFECYCLE: permanent
"""PL-420/421: budgeted HTTP delivery and bounded lease renewal on every outbox.

Run through run-emulator-proofs.sh; full qualification requires
OMI_REQUIRE_STORE_BACKENDS=all. Only callback IO and time/thread scheduling are
injected. The route, consumer, heartbeat, settlement and recovery use real code
against Firestore, Postgres and the reference simulator. No cloud/vendor IO.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
pytest_plugins = ['tests.conftest']

import pytest
from starlette.requests import Request

from database.outbox import Claim, Outcome
from database import outbox_firestore
from routers import enrichment as route
from testing.store_fixtures import outbox_backend  # noqa: F401
from utils.enrichment import consumer as consumer_module
from utils.enrichment import outbox as enrichment_rows
from utils.enrichment.consumer import EnrichmentConsumer
from utils.workers import consumer as worker_module
from utils.workers.consumer import http_response, run_push

pytestmark = pytest.mark.integration
T0 = 1_000_000.0
HOLD_CAP = 1500.0
BEAT = 30.0
LEASE = 120.0


@pytest.fixture
def ob(outbox_backend, monkeypatch):  # noqa: F811
    # Import delivery dependencies before starting the budget/callback latch.
    from config import action_item_identity  # noqa: F401
    from database import action_item_refresh, summary_processing  # noqa: F401
    from utils.conversations import summary_delivery  # noqa: F401
    from utils.enrichment import callback  # noqa: F401

    outbox_backend.store_harness.seed_user('o')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    monkeypatch.delenv('ENRICHMENT_DELIVERY_BUDGET_SECONDS', raising=False)
    monkeypatch.setattr(enrichment_rows, 'owns_runtime', lambda: True)
    monkeypatch.setattr(outbox_firestore, 'ENRICHMENT_OUTBOX', outbox_backend.outbox)
    clock = SimpleNamespace(time=lambda: T0, monotonic=lambda: 0.0)
    # Patch module references, never the shared time module or RPC deadlines.
    for module in (route, consumer_module, worker_module):
        monkeypatch.setattr(module, 'time', clock)
    return outbox_backend


def put(ob):
    owner = ob.store_harness.uid('o')
    return ob.outbox.enqueue(
        ob.key(owner, 'owed'),
        owner,
        ob.payload('owed', language='en', first_pending_at=T0, summary_seen=True),
        T0,
        now=T0,
    )


def request_for(queued):
    payload = json.dumps({'kind': 'enrichment', 'key': wire_key(queued), 'task_token': queued.wake_token}).encode()

    async def receive():
        return {'type': 'http.request', 'body': payload, 'more_body': False}

    return Request({'type': 'http', 'method': 'POST', 'path': '/v2/enrichment/run', 'headers': []}, receive)


def wire_key(queued):
    # The existing HTTP boundary uses Firestore-shaped keys. New-store row IDs
    # are translated only at this transport seam; all state operations are real.
    return hashlib.sha256(queued.row_id.encode()).hexdigest()


@pytest.mark.parametrize('finish', ['done', 'unexpected_error'])
def test_pl420_budget_frees_http_slot_without_cancelling_the_settlement_owner(ob, monkeypatch, caplog, finish):
    queued = put(ob)
    running, release = threading.Event(), threading.Event()
    calls = []
    tasks = []
    failure = RuntimeError('synthetic callback failure')

    def callback(*args):
        calls.append(args)
        running.set()
        assert release.wait(10), 'test failed to release the owned callback'
        if finish == 'unexpected_error':
            raise failure

    monkeypatch.setattr(EnrichmentConsumer, '_callback', lambda self: callback)
    consume = route.consume

    def consume_wire(key, token, *args):
        assert key == wire_key(queued) and token == queued.wake_token
        return consume(queued.row_id, token, *args)

    monkeypatch.setattr(route, 'consume', consume_wire)

    async def scenario(pool):
        async def run_blocking(_executor, fn, *args):
            return await asyncio.get_running_loop().run_in_executor(pool, functools.partial(fn, *args))

        def start(coro):
            task = asyncio.ensure_future(coro)
            tasks.append(task)
            return task

        async def expire(work, timeout):
            # Exercise the production 300s budget without racing a tiny real timer.
            assert timeout == 300.0
            started = await asyncio.get_running_loop().run_in_executor(pool, running.wait, 10)
            assert started, f'callback did not start; settlement={tasks[0].result() if tasks[0].done() else tasks[0]}'
            # wait_for cancels its awaited future on timeout. A shield must keep
            # the real settlement task alive, including its late error observer.
            work.cancel()
            raise asyncio.TimeoutError

        monkeypatch.setattr(route, 'run_blocking', run_blocking)
        monkeypatch.setattr(
            route,
            'asyncio',
            SimpleNamespace(
                ensure_future=start, shield=asyncio.shield, wait_for=expire, TimeoutError=asyncio.TimeoutError
            ),
        )
        try:
            response = await route.run_enrichment_task(request_for(queued), _retry_count=0)
            assert response.status_code == 409
            assert json.loads(response.body) == {'status': 'retry', 'reason': 'dependency_warming'}
            assert len(tasks) == 1 and not tasks[0].cancelled()
            retry = run_push(EnrichmentConsumer(ob.outbox), ob.outbox, queued.row_id, queued.wake_token, now=T0 + 1)
            assert retry.outcome is Outcome.BUSY
            assert http_response(retry).status_code == 200
            assert len(calls) == 1  # freeing the HTTP slot never admits a second callback
        finally:
            release.set()
            if tasks:
                # Every owned worker is joined on success and assertion failure.
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
        assert not tasks[0].cancelled(), 'delivery timeout cancelled the callback settlement owner'
        if finish == 'done':
            assert tasks[0].result().outcome is Outcome.DONE
            assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 2) is Outcome.STALE
        else:
            assert tasks[0].exception() is failure
            assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 2) is Outcome.BUSY
            # An unexpected late failure remains real debt; expiry recovery is
            # fenced and retains the original acceptance timestamp.
            ob.wakes.clear()
            counts = ob.outbox.sweep(now=T0 + LEASE + 1)
            assert counts.errors == 0 and counts.expired_leases == 1
            assert len(ob.wakes) == 1
            row_id, token, _ = ob.wakes[0]
            replacement = ob.outbox.claim_key(row_id, token, LEASE, now=T0 + LEASE + 2)
            assert isinstance(replacement, Claim) and replacement.attempt == 2
            assert replacement.payload['first_pending_at'] == T0
            assert ob.outbox.ack(replacement, 'processed', now=T0 + LEASE + 3)

    caplog.set_level(logging.WARNING)
    with ThreadPoolExecutor(max_workers=2) as pool:
        asyncio.run(scenario(pool))
    errors = [r for r in caplog.records if 'phase=after_budget' in r.getMessage()]
    assert len(errors) == (1 if finish == 'unexpected_error' else 0)


class HeartbeatSchedule:
    """Drive the real renewal loop on virtual ticks, with a hard stop for mutations.

    No sleeping or test threads: the injected Thread runs its target inline.
    The wait primitive supplies ticks; it never writes leases or predicts a
    consumer outcome. A removed cap reaches the extra ticks and fails assertions.
    """

    def __init__(self, *, ticks=52):
        self.now = T0
        self.monotonic_now = 0.0
        self.ticks = ticks
        self.waits = 0

    def event(self):
        schedule = self

        class TickEvent(threading.Event):
            def wait(self, timeout=None):
                if self.is_set() or schedule.waits >= schedule.ticks:
                    return True
                assert timeout == BEAT
                schedule.waits += 1
                schedule.now += BEAT
                schedule.monotonic_now += BEAT
                return False

        return TickEvent()

    def thread(self, *, target, **_kwargs):
        return SimpleNamespace(start=target, join=lambda timeout: None)

    def install(self, monkeypatch):
        monkeypatch.setattr(consumer_module, 'threading', SimpleNamespace(Event=self.event, Thread=self.thread))
        clock = SimpleNamespace(time=lambda: self.now, monotonic=lambda: self.monotonic_now)
        monkeypatch.setattr(consumer_module, 'time', clock)
        monkeypatch.setattr(worker_module, 'time', clock)


@pytest.mark.parametrize('late', [False, True])
def test_pl421_absolute_hold_cap_preserves_custody_and_fences_late_completion(ob, monkeypatch, caplog, late):
    queued = put(ob)
    schedule = HeartbeatSchedule()
    schedule.install(monkeypatch)
    beats = []
    original_claims = []
    replacements = []
    heartbeat = ob.outbox.heartbeat

    def record_heartbeat(claim, lease_seconds, *, now):
        beats.append(now)
        original_claims.append(claim)
        return heartbeat(claim, lease_seconds, now=now)

    monkeypatch.setattr(ob.outbox, 'heartbeat', record_heartbeat)

    def callback(*_):
        assert schedule.monotonic_now == HOLD_CAP
        assert beats == [T0 + n * BEAT for n in range(1, 50)]
        # The cap stops renewal; it does not revoke the last valid lease early.
        assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + HOLD_CAP + 89) is Outcome.BUSY
        if late:
            schedule.now = T0 + HOLD_CAP + LEASE + 1
            ob.wakes.clear()
            counts = ob.outbox.sweep(now=schedule.now)
            assert counts.errors == 0 and counts.expired_leases == 1
            assert len(ob.wakes) == 1
            row_id, token, _ = ob.wakes[0]
            assert token != queued.wake_token
            replacement = ob.outbox.claim_key(row_id, token, LEASE, now=schedule.now)
            assert isinstance(replacement, Claim) and replacement.attempt == 2
            assert replacement.payload['first_pending_at'] == T0
            replacements.append(replacement)
            old = original_claims[0]
            assert not ob.outbox.heartbeat(old, LEASE, now=schedule.now)
            assert not ob.outbox.release(old, 'retry', now=schedule.now)
            assert ob.outbox.defer(old, schedule.now + 30, 'not_due', now=schedule.now) is None
            assert not ob.outbox.ack(old, 'processed', now=schedule.now)

    caplog.set_level(logging.WARNING)
    result = run_push(
        EnrichmentConsumer(ob.outbox, process=callback), ob.outbox, queued.row_id, queued.wake_token, now=T0
    )
    assert result.outcome is (Outcome.STALE if late else Outcome.DONE)
    assert len([r for r in caplog.records if 'outcome=hold_cap' in r.getMessage()]) == 1
    if late:
        replacement = replacements[0]
        assert (
            ob.outbox.claim_key(replacement.row_id, replacement.wake_token, LEASE, now=schedule.now + 1) is Outcome.BUSY
        )
        assert ob.outbox.ack(replacement, 'processed', now=schedule.now + 2)
        assert not ob.outbox.ack(replacement, 'processed', now=schedule.now + 3)


def test_pl421_ordinary_heartbeats_extend_custody_before_the_cap(ob, monkeypatch):
    queued = put(ob)
    schedule = HeartbeatSchedule(ticks=3)
    schedule.install(monkeypatch)

    def callback(*_):
        assert schedule.monotonic_now == 90
        # The initial lease ended at +120. This observation needs real renewal.
        assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 150) is Outcome.BUSY

    result = run_push(
        EnrichmentConsumer(ob.outbox, process=callback), ob.outbox, queued.row_id, queued.wake_token, now=T0
    )
    assert result.outcome is Outcome.DONE
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 151) is Outcome.STALE
