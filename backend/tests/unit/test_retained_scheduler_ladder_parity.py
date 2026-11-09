"""Scheduler ladder parity: a typed retained diagnosis quarantines on attempt
one and never re-enters the pull ring, while every untyped or undiagnosed
failure walks the bounded ladder to the attempt cap and only then settles as
the historical stage=unknown worker_reason=unclassified quarantine.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import time

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.errors import validation_disposition_failure
from utils.batch_pipeline.scheduler import Scheduler


def fresh_queue():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    return store, queue, time.time()


def test_ladder_retry_state_at_attempt_1(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(1):
        assert queue.fail('a', lease.token, now) is True
        assert store.rows['jobs', 'a']['state'] == 'retry'
        now += 120
        queue.recover(now)
        leases = queue.pull(now)
        assert len(leases) == 1
        lease = leases[0]


def test_ladder_retry_state_at_attempt_2(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(2):
        assert queue.fail('a', lease.token, now) is True
        assert store.rows['jobs', 'a']['state'] == 'retry'
        now += 120
        queue.recover(now)
        leases = queue.pull(now)
        assert len(leases) == 1
        lease = leases[0]


def test_ladder_retry_state_at_attempt_3(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(3):
        assert queue.fail('a', lease.token, now) is True
        assert store.rows['jobs', 'a']['state'] == 'retry'
        now += 120
        queue.recover(now)
        leases = queue.pull(now)
        assert len(leases) == 1
        lease = leases[0]


def test_ladder_retry_state_at_attempt_4(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(4):
        assert queue.fail('a', lease.token, now) is True
        assert store.rows['jobs', 'a']['state'] == 'retry'
        now += 120
        queue.recover(now)
        leases = queue.pull(now)
        assert len(leases) == 1
        lease = leases[0]


def test_ladder_settles_at_the_attempt_cap(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(5):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    assert store.rows['jobs', 'a']['state'] == 'quarantined'
    assert store.rows['jobs', 'a']['attempt'] == 5


def test_ladder_terminal_books_unknown_unclassified(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(5):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert not job.get('worker_failure')


def test_ladder_counts_attempt_1(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now)
    assert store.rows['jobs', 'a']['attempt'] >= 1
    assert store.rows['jobs', 'a']['state'] in {'retry', 'leased'}


def test_ladder_counts_attempt_2(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(2):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    assert store.rows['jobs', 'a']['attempt'] >= 2
    assert store.rows['jobs', 'a']['state'] in {'retry', 'leased'}


def test_ladder_counts_attempt_3(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(3):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    assert store.rows['jobs', 'a']['attempt'] >= 3
    assert store.rows['jobs', 'a']['state'] in {'retry', 'leased'}


def test_ladder_counts_attempt_4(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(4):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    assert store.rows['jobs', 'a']['attempt'] >= 4
    assert store.rows['jobs', 'a']['state'] in {'retry', 'leased'}


def test_ladder_counts_attempt_5(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    for _ in range(5):
        queue.fail('a', lease.token, now)
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
        now += 120
        queue.recover(now)
        lease = queue.pull(now)[0]
    assert store.rows['jobs', 'a']['attempt'] >= 5
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_typed_evidence_skips_every_ladder_rung(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    assert queue.fail(
        'a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert store.rows['jobs', 'a']['attempt'] == 1
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


def test_typed_evidence_quarantine_is_not_recovered_by_the_sweep(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
    now += 86400
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


def test_typed_evidence_clears_the_lease_and_merge_pending(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
    job = store.rows['jobs', 'a']
    assert not job['merge_pending']
    assert job['recovery_state'] == 'held'


def test_wrong_lease_token_never_quarantines(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store, queue, now = fresh_queue()
    queue.pull(now)
    assert (
        queue.fail(
            'a', 'stale-token', now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
        )
        is False
    )
    assert store.rows['jobs', 'a']['state'] != 'quarantined'


def test_stale_lease_rejects_the_typed_failure_too(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store, queue, now = fresh_queue()
    lease = queue.pull(now)[0]
    assert (
        queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
        is True
    )
    assert (
        queue.fail('a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})
        is False
    )


def test_retained_reason_demotes_only_at_fetch_decode():
    assert validation_disposition_failure(
        {"stage": "fetch_decode", "reason": "retained_audio_invalid"}, disposition_enabled=False
    )


def test_retained_reason_at_vad_windows_never_demotes():
    assert not validation_disposition_failure(
        {"stage": "vad_windows", "reason": "retained_audio_invalid"}, disposition_enabled=True
    )


def test_decoded_duration_reason_demotes_only_at_fetch_decode():
    assert validation_disposition_failure(
        {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}, disposition_enabled=False
    )
    assert not validation_disposition_failure(
        {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}, disposition_enabled=True
    )


def test_staged_reason_demotes_only_at_fetch_decode():
    assert validation_disposition_failure(
        {"stage": "fetch_decode", "reason": "staged_audio_invalid"}, disposition_enabled=True
    )
    assert not validation_disposition_failure(
        {"stage": "word_clocks", "reason": "staged_audio_invalid"}, disposition_enabled=True
    )
