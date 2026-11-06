"""Phase 2a transaction boundary and flag-off write goldens (no cloud access)."""

import copy
import inspect
from datetime import datetime, timezone

import pytest
from google.cloud.firestore_v1 import _helpers

from database import conversations as db
from models.conversation_enums import ConversationStatus as Status
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.transcript_hash import transcript_sha256_for_binding

PATH = ('users', 'synthetic', 'conversations', 'capture')
NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)
KEEP = dict(
    verdict='keep',
    decided_by='policy',
    reason='lifecycle_terminal_default',
    trigger='lifecycle_terminal',
    rules_version=4,
)
DISCARD = dict(
    verdict='discard', decided_by='policy', reason='already_discarded', trigger='lifecycle_terminal', rules_version=4
)


@pytest.fixture
def store(monkeypatch):
    result = StrictFirestore({PATH: {'status': 'processing', 'discarded': False}})
    monkeypatch.setattr(db, 'db', result)
    monkeypatch.setattr(db.firestore, 'transactional', lambda callback: callback)
    for name in (
        'stop_quiet_check_for_conversation',
        'invalidate_people_stats_cache',
        '_sync_conversation_search_index',
        '_delete_conversation_search_index',
    ):
        monkeypatch.setattr(db, name, lambda *a, **k: None)
    monkeypatch.setattr(db, '_stage_notes_identity', lambda *a, **k: None)
    monkeypatch.setattr(db, '_reapply_current_manual_assignments', lambda *a, **k: None)
    from database import recurring_voice_privacy

    monkeypatch.setattr(recurring_voice_privacy, 'filter_processing_write', lambda *a: None)
    monkeypatch.setattr(db.summary_delivery, 'merge_result', lambda *a: None)
    monkeypatch.setattr(db.summary_delivery, 'emit_result', lambda *a: None)
    monkeypatch.setattr(db.processing_backlog, 'stage_transition', lambda *a, **k: False)
    monkeypatch.delenv('CONVERSATION_TERMINAL_FAMILY_MODE', raising=False)
    return result


def persist(payload, **kwargs):
    # Exercise the real transaction owner without the independent write-codec
    # decorators; lifecycle/expiry suites cover that public boundary as well.
    return inspect.unwrap(db.persist_processing_result_with_lifecycle)(
        'synthetic', {'id': 'capture', **payload}, **kwargs
    )


@pytest.mark.parametrize('shape', ['processing_completed', 'merging_completed_discarded', 'processing_live', 'digest'])
def test_flag_off_claim_write_goldens(store, monkeypatch, shape):
    monkeypatch.setenv('CONVERSATION_TERMINAL_FAMILY_MODE', 'off')
    expected, claimed, extra, allow = Status.processing, Status.completed, None, False
    golden = {'status': 'completed', 'relevance_decision': KEEP}
    quiet = []
    monkeypatch.setattr(db, 'restore_quiet_check_in_transaction', lambda *a: quiet.append(a[-1]))
    if shape == 'merging_completed_discarded':
        store.rows[PATH].update(status='merging', discarded=True)
        expected, allow = Status.merging, True
        golden = {'status': 'completed', 'relevance_decision': DISCARD}
    elif shape == 'processing_live':
        claimed = Status.in_progress
        golden = {'status': 'in_progress'}
    elif shape == 'digest':
        store.rows[PATH]['transcript_segments'] = []
        extra = {'client_processing': {'transcript_sha256': 'stale-digest'}, 'language': 'en'}
        golden = {'status': 'completed', 'language': 'en', 'relevance_decision': KEEP}
    assert db.claim_conversation_status('synthetic', 'capture', expected, claimed, extra, allow_discarded=allow)
    assert store.transactions[-1].updates == [(PATH, golden)]
    assert len(quiet) == (shape == 'processing_live')
    if quiet:
        assert quiet[0]['status'] == 'in_progress'


@pytest.mark.parametrize('mode', [None, 'on', 'off'])
def test_completion_classifier_and_legacy_rows(store, monkeypatch, mode):
    if mode is not None:
        monkeypatch.setenv('CONVERSATION_TERMINAL_FAMILY_MODE', mode)
    assert db.claim_conversation_status('synthetic', 'capture', Status.processing, Status.completed)
    row = store.rows[PATH]
    assert row['status'] == 'completed'
    assert row['relevance_decision'] == KEEP
    if mode == 'off':
        assert 'terminal_family' not in row and 'terminal_family_at' not in row
    else:
        assert row['terminal_family'] == 'success'
        assert isinstance(row['terminal_family_at'], datetime)


