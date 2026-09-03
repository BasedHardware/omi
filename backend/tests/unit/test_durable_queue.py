from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from database.durable_queue import (
    OutcomeKind,
    ProcessOutcome,
    QueuePolicy,
    adopt_on_identity,
    decide_attempt,
    drain_isolated,
    oldest_ready_age_seconds,
    ready_sort_key,
    redrive_patch,
)
from utils.durable_queue_metrics import observe_oldest_ready_age
from utils.memory.daily_memory_sweep_queue import drain_sweep_uids

NOW = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
POLICY = QueuePolicy(max_attempts=3, base_backoff_seconds=1, max_backoff_seconds=8)


def test_poison_item_does_not_block_the_item_behind_it():
    processed: list[str] = []

    def process(item: str) -> ProcessOutcome:
        processed.append(item)
        if item == 'poison':
            raise RuntimeError('malformed payload')
        return ProcessOutcome.ack()

    results = drain_isolated(['poison', 'healthy'], process)
    assert processed == ['poison', 'healthy']
    assert results[0].outcome.kind == OutcomeKind.REJECT
    assert results[0].raised is True
    assert 'malformed payload' in (results[0].outcome.error_text or '')
    assert results[1].outcome.kind == OutcomeKind.ACK


def test_poison_reaches_dead_letter_within_budget_with_error_text():
    decision = decide_attempt(
        attempt_count=1,
        outcome=ProcessOutcome.reject('canonical hash mismatch', reason='malformed'),
        policy=POLICY,
        now=NOW,
    )
    assert decision.terminal is True
    assert decision.status == 'dead_letter'
    assert decision.error_text == 'canonical hash mismatch'
    assert decision.reason == 'malformed'

    retry = decide_attempt(
        attempt_count=2,
        outcome=ProcessOutcome.retry('provider timeout', reason='timeout'),
        policy=POLICY,
        now=NOW,
    )
    assert retry.terminal is False
    assert retry.status == 'retrying'
    assert retry.available_at == NOW + timedelta(seconds=2)

    last = decide_attempt(
        attempt_count=3,
        outcome=ProcessOutcome.retry('provider timeout', reason='timeout'),
        policy=POLICY,
        now=NOW,
    )
    assert last.terminal is True
    assert last.error_text == 'provider timeout'


def test_duplicate_by_identity_is_adopted():
    created = adopt_on_identity(existing_id=None, item_id='evt_1')
    adopted = adopt_on_identity(existing_id='evt_1', item_id='evt_1')
    assert created.adopted is False
    assert adopted.adopted is True
    with pytest.raises(ValueError, match='enqueue identity mismatch'):
        adopt_on_identity(existing_id='evt_other', item_id='evt_1')


def test_oldest_ready_age_reflects_the_oldest_item():
    older = NOW - timedelta(hours=3)
    newer = NOW - timedelta(minutes=5)
    age = oldest_ready_age_seconds([newer, older], now=NOW)
    assert age == pytest.approx(3 * 3600)
    assert oldest_ready_age_seconds([], now=NOW) is None


def test_priority_sort_puts_meeting_notes_ahead_of_capture_cards():
    rows = [
        ready_sort_key(priority=2, created_at=NOW, item_id='capture', enable_priority=True),
        ready_sort_key(priority=0, created_at=NOW, item_id='meeting', enable_priority=True),
    ]
    assert sorted(rows)[0][-1] == 'meeting'


def test_redrive_patch_clears_dead_letter_by_identity():
    patch = redrive_patch(now=NOW)
    assert patch['status'] == 'pending'
    assert patch['attempt_count'] == 0
    assert patch['dead_letter_reason'] is None


def test_failures_are_never_acked():
    results = drain_isolated(['x'], lambda _item: ProcessOutcome.reject('hard fail', reason='conflict'))
    assert results[0].outcome.kind != OutcomeKind.ACK


def test_daily_sweep_poison_uid_does_not_block_the_uid_behind_it():
    processed: list[str] = []

    def process(uid: str) -> ProcessOutcome:
        processed.append(uid)
        if uid == 'poison':
            raise RuntimeError('malformed payload')
        return ProcessOutcome.ack()

    acked = drain_sweep_uids(['poison', 'healthy'], process, ready_created_at=[NOW - timedelta(hours=2)], now=NOW)
    assert processed == ['poison', 'healthy']
    assert acked == ['healthy']


def test_daily_sweep_age_gauge_reflects_oldest_ready_item():
    age = oldest_ready_age_seconds([NOW - timedelta(hours=2), NOW - timedelta(minutes=3)], now=NOW)
    observe_oldest_ready_age('daily_memory_sweep', age)
    assert age == pytest.approx(2 * 3600)
