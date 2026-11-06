"""Durable retry counters, their atomic receipt, and cached replica mirrors."""

from copy import deepcopy
from types import SimpleNamespace

from google.api_core import exceptions as api
import pytest

from database.batch_final_pass_retry import COUNTER_SHARDS, FinalPassRetries
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import prod_shaped, UID, batch_outcome_counts  # noqa: F401
from tests.unit.test_batch_final_pass_retry import ready, next_wake  # noqa: F401
from utils.conversations import final_pass_retry as retry
from utils.observability import speaker_retry_terminal as metrics

KEY = 'ab' * 32


def samples(collector):
    return {
        (sample.name, tuple(sample.labels.items())): sample.value
        for family in collector.collect()
        for sample in family.samples
    }


def count(collector, outcome):
    return samples(collector).get(('omi_transcription_final_pass_retry_terminal_total', (('outcome', outcome),)), 0)


@pytest.fixture
def durable_store(monkeypatch):
    client = StrictFirestore()
    store = FinalPassRetries(client)
    monkeypatch.setattr(store, '_collection', lambda: client.collection('synthetic-outbox'))
    monkeypatch.setattr(store, '_counter_collection', lambda: client.collection('synthetic-counters'))
    client.rows[('synthetic-outbox', KEY)] = {
        'outcome': 'success',
        'token': 'wake',
        'terminal_pending': True,
        'repair_after': 2000,
    }
    return client, store


@pytest.mark.parametrize('outcome', ['success', 'partial_coverage', 'skipped_retry_exhausted', 'skipped_ineligible'])
def test_real_transaction_closes_receipt_and_increments_once_with_reads_before_writes(durable_store, outcome):
    client, store = durable_store
    client.rows[('synthetic-outbox', KEY)]['outcome'] = outcome
    assert store.take_terminal(KEY, 'wake')
    receipt = client.rows[('synthetic-outbox', KEY)]
    assert not any(field in receipt for field in ('terminal_pending', 'repair_after', 'due_at'))
    counters = client.rows[('synthetic-counters', str(int(KEY[:2], 16) % COUNTER_SHARDS))]
    assert counters == ({} if outcome == 'skipped_ineligible' else {outcome: 1})
    # Receipt and aggregate are both transaction-bound; the strict fixture
    # rejects a counter read after staging the receipt write.
    assert len(client.transactions[0].sets) == 2
    assert not store.take_terminal(KEY, 'wake')
    assert not client.transactions[-1].sets


def test_sdk_commit_reply_loss_does_not_require_local_metric_emission(durable_store, monkeypatch):
    client, store = durable_store
    make_transaction = client.transaction
    transaction = client.transaction()

    def lost_reply():
        raise api.ServiceUnavailable('PRIVATE reply lost after committed writes')

    monkeypatch.setattr(transaction, '_commit', lost_reply)
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction)
    with pytest.raises(api.ServiceUnavailable):
        store.take_terminal(KEY, 'wake')
    # StrictFirestore models transaction ordering, not commit/rollback
    # visibility. Here the deliberately injected commit-then-error state is
    # explicit: both writes persisted before the synthetic reply failed.
    assert client.rows[('synthetic-counters', str(int(KEY[:2], 16) % COUNTER_SHARDS))] == {'success': 1}
    assert 'terminal_pending' not in client.rows[('synthetic-outbox', KEY)]
    snapshot = deepcopy(client.rows)
    monkeypatch.setattr(client, 'transaction', make_transaction)
    assert not store.take_terminal(KEY, 'wake')
    assert client.rows == snapshot


def test_counter_refresh_is_one_fixed_size_bounded_read(durable_store, monkeypatch):
    client, store = durable_store
    calls = []

    def get_all(references, **kwargs):
        calls.append((references, kwargs))
        return [SimpleNamespace(id=ref.id, to_dict=lambda: {'success': 2}) for ref in reversed(references)]

    monkeypatch.setattr(client, 'get_all', get_all)
    result = store.terminal_counts()
    assert set(result) == set(map(str, range(COUNTER_SHARDS)))
    assert len(calls) == 1 and len(calls[0][0]) == COUNTER_SHARDS
    assert calls[0][1] == {'retry': None, 'timeout': 3}


def test_cold_collect_has_no_fabricated_zero_or_firestore_io():
    collector = metrics.RetryTerminals()
    assert samples(collector) == {}
    assert len(collector.describe()) == 2


def test_partial_batch_read_cannot_be_published_as_a_fresh_global_total(durable_store, monkeypatch):
    client, store = durable_store
    monkeypatch.setattr(client, 'get_all', lambda *args, **kwargs: [])
    with pytest.raises(ValueError, match='retry_counter_snapshot_incomplete'):
        store.terminal_counts()


def test_duplicate_and_older_snapshots_do_not_add_or_lower_counts():
    collector = metrics.RetryTerminals()
    collector.publish({'0': {'success': 2}, '1': {'success': 3}}, observed_at=2000)
    first = samples(collector)
    collector.publish({'0': {'success': 2}, '1': {'success': 3}}, observed_at=2000)
    assert samples(collector) == first
    collector.publish({'0': {'success': 1}, '1': {}}, observed_at=1000)
    assert samples(collector) == first
    collector.publish({'0': {'success': 3}, '1': {'success': 4}}, observed_at=2100)
    assert count(collector, 'success') == 7


def test_restarted_replica_exports_same_global_total_without_replaying_rows(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert retry.sweep(now=ready.state.clock[0] + 2000) == 0
    first = samples(metrics.TERMINALS)
    replacement = metrics.RetryTerminals()
    monkeypatch.setattr(metrics, 'TERMINALS', replacement)
    assert samples(replacement) == {}
    assert retry.sweep(now=ready.state.clock[0] + 2000) == 0
    assert samples(replacement) == first and count(replacement, 'success') == 1
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert len(ready.lane.gpu) == len(ready.writes) == 1


def test_failed_refresh_keeps_last_observation_and_recovers_without_rows(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    retry.sweep(now=2000)
    first = samples(metrics.TERMINALS)
    original = ready.state.store.terminal_counts

    def unavailable():
        raise api.ServiceUnavailable('PRIVATE')

    monkeypatch.setattr(ready.state.store, 'terminal_counts', unavailable)
    assert retry.sweep(now=3000) == 0
    assert samples(metrics.TERMINALS) == first
    monkeypatch.setattr(ready.state.store, 'terminal_counts', original)
    assert retry.sweep(now=4000) == 0
    assert count(metrics.TERMINALS, 'success') == 1


def test_counter_read_failure_does_not_prevent_pending_wake_repair(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key, old_token = next_wake(ready.state)
    ready.state.clock[0] = ready.state.rows[key]['repair_after'] + 1

    def unavailable():
        raise api.ServiceUnavailable('PRIVATE')

    monkeypatch.setattr(ready.state.store, 'terminal_counts', unavailable)
    assert retry.sweep(now=ready.state.clock[0]) == 1
    assert ready.state.rows[key]['token'] != old_token
    assert retry.consume(key, old_token)['outcome'] == 'stale'


def test_report_does_not_also_increment_initial_pass_counter(ready):
    from utils.conversations import final_pass_batch as batch

    initial = batch.OUTCOMES.labels(lane='batch', outcome='success')._value.get()
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert batch.OUTCOMES.labels(lane='batch', outcome='success')._value.get() == initial
    retry.sweep(now=2000)
    assert count(metrics.TERMINALS, 'success') == 1