def test_guards_precede_projection_reads_and_quiet_hooks(store, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('refused CAS must not bind a projection or restore quiet debt')

    monkeypatch.setattr(db, 'extra_updates_with_bound_client_processing', forbidden)
    monkeypatch.setattr(db, 'restore_quiet_check_in_transaction', forbidden)
    store.rows[PATH]['deleted'] = True
    assert not db.claim_conversation_status(
        'synthetic',
        'capture',
        Status.processing,
        Status.in_progress,
        {'language': 'en'},
        expected_fields={'deleted': False},
    )
    assert not store.transactions[-1].has_written


def test_core_does_not_mutate_inputs_or_run_hooks(store, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('pure core called an IO/metric/quiet hook')

    from utils.conversations import terminal_relevance

    monkeypatch.setattr(terminal_relevance, 'stamp_terminal_decision', forbidden)
    monkeypatch.setattr(db, 'restore_quiet_check_in_transaction', forbidden)
    current, extra = copy.deepcopy(store.rows[PATH]), {'language': 'en'}
    before = copy.deepcopy((current, extra))
    updates = db.claim_conversation_status_in_txn(
        current,
        expected_status='processing',
        claimed_status='completed',
        extra_updates=extra,
        terminal_family='success',
        terminal_family_at=NOW,
    )
    assert updates == {
        'status': 'completed',
        'language': 'en',
        'relevance_decision': KEEP,
        'terminal_family': 'success',
        'terminal_family_at': NOW,
    }
    assert (current, extra) == before
    assert store.transactions == []
    assert db.claim_conversation_status_in_txn(current, expected_status='merging', claimed_status='completed') is None


@pytest.mark.parametrize('family', sorted(db.TERMINAL_FAILURE_FAMILIES) + [None])
@pytest.mark.parametrize('status', ['processing', 'completed', 'failed'])
def test_late_persist_keeps_failure_and_merges_content(store, family, status):
    marker = (
        {'terminal_family': family, 'terminal_family_at': NOW} if family else {'finalization_status': 'dead_letter'}
    )
    store.rows[PATH].update(status=status, **marker)
    label = family or 'dead_letter'
    metric = db.TERMINAL_CLAIM_REFUSALS.labels(family=label)
    before = metric._value.get()
    callbacks = []
    assert persist(
        {
            'status': 'completed',
            'terminal_family': 'success',
            'terminal_family_at': 'stale',
            'finalization_status': 'completed',
            'title': 'late content',
        },
        on_first_completion=lambda: callbacks.append(True),
    )
    row = store.rows[PATH]
    assert row['status'] == status
    assert all(row[key] == value for key, value in marker.items())
    assert row['title'] == 'late content'
    assert metric._value.get() == before + 1
    assert callbacks == []
    writes = store.transactions[-1].updates
    assert len(writes) == 1 and 'status' not in writes[0][1]
    assert not store.transactions[-1].sets


def test_persist_flips_content_and_status_in_one_write(store):
    observed = []
    assert persist({'status': 'completed', 'title': 'new content'}, on_first_completion=lambda: observed.append(True))
    assert len(store.transactions) == 1
    tx = store.transactions[0]
    assert tx.sets == [] and len(tx.updates) == 1
    patch = tx.updates[0][1]
    assert patch['title'] == 'new content' and patch['status'] == 'completed'
    assert patch['terminal_family'] == 'success'
    assert observed == [True]


def test_flag_off_persist_write_golden(store, monkeypatch):
    monkeypatch.setenv('CONVERSATION_TERMINAL_FAMILY_MODE', 'off')
    captured = []
    # StrictFirestore deliberately does not simulate general merge=True. Record
    # the exact legacy storage call rather than weakening its semantics.
    tx = store.transaction()
    monkeypatch.setattr(store, 'transaction', lambda: tx)
    monkeypatch.setattr(tx, 'set', lambda ref, data, **kwargs: captured.append((ref.path, data, kwargs)))
    store.rows[PATH]['finalization_status'] = 'dead_letter'
    assert persist({'status': 'completed', 'structured': {'title': 'legacy'}})
    assert captured == [
        (PATH, {'id': 'capture', 'status': 'completed', 'structured': {'title': 'legacy'}}, {'merge': True})
    ]
    assert tx.updates == []


def test_update_mask_matches_legacy_merge_including_empty_maps_and_literal_keys():
    payload = {'structured': {'title': 'notes', 'kept': {}}, 'literal.dot': {'back`tick': 2}, 'list': [1, 2]}
    merge = _helpers.pbs_for_set_with_merge('projects/demo/databases/(default)/documents/users/u', payload, True)[0]
    update = _helpers.pbs_for_update(
        'projects/demo/databases/(default)/documents/users/u', db._processing_result_update_fields(payload), None
    )[0]
    assert set(merge.update_mask.field_paths) == set(update.update_mask.field_paths)
    assert merge.update.fields == update.update.fields


@pytest.mark.parametrize('mode, expected', [(None, True), ('on', True), ('off', False)])
def test_mode_default_and_operator_kill_switch(monkeypatch, mode, expected):
    if mode is None:
        monkeypatch.delenv('CONVERSATION_TERMINAL_FAMILY_MODE', raising=False)
    else:
        monkeypatch.setenv('CONVERSATION_TERMINAL_FAMILY_MODE', mode)
    assert db._terminal_family_serving('synthetic') is expected


def test_refusal_counter_is_not_emitted_on_failed_commit(store, monkeypatch):
    store.rows[PATH]['finalization_status'] = 'dead_letter'
    metric = db.TERMINAL_CLAIM_REFUSALS.labels(family='dead_letter')
    before = metric._value.get()

    def failed_commit(client, callback):
        callback(client.transaction())
        raise RuntimeError('synthetic commit failure')

    monkeypatch.setattr(db, 'run_transactional', failed_commit)
    with pytest.raises(RuntimeError, match='synthetic commit failure'):
        persist({'status': 'completed', 'title': 'late'})
    assert metric._value.get() == before


def test_transaction_retry_resets_refusal_outcome(store, monkeypatch):
    metric = db.TERMINAL_CLAIM_REFUSALS.labels(family='dead_letter')
    before = metric._value.get()
    store.rows[PATH]['finalization_status'] = 'dead_letter'

    def retry(client, callback):
        callback(client.transaction())
        # The first attempt did not commit; the next snapshot is recoverable.
        client.rows[PATH] = {'status': 'processing'}
        return callback(client.transaction())

    monkeypatch.setattr(db, 'run_transactional', retry)
    assert persist({'status': 'completed', 'title': 'recovered'})
    assert metric._value.get() == before
    assert store.rows[PATH]['status'] == 'completed'
    assert store.rows[PATH]['terminal_family'] == 'success'
