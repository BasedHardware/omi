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
from database.durable_queue_age import QUEUE_AGE_SAMPLERS, sample_store_wide_oldest_ready_ages
from utils.durable_queue_metrics import publish_sampled_queue_oldest_ready_ages
from utils.metrics import OMI_QUEUE_NAMES, generate_latest
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

    acked = drain_sweep_uids(['poison', 'healthy'], process)
    assert processed == ['poison', 'healthy']
    assert acked == ['healthy']


def test_daily_sweep_age_gauge_reflects_oldest_ready_item():
    age = oldest_ready_age_seconds([NOW - timedelta(hours=2), NOW - timedelta(minutes=3)], now=NOW)
    assert age == pytest.approx(2 * 3600)


def test_queue_names_match_store_wide_samplers():
    assert set(OMI_QUEUE_NAMES) == set(QUEUE_AGE_SAMPLERS)


def test_store_wide_age_is_min_created_at_across_the_bounded_page():
    class _Snap:
        def __init__(self, payload: dict):
            self._payload = payload

        def to_dict(self) -> dict:
            return self._payload

    class _Query:
        def where(self, *args, **kwargs):
            return self

        def limit(self, _limit: int):
            return self

        def stream(self):
            return [
                _Snap(
                    {
                        'created_at': NOW - timedelta(hours=4),
                        'status': 'pending',
                        'delivery_state': 'ready',
                        'event_type': 'vector_repair_purge',
                    }
                ),
                _Snap(
                    {
                        'created_at': NOW - timedelta(hours=1),
                        'status': 'pending',
                        'delivery_state': 'ready',
                        'event_type': 'vector_repair_purge',
                    }
                ),
            ]

    class _Client:
        def collection_group(self, _name: str) -> _Query:
            return _Query()

    ages = sample_store_wide_oldest_ready_ages(
        now=NOW,
        firestore_client=_Client(),
        finalization_summary={'oldest_nonterminal_age_seconds': 12},
    )
    assert ages['memory_outbox'] == pytest.approx(4 * 3600)
    assert ages['daily_summary_hour_groups'] == 0.0
    assert ages['daily_memory_sweep'] == 0.0
    assert ages['conversation_finalization_jobs'] == 12.0


def test_sampler_failure_leaves_the_queue_absent():
    class _Boom:
        def collection_group(self, _name: str):
            raise RuntimeError('firestore unavailable')

    ages = sample_store_wide_oldest_ready_ages(
        now=NOW,
        firestore_client=_Boom(),
        finalization_summary={'oldest_nonterminal_age_seconds': 1},
    )
    assert 'memory_outbox' not in ages
    assert ages['daily_memory_sweep'] == 0.0
    assert ages['conversation_finalization_jobs'] == 1.0


def test_publisher_emits_labeled_samples_only_after_a_sample():
    publish_sampled_queue_oldest_ready_ages({'memory_outbox': 99.5})
    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{' in exported
    assert 'memory_outbox' in exported


def test_chat_first_fetch_order_uses_ready_sort_key():
    from database.chat_first_intent_queue import sort_ready_intents
    from types import SimpleNamespace

    intents = [
        SimpleNamespace(intent_id='capture', created_at=NOW),
        SimpleNamespace(intent_id='meeting', created_at=NOW),
    ]
    ordered = sort_ready_intents(intents, priority_of=lambda intent: 0 if intent.intent_id == 'meeting' else 2)
    assert [intent.intent_id for intent in ordered] == ['meeting', 'capture']
