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
    assert age == 3 * 3600
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


def test_daily_sweep_age_gauge_reflects_oldest_ready_item():
    age = oldest_ready_age_seconds([NOW - timedelta(hours=2), NOW - timedelta(minutes=3)], now=NOW)
    assert age == 2 * 3600


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

        def select(self, fields):
            assert 'payload' not in fields
            return self

        def limit(self, _limit: int):
            return self

        def stream(self):
            return [
                _Snap(
                    {
                        'created_at': NOW - timedelta(hours=4),
                        'queued_at': (NOW - timedelta(hours=4)).isoformat(),
                        'status': 'pending',
                        'delivery_state': 'ready',
                        'event_type': 'vector_repair_purge',
                    }
                ),
                _Snap(
                    {
                        'created_at': NOW - timedelta(hours=1),
                        'queued_at': (NOW - timedelta(hours=1)).isoformat(),
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
    assert ages['memory_outbox'] == 4 * 3600
    assert ages['daily_summary_hour_groups'] == 0.0
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


@pytest.mark.parametrize(
    'payload,expected',
    [
        ({'available_at': NOW + timedelta(minutes=1)}, []),
        ({'available_at': NOW - timedelta(minutes=1)}, [NOW - timedelta(days=60)]),
        ({'status': 'processing', 'claimed_at': NOW - timedelta(seconds=299)}, []),
        ({'status': 'processing', 'claimed_at': NOW - timedelta(seconds=300)}, [NOW - timedelta(days=60)]),
        ({'status': 'processing'}, [NOW - timedelta(days=60)]),
    ],
)
def test_age_sampler_excludes_future_retries_and_live_leases_but_keeps_abandoned_work(payload, expected):
    from database.durable_queue_age import _created_ats_from_page

    assert (
        _created_ats_from_page(
            [{'created_at': NOW - timedelta(days=60), **payload}], created_at_field='created_at', now=NOW
        )
        == expected
    )


@pytest.mark.parametrize(
    'payload,ready',
    [
        ({'available_at': (NOW + timedelta(seconds=1)).replace(tzinfo=None)}, False),
        ({'available_at': NOW.replace(tzinfo=None)}, True),
        ({'status': 'processing', 'claimed_at': (NOW - timedelta(seconds=299)).replace(tzinfo=None)}, False),
        ({'status': 'processing', 'claimed_at': (NOW - timedelta(seconds=300)).replace(tzinfo=None)}, True),
        ({'status': 'processing', 'lease_expires_at': NOW + timedelta(seconds=1)}, False),
        ({'status': 'processing', 'lease_expires_at': NOW}, True),
        ({'status': 'in_progress', 'lease_expires_at': (NOW + timedelta(seconds=1)).isoformat()}, False),
        ({'status': 'in_progress', 'lease_expires_at': NOW.isoformat()}, True),
        ({'available_at': (NOW + timedelta(seconds=1)).isoformat()}, False),
        ({'available_at': NOW.isoformat().replace('+00:00', 'Z')}, True),
    ],
)
def test_queue_timestamp_normalization_and_lease_expiry(payload, ready):
    from database.durable_queue_age import _created_ats_from_page

    created = NOW - timedelta(hours=2)
    result = _created_ats_from_page([{'created_at': created, **payload}], created_at_field='created_at', now=NOW)
    assert result == ([created] if ready else [])


def test_bad_document_does_not_drop_healthy_age():
    from database.durable_queue_age import _created_ats_from_page

    class BrokenSnapshot:
        def to_dict(self):
            raise ValueError('bad metadata')

    failures = []
    created = NOW - timedelta(hours=2)
    result = _created_ats_from_page(
        [BrokenSnapshot(), {'available_at': 'invalid'}, {'created_at': created}],
        created_at_field='created_at',
        now=NOW,
        failures=failures,
    )
    assert result == [created]
    assert len(failures) == 2


class _PagedAgeClient:
    """Model implicit document-name ordering, status equality and field masks."""

    def __init__(self, records):
        self.records = records
        self.reads = 0
        self.statuses = []
        self.masks = []

    def collection_group(self, collection):
        client = self

        class Query:
            def __init__(self):
                self.rows = list(enumerate(client.records))
                self.fields = []
                self.cap = 0

            def where(self, *, filter):
                client.statuses.append(filter.value)
                self.rows = [(i, row) for i, row in self.rows if row.get(filter.field_path) == filter.value]
                return self

            def select(self, fields):
                self.fields = fields
                client.masks.append(fields)
                return self

            def limit(self, cap):
                self.cap = cap
                return self

            def start_after(self, snapshot):
                self.rows = [(i, row) for i, row in self.rows if i > snapshot.position]
                return self

            def stream(self):
                from types import SimpleNamespace

                rows = self.rows[: self.cap]
                client.reads += len(rows)
                return [
                    SimpleNamespace(position=i, to_dict=lambda row=row: {k: row[k] for k in self.fields if k in row})
                    for i, row in rows
                ]

        return Query()


@pytest.mark.parametrize('blocked', ['future_retry', 'live_lease', 'other_event'])
def test_sampler_refills_filtered_page(blocked):
    from database.durable_queue_age import _sample_status_page

    spec = QUEUE_AGE_SAMPLERS['vector_repair_outbox' if blocked == 'other_event' else 'candidate_integration_outbox']
    status = 'processing' if blocked == 'live_lease' else 'pending'
    ready = {
        'status': status,
        'created_at': NOW - timedelta(days=60),
        'queued_at': (NOW - timedelta(days=60)).isoformat(),
        'event_type': 'vector_repair_purge',
    }
    filtered = (
        {**ready, 'available_at': (NOW + timedelta(hours=1)).isoformat()}
        if blocked == 'future_retry'
        else ({**ready, 'claimed_at': NOW} if blocked == 'live_lease' else {**ready, 'event_type': 'other'})
    )
    client = _PagedAgeClient([filtered] * 200 + [ready])
    assert _sample_status_page(client, spec, now=NOW) == [NOW - timedelta(days=60)]
    assert client.reads == 201
    assert all('payload' not in fields and 'lease_expires_at' in fields for fields in client.masks)


def test_capped_filtered_sample_is_unknown_and_bounded(monkeypatch):
    from database import durable_queue_age

    spec = QUEUE_AGE_SAMPLERS['candidate_integration_outbox']
    monkeypatch.setattr(durable_queue_age, 'QUEUE_AGE_SAMPLERS', {'candidate_integration_outbox': spec})
    filtered = {'status': 'failed', 'created_at': NOW, 'available_at': NOW + timedelta(hours=1)}
    client = _PagedAgeClient([filtered] * 1000 + [{'status': 'failed', 'created_at': NOW - timedelta(days=60)}])
    assert durable_queue_age.sample_store_wide_oldest_ready_ages(now=NOW, firestore_client=client) == {}
    assert client.reads == 1000


def test_exhausted_filtered_sample_proves_empty():
    from database.durable_queue_age import _sample_status_page

    client = _PagedAgeClient([{'status': 'failed', 'available_at': NOW + timedelta(hours=1)}] * 200)
    assert _sample_status_page(client, QUEUE_AGE_SAMPLERS['candidate_integration_outbox'], now=NOW) == []
    assert client.reads == 200


def test_malformed_empty_sample_is_unknown():
    from database.durable_queue_age import _sample_status_page

    client = _PagedAgeClient([{'status': 'pending', 'available_at': 'bad'}])
    assert _sample_status_page(client, QUEUE_AGE_SAMPLERS['memory_outbox'], now=NOW) is None


@pytest.mark.parametrize(
    'queue,status,timestamp_field',
    [
        ('memory_outbox', 'processing', 'created_at'),
        ('vector_repair_outbox', 'in_progress', 'queued_at'),
    ],
)
def test_sampler_queries_expired_lease_status(queue, status, timestamp_field):
    from database.durable_queue_age import _sample_status_page

    created = NOW - timedelta(days=60)
    client = _PagedAgeClient(
        [
            {
                'status': status,
                timestamp_field: created.isoformat(),
                'event_type': 'vector_repair_purge',
                'lease_expires_at': NOW.isoformat(),
            }
        ]
    )
    assert _sample_status_page(client, QUEUE_AGE_SAMPLERS[queue], now=NOW) == [created]
    assert status in client.statuses


@pytest.mark.parametrize('initial_age', [None, 0, 99])
def test_unknown_sample_removes_stale_age_and_recovers(initial_age):
    if initial_age is not None:
        publish_sampled_queue_oldest_ready_ages({'memory_outbox': initial_age})
    publish_sampled_queue_oldest_ready_ages({})
    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{queue="memory_outbox"}' not in exported
    assert 'omi_queue_oldest_ready_sample_unknown{queue="memory_outbox"} 1.0' in exported
    publish_sampled_queue_oldest_ready_ages({'memory_outbox': None})
    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{queue="memory_outbox"} 0.0' in exported
    assert 'omi_queue_oldest_ready_sample_unknown{queue="memory_outbox"} 0.0' in exported


@pytest.mark.parametrize(
    'metadata,expected_hours',
    [
        ({'status': 'processing', 'lease_expires_at': NOW - timedelta(hours=7)}, 7),
        ({'status': 'processing', 'claimed_at': NOW - timedelta(hours=8)}, 8),
        ({'status': 'pending', 'event_type': 'vector_repair_purge', 'queued_at': NOW - timedelta(hours=9)}, 9),
        ({'status': 'pending', 'available_at': NOW - timedelta(hours=10)}, 10),
        ({'status': 'processing', 'created_at': NOW - timedelta(hours=12), 'lease_expires_at': NOW}, 12),
    ],
)
def test_memory_sampler_ages_canonical_and_vector_rows_without_creation_time(metadata, expected_hours):
    from database.durable_queue_age import _sample_status_page

    result = _sample_status_page(_PagedAgeClient([metadata]), QUEUE_AGE_SAMPLERS['memory_outbox'], now=NOW)
    assert result == [NOW - timedelta(hours=expected_hours)]


@pytest.mark.parametrize('include_ready', [False, True])
def test_cap_with_other_event_types_is_unknown_even_with_partial_ready_proof(include_ready, monkeypatch):
    from database import durable_queue_age

    ready = {'status': 'pending', 'event_type': 'vector_repair_purge', 'queued_at': NOW - timedelta(hours=7)}
    skipped = {'status': 'pending', 'event_type': 'memory_change'}
    rows = ([ready] if include_ready else [skipped]) + [skipped] * 999 + [ready]
    client = _PagedAgeClient(rows)
    monkeypatch.setattr(
        durable_queue_age, 'QUEUE_AGE_SAMPLERS', {'vector_repair_outbox': QUEUE_AGE_SAMPLERS['vector_repair_outbox']}
    )
    publish_sampled_queue_oldest_ready_ages({'vector_repair_outbox': 0})
    ages = sample_store_wide_oldest_ready_ages(now=NOW, firestore_client=client)
    assert ages == {}
    assert client.reads == 1000
    publish_sampled_queue_oldest_ready_ages(ages)
    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{queue="vector_repair_outbox"}' not in exported
    assert 'omi_queue_oldest_ready_sample_unknown{queue="vector_repair_outbox"} 1.0' in exported


def test_document_failure_without_proof_invalidates_previous_zero(monkeypatch):
    from database import durable_queue_age

    monkeypatch.setattr(durable_queue_age, 'QUEUE_AGE_SAMPLERS', {'memory_outbox': QUEUE_AGE_SAMPLERS['memory_outbox']})
    publish_sampled_queue_oldest_ready_ages({'memory_outbox': 0})
    ages = sample_store_wide_oldest_ready_ages(now=NOW, firestore_client=_PagedAgeClient([{'status': 'pending'}]))
    assert ages == {}
    publish_sampled_queue_oldest_ready_ages(ages)
    exported = generate_latest().decode()
    assert 'omi_queue_oldest_ready_age_seconds{queue="memory_outbox"}' not in exported
    assert 'omi_queue_oldest_ready_sample_unknown{queue="memory_outbox"} 1.0' in exported
