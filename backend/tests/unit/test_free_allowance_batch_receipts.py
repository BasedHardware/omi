"""Batch chunks release holds while one generation receipt owns exact billed totals."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import free_allowance_leases as ledger
from database import batch_pipeline_projection as projection
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.stt.allowance_batch import observe_billed_batch

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return StrictFirestore({('users', 'u'): {}})


def bill(store, total, *, started=NOW):
    ref = sync_content_ledger_ref(store, 'u', 'content')
    store.rows[ref.path] = {
        'usage_committed_at': NOW,
        'allowance_billing_started_at': started,
        'allowance_billed_seconds': total,
    }


def register(store, *ids):
    for sid in ids:
        ref = ledger.reference('u', f'batch-unit:{sid}', NOW)
        store.rows[('users', 'u', 'free_allowance_operations', ref.key)] = {
            'months': [ref.month],
            'status': 'active',
            'had_refusal': False,
        }
        state = store.rows.setdefault(
            ('users', 'u', 'free_allowance_months', ref.month),
            {'schema_version': 1, 'holds': {}, 'ptt_seconds': 0},
        )
        state['holds'][ref.key] = {'seconds': 2, 'expires_at': NOW.timestamp() + 30}


def receipts(store):
    return [data for path, data in store.rows.items() if len(path) == 4 and path[2] == 'free_allowance_receipts']


def observe(store, ids, *, started=NOW):
    observe_billed_batch(store, 'u', 'content', started, ids, NOW.timestamp())


@pytest.mark.parametrize('registered', [('64',), ('0', '64'), ('31', '32', '64')])
def test_missing_or_mixed_earlier_chunks_cannot_drop_batch_seconds(store, registered):
    bill(store, 17)
    register(store, *registered)
    observe(store, [str(i) for i in range(65)])
    assert sum(row['billed_seconds'] for row in receipts(store)) == 17
    assert len([row for row in receipts(store) if row.get('kind') == 'batch_aggregate']) == 1
    assert store.rows[('users', 'u', 'free_allowance_months', '2026-11')]['holds'] == {}
    observe(store, [str(i) for i in range(65)])
    assert sum(row['billed_seconds'] for row in receipts(store)) == 17


def test_partial_then_full_and_delayed_replays_record_only_cumulative_billing(store):
    register(store, '0')
    bill(store, 3)
    observe(store, ['0'])
    register(store, '64')
    bill(store, 11)
    observe(store, [str(i) for i in range(65)])
    observe(store, ['0'])
    assert sum(row['billed_seconds'] for row in receipts(store)) == 11


def test_full_completion_repairs_an_entirely_missed_partial_observer(store):
    register(store, '0', '64')
    bill(store, 11)
    observe(store, [str(i) for i in range(65)])
    assert sum(row['billed_seconds'] for row in receipts(store)) == 11


def test_lost_first_commit_reply_cannot_assign_total_to_a_later_chunk(store, monkeypatch):
    register(store, '0', '64')
    bill(store, 11)
    actual = ledger.settle_billed
    calls = 0

    def lost(*args, **kwargs):
        nonlocal calls
        result = actual(*args, **kwargs)
        calls += 1
        if calls == 1:
            raise TimeoutError('lost committed response')
        return result

    monkeypatch.setattr(ledger, 'settle_billed', lost)
    observe(store, [str(i) for i in range(65)])
    observe(store, [str(i) for i in range(65)])
    assert sum(row['billed_seconds'] for row in receipts(store)) == 11
    assert store.rows[('users', 'u', 'free_allowance_months', '2026-11')]['holds'] == {}


def test_generation_fence_and_new_generation_are_distinct(store):
    register(store, 'old')
    bill(store, 3)
    observe(store, ['old'])
    next_start = NOW + timedelta(hours=1)
    register(store, 'new')
    bill(store, 2, started=next_start)
    observe(store, ['new'])  # A delayed callback may not borrow the new generation.
    assert len(receipts(store)) == 2
    observe(store, ['new'], started=next_start)
    assert sum(row['billed_seconds'] for row in receipts(store)) == 5


@pytest.mark.parametrize('total', [None, True, -1, float('nan')])
def test_unknown_billing_provenance_retains_holds_and_never_fabricates_zero(store, total):
    register(store, 'one')
    bill(store, total)
    observe(store, ['one'])
    assert receipts(store) == []
    assert store.rows[('users', 'u', 'free_allowance_months', '2026-11')]['holds']


def test_unregistered_paid_or_legacy_operations_do_not_create_batch_receipts(store):
    bill(store, 17)
    observe(store, ['legacy'])
    assert receipts(store) == []


@pytest.mark.parametrize('updates,prior,expected', [(True, 3, 7), (False, 0, 0), (True, None, None)])
def test_writer_provenance_tracks_exact_integer_delta_without_changing_usage(
    store, monkeypatch, updates, prior, expected
):
    monkeypatch.setattr(projection, 'queue_increment', Mock())
    source = {
        'status': 'partial',
        'usage_committed_seconds': 3.8,
        'allowance_billing_started_at': NOW,
        'allowance_billed_seconds': prior,
    }
    accounting = {'charged': 3.8, 'updates': {'transcription_seconds': 4} if updates else {}, 'hour': '2026-11-12-12'}
    tx = Mock()
    ref = sync_content_ledger_ref(store, 'u', 'content')
    owner = SimpleNamespace(owner_id='u')
    projection.ProjectionStore(SimpleNamespace(client=store))._commit_usage(
        tx, ref, source, owner, accounting, 7.9, NOW.timestamp()
    )
    metadata = tx.update.call_args.args[1]
    assert metadata['allowance_billed_seconds'] == expected
    assert metadata['allowance_billing_started_at'] == NOW
    if updates:
        assert tx.set.call_args.args[1] == accounting['updates']
    else:
        tx.set.assert_not_called()
