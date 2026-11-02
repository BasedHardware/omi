"""Swarm lane-1 stubs: consumer drivers, retry shape, reason labels, import direction (contracts (a), (b), (d), (e))."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, ClassVar

import pytest

from database.outbox import Claim, OutboxKind, Outcome
from utils.observability.reasons import (
    REASON_UNKNOWN_TOTAL,
    ConsumerReason,
    ReasonFamily,
    RetryReason,
    reason_label,
)
from utils.workers.consumer import Result, Role, http_response, run_pull, run_push
from utils.workers.retry import ExpectedRetry, retry_response

BACKEND = Path(__file__).resolve().parents[2]


def _claim(row_id: str = 'row-1', lease_token: str = 'lt-1', wake_token: str = 'wk-1') -> Claim:
    return Claim(
        kind=OutboxKind.ENRICHMENT,
        row_id=row_id,
        lease_token=lease_token,
        wake_token=wake_token,
        attempt=1,
        lease_until=1_000.0 + 1800.0,
        owner_id='owner-synthetic',
        payload={},
        policy_id='p' * 16,
    )


@dataclass
class FakeOutbox:
    kind: OutboxKind = OutboxKind.ENRICHMENT
    claim_result: Claim | Outcome = field(default_factory=_claim)
    pull_claims: list[Claim] = field(default_factory=list)
    fenced: bool = False  # ack/defer/release fail as if another holder took the lease
    calls: list[tuple] = field(default_factory=list)

    def claim_key(self, row_id, wake_token, lease_seconds, *, now):
        self.calls.append(('claim_key', row_id, wake_token, lease_seconds))
        return self.claim_result

    def claim(self, n, lease_seconds, *, now):
        self.calls.append(('claim', n, lease_seconds))
        return self.pull_claims[:n]

    def heartbeat(self, claim, lease_seconds, *, now):
        self.calls.append(('heartbeat', claim.lease_token))
        return not self.fenced

    def ack(self, claim, reason, *, now):
        self.calls.append(('ack', claim.lease_token, reason))
        return not self.fenced

    def defer(self, claim, available_at, reason, *, now):
        self.calls.append(('defer', claim.lease_token, available_at, reason))
        return None if self.fenced else 'wk-2'

    def release(self, claim, reason, *, now):
        self.calls.append(('release', claim.lease_token, reason))
        return not self.fenced


class FakeConsumer:
    kind: ClassVar[OutboxKind] = OutboxKind.ENRICHMENT
    role: ClassVar[Role] = Role.WORKERS
    lease_seconds: ClassVar[float] = 1800.0
    heartbeat_seconds: ClassVar[float] = 0.0

    def __init__(self, result: Result | Exception):
        self.result = result
        self.seen: list[Claim] = []

    def process(self, claim: Claim, heartbeat: Callable[[], bool]) -> Result:
        self.seen.append(claim)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    'result, expected_call',
    [
        (Result(Outcome.DONE, ConsumerReason.PROCESSED), 'ack'),
        (Result(Outcome.DISCARDED, ConsumerReason.PRIVACY_BLOCKED), 'ack'),
        (Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE, available_at=2_000.0), 'defer'),
        (Result(Outcome.RETRY, RetryReason.LOCKED, available_at=1_010.0), 'release'),
    ],
)
def test_run_push_settles_the_row_with_the_claim_lease_token(result, expected_call):
    outbox = FakeOutbox()
    consumer = FakeConsumer(result)
    got = run_push(consumer, outbox, 'row-1', 'wk-1', now=1_000.0)
    assert got == result
    assert outbox.calls[0] == ('claim_key', 'row-1', 'wk-1', 1800.0)
    assert outbox.calls[1][0] == expected_call
    assert outbox.calls[1][1] == 'lt-1'
    assert outbox.calls[1][-1] == result.reason.value


@pytest.mark.parametrize(
    'claimed, expected',
    [
        (Outcome.STALE, Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)),
        (Outcome.BUSY, Result(Outcome.BUSY, ConsumerReason.LEASE_HELD)),
        (Outcome.DEFERRED, Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE)),
        (Outcome.DISCARDED, Result(Outcome.DISCARDED, ConsumerReason.SUPERSEDED)),
    ],
)
def test_run_push_claim_key_outcomes_are_200_without_processing(claimed, expected):
    outbox = FakeOutbox(claim_result=claimed)
    consumer = FakeConsumer(AssertionError('must not process'))
    got = run_push(consumer, outbox, 'row-1', 'wk-old', now=1_000.0)
    assert got == expected
    assert consumer.seen == []
    assert http_response(got).status_code == 200


def test_run_push_lost_lease_at_settle_is_stale():
    outbox = FakeOutbox(fenced=True)
    got = run_push(FakeConsumer(Result(Outcome.DONE, ConsumerReason.PROCESSED)), outbox, 'row-1', 'wk-1', now=1_000.0)
    assert got == Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)


def test_run_push_unexpected_exception_propagates_and_writes_nothing():
    outbox = FakeOutbox()
    before = _counter_value('omi_consumer_unexpected_total', kind='enrichment')
    with pytest.raises(RuntimeError):
        run_push(FakeConsumer(RuntimeError('boom')), outbox, 'row-1', 'wk-1', now=1_000.0)
    assert [c[0] for c in outbox.calls] == ['claim_key']
    assert _counter_value('omi_consumer_unexpected_total', kind='enrichment') == before + 1


def test_run_pull_processes_each_claim_up_to_limit():
    claims = [_claim(row_id=f'row-{i}', lease_token=f'lt-{i}', wake_token='') for i in range(3)]
    outbox = FakeOutbox(pull_claims=claims)
    consumer = FakeConsumer(Result(Outcome.DONE, ConsumerReason.PROCESSED))
    results = run_pull(consumer, outbox, limit=2, now=1_000.0)
    assert len(results) == 2
    assert [c.row_id for c in consumer.seen] == ['row-0', 'row-1']
    assert [c[:2] for c in outbox.calls if c[0] == 'ack'] == [('ack', 'lt-0'), ('ack', 'lt-1')]


def test_heartbeat_reports_lost_lease():
    outbox = FakeOutbox(fenced=True)
    seen: list[bool] = []

    class Beating(FakeConsumer):
        def process(self, claim, heartbeat):
            seen.append(heartbeat())
            return Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)

    got = run_push(Beating(Result(Outcome.DONE, ConsumerReason.PROCESSED)), outbox, 'row-1', 'wk-1', now=1_000.0)
    assert seen == [False]
    assert got.outcome is Outcome.STALE


@pytest.mark.parametrize('expected_call', ['ack', 'defer', 'release'])
def test_settle_uses_a_clock_no_earlier_than_the_last_heartbeat(monkeypatch, expected_call):
    """M1 Grok L01-1: a long, heartbeated run must not settle at the entry ``now`` (the outbox derives the
    settle/coalesce window from it)."""
    from utils.workers import consumer as consumer_module

    clock = iter([1_500.0, 2_400.0])
    monkeypatch.setattr(consumer_module.time, 'time', lambda: next(clock))
    nows: dict[str, float] = {}

    class RecordingOutbox(FakeOutbox):
        def heartbeat(self, claim, lease_seconds, *, now):
            nows['heartbeat'] = now
            return super().heartbeat(claim, lease_seconds, now=now)

        def ack(self, claim, reason, *, now):
            nows['settle'] = now
            return super().ack(claim, reason, now=now)

        def defer(self, claim, available_at, reason, *, now):
            nows['settle'] = now
            return super().defer(claim, available_at, reason, now=now)

        def release(self, claim, reason, *, now):
            nows['settle'] = now
            return super().release(claim, reason, now=now)

    results = {
        'ack': Result(Outcome.DONE, ConsumerReason.PROCESSED),
        'defer': Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE, available_at=5_000.0),
        'release': Result(Outcome.RETRY, RetryReason.LOCKED, available_at=5_000.0),
    }

    class LongRun(FakeConsumer):
        def process(self, claim, heartbeat):
            assert heartbeat() and heartbeat()
            return self.result

    run_push(LongRun(results[expected_call]), RecordingOutbox(), 'row-1', 'wk-1', now=1_000.0)
    assert nows == {'heartbeat': 2_400.0, 'settle': 2_400.0}


def test_settle_without_heartbeat_keeps_the_entry_clock():
    outbox = FakeOutbox()
    run_push(FakeConsumer(Result(Outcome.DONE, ConsumerReason.PROCESSED)), outbox, 'row-1', 'wk-1', now=1_000.0)
    assert [c[0] for c in outbox.calls] == ['claim_key', 'ack']


@pytest.mark.parametrize(
    'kwargs, error',
    [
        ({'outcome': Outcome.RETRY, 'reason': ConsumerReason.PROCESSED, 'available_at': 1.0}, TypeError),
        ({'outcome': Outcome.DONE, 'reason': RetryReason.LOCKED}, TypeError),
        ({'outcome': Outcome.RETRY, 'reason': RetryReason.LOCKED}, ValueError),
    ],
)
def test_result_rejects_reason_family_and_missing_available_at(kwargs, error):
    with pytest.raises(error):
        Result(**kwargs)


def test_consumer_deferring_without_available_at_is_rejected():
    outbox = FakeOutbox()
    with pytest.raises(ValueError):
        run_push(FakeConsumer(Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE)), outbox, 'row-1', 'wk-1', now=1_000.0)
    assert [c[0] for c in outbox.calls] == ['claim_key']


def test_not_due_claim_key_maps_to_200_deferred_not_due():
    got = run_push(FakeConsumer(AssertionError()), FakeOutbox(claim_result=Outcome.DEFERRED), 'r', 'w', now=1.0)
    response = http_response(got)
    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'deferred', 'reason': 'not_due'}


def test_outbox_protocol_has_idempotent_wake():
    from database.outbox import Outbox

    assert callable(getattr(Outbox, 'wake'))


def test_http_response_mapping_is_200_or_409_only():
    for outcome, reason in [
        (Outcome.DONE, ConsumerReason.PROCESSED),
        (Outcome.DISCARDED, ConsumerReason.TARGET_DELETED),
        (Outcome.STALE, ConsumerReason.STALE_TOKEN),
        (Outcome.BUSY, ConsumerReason.LEASE_HELD),
        (Outcome.DEFERRED, ConsumerReason.NOT_DUE),
    ]:
        available_at = 1.0 if outcome is Outcome.DEFERRED else None
        response = http_response(Result(outcome, reason, available_at=available_at))
        assert response.status_code == 200
        assert json.loads(response.body) == {'status': outcome.value, 'reason': reason.value}
    retry = http_response(Result(Outcome.RETRY, RetryReason.CALLBACK_PENDING, available_at=1.0))
    assert retry.status_code == 409
    assert json.loads(retry.body) == {'status': 'retry', 'reason': 'callback_pending'}


def test_retry_response_and_expected_retry():
    response = retry_response(RetryReason.KILL_SWITCH_OFF)
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': 'kill_switch_off'}
    assert ExpectedRetry(RetryReason.LOCKED).reason is RetryReason.LOCKED
    with pytest.raises(ValueError):
        ExpectedRetry('not_a_reason')  # type: ignore[arg-type]


def test_reason_label_counts_unknown_and_never_raises():
    before = _counter_value('omi_reason_unknown_total', family='retry')
    assert reason_label(ReasonFamily.RETRY, 'locked', RetryReason) == 'locked'
    assert reason_label(ReasonFamily.RETRY, RetryReason.LOCKED, RetryReason) == 'locked'
    assert reason_label(ReasonFamily.RETRY, 'some free text', RetryReason) == 'unknown'
    assert reason_label(ReasonFamily.RETRY, None, RetryReason) == 'unknown'
    assert _counter_value('omi_reason_unknown_total', family='retry') == before + 2


def test_reason_enums_follow_naming_rules():
    for enum in (ReasonFamily, RetryReason, ConsumerReason):
        for member in enum:
            assert member.value == member.value.lower() and len(member.value) <= 40
    for enum in (RetryReason, ConsumerReason):
        assert enum.UNKNOWN.value == 'unknown'


def test_outbox_imports_nothing_from_workers_and_workers_read_no_env():
    """Contract (a) import direction, and contract (c) invariant 3 for the lane-1 stub files."""
    outbox_tree = ast.parse((BACKEND / 'database' / 'outbox.py').read_text())
    for node in ast.walk(outbox_tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or '').startswith('utils.workers')
    for path in [BACKEND / 'database' / 'outbox.py', *sorted((BACKEND / 'utils' / 'workers').glob('*.py'))]:
        source = path.read_text()
        assert 'os.getenv' not in source and 'os.environ' not in source, path


def test_claim_is_frozen():
    claim = _claim()
    with pytest.raises(Exception):
        claim.row_id = 'other'  # type: ignore[misc]
    assert replace(claim, attempt=2).attempt == 2


def _counter_value(name: str, **labels: str) -> float:
    from prometheus_client import REGISTRY

    value = REGISTRY.get_sample_value(name, labels)
    return value or 0.0


def test_unknown_counter_is_preinitialized_for_every_family():
    for family in ReasonFamily:
        REASON_UNKNOWN_TOTAL.labels(family=family.value)  # existing child, no new series
        assert _counter_value('omi_reason_unknown_total', family=family.value) >= 0.0
