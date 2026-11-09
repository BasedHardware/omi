# LIFECYCLE: permanent
"""Daily parity PL-342/397/398: enrichment debt survives retries and bounded scans.

The same consumer and Outbox contract runs on legacy Firestore, reference sim and
replacement Postgres. Only dependency IO is injected; claims, releases, deferrals,
wakes and scan progress use the real implementations. No cloud or vendor IO.
Require OMI_REQUIRE_STORE_BACKENDS=all for a complete qualification.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This proof lives in the workflow's existing *_emulator_test.py path filter.
# Reuse the canonical backend test environment and outbound-network guards.
pytest_plugins = ['tests.conftest']

import httpx
import pytest
from google.api_core import exceptions as google_errors

from database.outbox import Claim, Outcome
from testing.store_fixtures import outbox_backend  # noqa: F401
from utils.enrichment.consumer import EnrichmentConsumer
from utils.enrichment import consumer as enrichment_consumer
from utils.workers.consumer import http_response, run_push

pytestmark = pytest.mark.integration
T0 = 1_000_000.0
LEASE = 120.0


@pytest.fixture
def ob(outbox_backend, monkeypatch):  # noqa: F811
    outbox_backend.store_harness.seed_user('o')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    return outbox_backend


def put(ob, label='owed', *, at=T0, **metadata):
    owner = ob.store_harness.uid('o')
    return ob.outbox.enqueue(ob.key(owner, label), owner, ob.payload(label, language='en', **metadata), at, now=at)


def take(ob, queued, *, now=T0, token=None, lease=LEASE):
    claim = ob.outbox.claim_key(queued.row_id, token or queued.wake_token, lease, now=now)
    assert isinstance(claim, Claim)
    return claim


def fault(kind):
    if kind.startswith('google_'):
        return getattr(google_errors, kind.removeprefix('google_'))('synthetic dependency fault')
    if kind == 'timeout':
        return httpx.ReadTimeout('synthetic timeout')
    if kind == 'network':
        return httpx.ConnectError('synthetic network failure')
    if kind == 'wrapped':
        wrapped = RuntimeError('synthetic wrapper')
        wrapped.__cause__ = httpx.ReadTimeout('synthetic timeout')
        return wrapped
    if kind == 'text_only':
        return RuntimeError('503 ServiceUnavailable timeout: message text is not typed evidence')
    request = httpx.Request('POST', 'https://synthetic.invalid/embedding')
    return httpx.HTTPStatusError(
        'synthetic response', request=request, response=httpx.Response(int(kind), request=request)
    )


@pytest.mark.parametrize(
    'kind',
    [
        'google_Aborted',
        'google_DeadlineExceeded',
        'google_ServiceUnavailable',
        'google_InternalServerError',
        'google_TooManyRequests',
        'timeout',
        'network',
        'wrapped',
        '429',
        '500',
        '502',
        '503',
        '504',
    ],
)
def test_pl397_transient_dependency_retries_before_the_original_lease_expires(ob, monkeypatch, kind):
    # A later revision isolates retry custody from first-summary admission.
    queued = put(ob, summary_seen=True)
    calls = []
    error = fault(kind)

    def callback(*args):
        calls.append(args)
        if len(calls) == 1:
            raise error

    # Inject only the consumer clock; transport deadline clocks remain real.
    monkeypatch.setattr(enrichment_consumer, 'time', SimpleNamespace(time=lambda: T0 + 1, monotonic=lambda: T0 + 1))
    consumer = EnrichmentConsumer(ob.outbox, process=callback)
    retry = run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0)
    response = http_response(retry)
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': 'dependency_warming'}
    # Same task delivery must reclaim immediately, rather than answer BUSY 200.
    done = run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0 + 2)
    assert done.outcome is Outcome.DONE
    assert len(calls) == 2
    assert http_response(done).status_code == 200
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 3) is Outcome.STALE


@pytest.mark.parametrize('kind', ['400', '401', '403', 'text_only'])
def test_pl397_unexpected_fault_keeps_custody_until_expiry(ob, monkeypatch, kind):
    # A later revision isolates retry custody from first-summary admission.
    queued = put(ob, summary_seen=True)
    error = fault(kind)
    monkeypatch.setattr(enrichment_consumer, 'time', SimpleNamespace(time=lambda: T0, monotonic=lambda: T0))

    def callback(*_):
        raise error

    consumer = EnrichmentConsumer(ob.outbox, process=callback)
    with pytest.raises(type(error)) as raised:
        run_push(consumer, ob.outbox, queued.row_id, queued.wake_token, now=T0)
    assert raised.value is error
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 2) is Outcome.BUSY
    reclaimed = take(ob, queued, now=T0 + LEASE + 1)
    assert reclaimed.attempt == 2
    assert ob.outbox.ack(reclaimed, 'processed', now=T0 + LEASE + 2)


def test_pl397_retry_settlement_cannot_release_a_replacement_owner(ob, monkeypatch):
    # A later revision isolates retry custody from first-summary admission.
    queued = put(ob, summary_seen=True)
    replacement = []
    monkeypatch.setattr(enrichment_consumer, 'time', SimpleNamespace(time=lambda: T0, monotonic=lambda: T0))

    def callback(*_):
        replacement.append(take(ob, queued, now=T0 + LEASE + 1))
        raise google_errors.Aborted('synthetic contention after the old lease expired')

    result = run_push(
        EnrichmentConsumer(ob.outbox, process=callback), ob.outbox, queued.row_id, queued.wake_token, now=T0
    )
    assert result.outcome is Outcome.STALE
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + LEASE + 2) is Outcome.BUSY
    assert ob.outbox.ack(replacement[0], 'processed', now=T0 + LEASE + 2)


@pytest.mark.parametrize('prefix_kind', ['leased', 'healthy_wake'])
def test_pl398_bounded_watchdog_reaches_expired_debt_beyond_a_healthy_prefix(ob, prefix_kind, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120')
    # More than the legacy sweep's ten pages of two rows. A stateless rescan
    # never reaches the tail. Postgres/sim may select actionable rows directly.
    for index in range(23):
        queued = put(ob, f'prefix-{index}', at=T0 + index)
        claim = take(ob, queued, now=T0 + index, lease=10_000)
        if prefix_kind == 'healthy_wake':
            assert ob.outbox.defer(claim, T0 + index, 'conversation_missing', now=T0 + index)
    tail = put(ob, 'lost-wake', at=T0 + 30, first_pending_at=T0 + 30, summary_deadline_at=T0 + 150)
    abandoned = take(ob, tail, now=T0 + 30)
    ob.wakes.clear()
    now = T0 + 200
    for _ in range(4):
        counts = ob.outbox.sweep(now=now, limit=2)
        assert counts.errors == 0
        repaired = [wake for wake in ob.wakes if wake[0] == tail.row_id]
        if repaired:
            break
    assert len(repaired) == 1, 'bounded sweeps repeatedly inspected the same healthy prefix'
    row_id, token, due = repaired[0]
    assert token != tail.wake_token and due <= now
    assert not ob.outbox.ack(abandoned, 'processed', now=now)
    replacement = take(ob, tail, now=now, token=token)
    assert replacement.attempt == 2
    assert replacement.owner_id == abandoned.owner_id
    assert replacement.payload == abandoned.payload  # acceptance/deadline metadata is not renewed
    assert replacement.payload['first_pending_at'] == T0 + 30
    assert replacement.payload['summary_deadline_at'] == T0 + 150
    assert not ob.outbox.release(dataclasses.replace(replacement, lease_token=abandoned.lease_token), 'retry', now=now)
    assert ob.outbox.ack(replacement, 'processed', now=now)
    assert ob.outbox.claim_key(row_id, token, LEASE, now=now + 1) is Outcome.STALE


def test_pl342_long_custody_episode_slows_polling_without_retiring_debt(ob, request):
    if ob.name in {'sim', 'postgres'}:
        request.applymarker(
            pytest.mark.xfail(
                strict=True,
                raises=AssertionError,
                reason='https://github.com/BasedHardware/omi/issues/24556 — reason-bound custody age is not ported',
            )
        )
    queued = put(ob)
    first = take(ob, queued)
    token = ob.outbox.defer(first, T0 + 120, 'conversation_missing', now=T0)
    assert token
    late = T0 + 6 * 3600 + 1
    second = take(ob, queued, now=late, token=token)
    ob.wakes.clear()
    token = ob.outbox.defer(second, late + 120, 'conversation_missing', now=late)
    assert token
    assert ob.wakes[-1] == (queued.row_id, token, late + 3600)
    # Inspect the scheduled wake rather than delivering early: early delivery
    # itself legitimately rotates the wake token under contract (b).
    resumed = take(ob, queued, now=late + 3600, token=token)
    assert ob.outbox.ack(resumed, 'processed', now=late + 3600)


def test_pl342_reason_change_and_reopening_start_fresh_custody_episodes(ob):
    queued = put(ob)
    first = take(ob, queued)
    token = ob.outbox.defer(first, T0 + 120, 'conversation_missing', now=T0)
    late = T0 + 6 * 3600 + 1
    resumed = take(ob, queued, now=late, token=token)
    ob.wakes.clear()
    next_due = late + 120
    token = ob.outbox.defer(resumed, next_due, 'pending_live_bridge', now=late)
    assert ob.wakes[-1] == (queued.row_id, token, next_due)
    changed = take(ob, queued, now=next_due, token=token)
    if ob.name == 'emulator':
        # The old backend retains a dormant first-summary receipt instead of
        # deleting the row. Reopening that receipt must reset its episode too.
        assert ob.outbox.record_summary(changed)
    assert ob.outbox.ack(changed, 'processed', now=next_due)
    # A new obligation with the same dedupe key cannot inherit the old age.
    reopened_at = next_due + 6 * 3600 + 1
    reopened = put(ob, at=reopened_at)
    claim = take(ob, reopened, now=reopened_at)
    token = ob.outbox.defer(claim, reopened_at + 120, 'pending_live_bridge', now=reopened_at)
    assert ob.wakes[-1] == (reopened.row_id, token, reopened_at + 120)
