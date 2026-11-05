"""Batch-store contention attribution and advisory probe parity.

Two production contracts are pinned here:

1. Every ``FirestoreStore.run`` resolves a static caller label before a
   transaction opens. The anonymous ``batch_pipeline_store`` default used
   to absorb dozens of worker-hot call sites, so an
   ``operation=batch_pipeline_store ... outcome=exhausted`` storm
   (x709/30m in production) could not name the caller that burned the
   five-attempt budget. The default is now ``None`` and an unlabeled run
   is refused fail-closed; every site carries a literal label.
2. Single-document advisory reads leave the transactional ladder
   entirely via ``Store.probe``. A read-only body takes no locks and
   writes nothing, but its read set still aborts on every concurrent
   write to the probed document — on hot job documents that converts one
   busy owner into a shared-budget exhaustion storm. Probes are strongly
   consistent point reads; every write decision re-verifies its fences
   inside the transaction that acts.
"""

import ast
import contextlib
import logging
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_transaction_labels import (
    current_operation,
    pull_operation,
    shadow_operation,
    store_operation,
)
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.leader import PUMP_RECOVERY, LeaderLease

BACKEND = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class _DictTx:
    """Minimal transaction view over plain rows for caller stubs."""

    def __init__(self, rows):
        self.rows = rows
        self.writes = {}

    def get(self, table, key):
        return deepcopy(self.writes.get((table, key), self.rows.get((table, key), {})))

    def put(self, table, key, value):
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table, key, fields):
        self.writes.setdefault((table, key), {}).update(deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


class RecordingStore:
    """Records the operation label of every run and every probe key."""

    def __init__(self, rows=None, namespace='batch_pipeline_dev'):
        self.rows = dict(rows or {})
        self.namespace = namespace
        self.labels = []
        self.probes = []

    def run(self, body, *, operation=None):
        self.labels.append(operation if operation is not None else current_operation())
        tx = _DictTx(self.rows)
        result = body(tx)
        self.rows.update(tx.writes)
        return result

    def probe(self, table, key):
        self.probes.append((table, key))
        return deepcopy(self.rows.get((table, key), {}))


def job_row(state='ready'):
    return {'state': state, 'owner_id': 'owner', 'conversation_id': None, 'privacy_generation': None}


def dev_store(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    # Privacy fences are their own contract suite; label/probe parity needs
    # the write path to flush, not the owner's account state.
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', lambda *args, **kwargs: 0)
    return storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())


def plant(store, table, key, row):
    """Arrange a committed row directly, bypassing the flush privacy fence.

    Privacy fences are a separate contract (batch_pipeline_privacy); probe
    parity only needs committed rows under the production document layout.
    """
    from database.batch_pipeline_store import document_ref

    reference = document_ref(store.client, store.namespace, table, key)
    store.client.rows[tuple(reference.path)] = deepcopy(row)


# --------------------------------------------------------------------------
# Section 1 — the fail-closed label contract on the real store
# --------------------------------------------------------------------------


def test_unlabeled_run_is_refused_before_any_transaction(monkeypatch):
    store = dev_store(monkeypatch)
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None)


def test_unlabeled_run_is_refused_before_the_client_is_constructed(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=object())
    # A refusable call must not build a transaction factory first.
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None)


def test_router_recover_quarantine_probes():
    assert _contains('routers/batch_pipeline.py', "service.store.probe, 'jobs', body.segment_id")


def test_database_intake_module_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_intake.py') == []


def test_router_batch_pipeline_module_has_no_unlabeled_store_run():
    assert _unlabeled('routers/batch_pipeline.py') == []


def test_pull_operation_rejects_unknown_operations():
    with pytest.raises(ValueError, match='static pull operation'):
        with pull_operation('peek', 'scheduler_03'):
            pass


def test_pull_operation_rejects_unknown_shards():
    with pytest.raises(ValueError, match='static pull operation'):
        with pull_operation('pull', 'scheduler_99'):
            pass


def test_shadow_operation_rejects_unknown_operations():
    with pytest.raises(ValueError, match='static shadow store operation'):
        with shadow_operation('peek'):
            pass


def test_labeled_non_contention_errors_are_never_replayed(caplog):
    attempts = {'n': 0}

    def operation(tx):
        attempts['n'] += 1
        raise KeyError('schema drift')

    with pytest.raises(KeyError):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='batch_recovery_settle', sleep=lambda seconds: None
        )
    assert attempts['n'] == 1


def test_expired_chains_keep_the_three_chain_ceiling_without_a_deadline():
    from google.api_core.exceptions import InvalidArgument

    attempts = {'n': 0}

    def operation(tx):
        attempts['n'] += 1
        raise InvalidArgument('transaction has expired')

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='batch_recovery_settle', sleep=lambda seconds: None
        )
    assert attempts['n'] == 3


def test_equal_jitter_delay_stays_bounded_for_labeled_attempts():
    from database.firestore_transaction_retry import equal_jitter_delay

    assert equal_jitter_delay(1, random_value=lambda: 1.0) == 0.2
    assert equal_jitter_delay(3, random_value=lambda: 1.0) == 0.8
    assert equal_jitter_delay(9, random_value=lambda: 1.0) == 1.0


def test_docs_declare_the_failure_class():
    docs = (BACKEND / 'docs/batch-store-contention-attribution.md').read_text()
    assert (
        'Failure-Class: FC-advisory-probe-reads-and-unlabeled-store-operations-exhaust-the-anonymous-contention-budget'
        in docs
    )


def test_explicit_labels_compose_with_the_ambient_pull_context(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    with pull_operation('pull', 'scheduler_01'):
        store.run(lambda tx: None, operation='batch_test_explicit')
    assert seen == ['batch_test_explicit']


def test_probe_returns_a_plain_dict_not_a_snapshot(monkeypatch):
    store = dev_store(monkeypatch)
    store.run(lambda tx: tx.put('jobs', 'seg', job_row()), operation='batch_test_store')
    assert type(store.probe('jobs', 'seg')) is dict


def test_document_ref_routes_content_through_the_sync_ledger_collection(monkeypatch):
    from database.batch_pipeline_store import document_ref
    from utils.sync.stage import collection_name

    store = dev_store(monkeypatch)
    reference = storage.document_ref(store.client, store.namespace, 'content', 'uid/content')
    assert reference.path == ('users', 'uid', collection_name('sync_content_ledger'), 'content')


def test_unlabeled_run_writes_nothing(monkeypatch):
    store = dev_store(monkeypatch)
    with contextlib.suppress(ValueError):
        store.run(lambda tx: tx.put('jobs', 'x', job_row()))
    assert store.probe('jobs', 'x') == {}


def test_explicit_operation_label_reaches_the_retry_ladder(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    store.run(lambda tx: tx.put('jobs', 'labeled', job_row()), operation='batch_test_store')
    assert seen == ['batch_test_store']


def test_ambient_store_operation_context_labels_the_run(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    with store_operation('batch_test_ambient'):
        store.run(lambda tx: None)
    assert seen == ['batch_test_ambient']


def test_explicit_label_wins_over_the_ambient_context(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    with store_operation('batch_test_ambient'):
        store.run(lambda tx: None, operation='batch_test_explicit')
    assert seen == ['batch_test_explicit']


def test_kill_switch_path_also_requires_a_label(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None)


def test_kill_switch_path_accepts_the_explicit_label(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    assert store.run(lambda tx: tx.put('merge_holds', 'x', {'held': True}), operation='batch_test_store') is None
    assert store.probe('merge_holds', 'x') == {'held': True}


def test_current_operation_defaults_to_none():
    assert current_operation() is None


def test_anonymous_default_label_is_retired(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    with pytest.raises(ValueError):
        store.run(lambda tx: None)
    assert 'batch_pipeline_store' not in seen


@pytest.mark.parametrize('bad', [None, '', 123, 'Bad', 'BAD', '1lead', 'has space', 'a' * 65])
def test_require_operation_label_refuses_non_literal_labels(bad):
    from database.batch_pipeline_transaction_labels import require_operation_label

    with pytest.raises(ValueError, match='static store operation label required'):
        require_operation_label(bad)


def test_require_operation_label_accepts_the_pattern_boundaries():
    from database.batch_pipeline_transaction_labels import require_operation_label

    assert require_operation_label('a') == 'a'
    assert require_operation_label('a' * 64) == 'a' * 64


def test_store_run_refuses_an_invalid_explicit_label(monkeypatch):
    store = dev_store(monkeypatch)
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None, operation='Not A Label')


def test_store_operation_context_restores_after_exit():
    with store_operation('batch_outer'):
        with store_operation('batch_inner'):
            assert current_operation() == 'batch_inner'
        assert current_operation() == 'batch_outer'
    assert current_operation() is None


def test_pull_operation_still_names_its_shard():
    with pull_operation('pull', 'scheduler_03'):
        assert current_operation() == 'batch_pull shard=scheduler_03'


def test_the_composed_serving_pull_label_is_a_valid_run_label(monkeypatch):
    store = dev_store(monkeypatch)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(factory, operation, *, operation_name, **kwargs):
        seen.append(operation_name)
        return original(factory, operation, operation_name=operation_name, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    with pull_operation('pull', 'scheduler_03'):
        store.run(lambda tx: None)
    assert seen == ['batch_pull shard=scheduler_03']


def test_a_composed_label_from_an_unlisted_shard_is_refused():
    from database.batch_pipeline_transaction_labels import require_operation_label

    with pytest.raises(ValueError, match='static store operation label required'):
        require_operation_label('batch_pull shard=scheduler_99')


def test_shadow_operation_still_names_its_operation():
    with shadow_operation('reserve'):
        assert current_operation() == 'batch_shadow_reserve'


def test_exhausted_ladder_log_names_the_caller(caplog):
    attempts = {'n': 0}

    def operation(tx):
        attempts['n'] += 1
        raise Aborted('busy')

    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(), operation, operation_name='batch_recovery_settle', sleep=lambda seconds: None
            )
    exhausted = [
        record
        for record in caplog.records
        if 'outcome=exhausted' in record.getMessage() and record.levelno == logging.ERROR
    ]
    assert attempts['n'] == 5
    assert any('operation=batch_recovery_settle attempt=5/5' in record.getMessage() for record in exhausted)


def test_recovered_ladder_log_names_the_caller(caplog):
    attempts = {'n': 0}

    def operation(tx):
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise Aborted('busy')
        return 7

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert (
            run_with_transaction_contention_retry(
                lambda: object(), operation, operation_name='batch_recovery_prepare', sleep=lambda seconds: None
            )
            == 7
        )
    recovered = [record for record in caplog.records if 'outcome=recovered' in record.getMessage()]
    assert attempts['n'] == 2
    assert any('operation=batch_recovery_prepare attempt=2/5' in record.getMessage() for record in recovered)


def test_deadline_exhausted_log_names_the_caller(caplog):
    ticks = iter([0.0, 0.0, 100.0, 100.0, 100.0])

    def operation(tx):
        raise Aborted('busy')

    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='batch_merge_hold_release',
                deadline=50.0,
                sleep=lambda seconds: None,
                monotonic=lambda: next(ticks, 1000.0),
            )
    assert any(
        'operation=batch_merge_hold_release' in record.getMessage()
        and 'outcome=deadline_exhausted' in record.getMessage()
        for record in caplog.records
    )


# --------------------------------------------------------------------------
# Section 2 — the probe contract on the real store
# --------------------------------------------------------------------------


def test_probe_reads_the_committed_document(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'jobs', 'seg', job_row())
    assert store.probe('jobs', 'seg') == job_row()


def test_probe_missing_document_reads_empty_dict(monkeypatch):
    store = dev_store(monkeypatch)
    assert store.probe('jobs', 'absent') == {}


def test_probe_sees_the_transactional_write_of_the_same_layout(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'content', 'owner/content', {'status': 'processing'})
    assert store.probe('content', 'owner/content') == {'status': 'processing'}


def test_probe_and_transaction_resolve_conversation_rows_identically(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'conversations', 'owner/conv', {'status': 'completed'})
    with store_operation('batch_test_store'):
        store.run(lambda tx: tx.patch('conversations', 'owner/conv', {'record_lane_owner': 'batch_sync_v1'}))
    assert store.probe('conversations', 'owner/conv') == {'record_lane_owner': 'batch_sync_v1', 'status': 'completed'}
    with store_operation('batch_test_store'):
        assert store.run(lambda tx: tx.get('conversations', 'owner/conv')) == store.probe('conversations', 'owner/conv')


def test_probe_is_a_private_copy(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'jobs', 'seg', job_row())
    seen = store.probe('jobs', 'seg')
    seen['state'] = 'committed'
    assert store.probe('jobs', 'seg') == job_row()


def test_probe_never_opens_a_transaction(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'jobs', 'seg', job_row())
    seen = []
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    original = StrictFirestoreDocument.get

    def recording_get(reference, *args, **kwargs):
        seen.append(kwargs.get('transaction'))
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', recording_get)
    assert store.probe('jobs', 'seg') == job_row()
    assert seen == [None]


def test_probe_reads_do_not_abort_on_a_concurrent_write(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'jobs', 'seg', job_row())
    first = store.probe('jobs', 'seg')
    plant(store, 'jobs', 'seg', job_row('leased'))
    # A point read between two competing commits never joins their read set.
    assert store.probe('jobs', 'seg') == job_row('leased')
    assert first == job_row()


def test_probe_document_module_helper_matches_the_store_method(monkeypatch):
    store = dev_store(monkeypatch)
    plant(store, 'jobs', 'seg', job_row())
    assert storage.probe_document(store.client, store.namespace, 'jobs', 'seg') == store.probe('jobs', 'seg')
    assert storage.probe_document(store.client, store.namespace, 'jobs', 'absent') == {}


def test_document_ref_matches_the_transactional_layout_per_table(monkeypatch):
    from database.batch_pipeline_store import document_ref

    store = dev_store(monkeypatch)
    for table, key in (('jobs', 'seg'), ('results', 'seg'), ('owners', 'hashed'), ('merge_holds', 'owner')):
        assert storage.document_ref(store.client, store.namespace, table, key).id == key


def test_document_ref_routes_conversations_through_the_users_path(monkeypatch):
    from database.batch_pipeline_store import document_ref

    store = dev_store(monkeypatch)
    reference = storage.document_ref(store.client, store.namespace, 'conversations', 'uid/conv')
    assert reference.path == ('users', 'uid', 'conversations', 'conv')


@pytest.mark.parametrize(
    'table', ['jobs', 'results', 'owners', 'intakes', 'merge_holds', 'artifacts', 'shadow_jobs', 'control']
)
def test_probe_covers_every_batch_table_namespace(monkeypatch, table):
    store = dev_store(monkeypatch)
    assert store.probe(table, 'absent') == {}
    row = job_row() if table in {'jobs', 'results'} else {'v': 1}
    plant(store, table, 'row', row)
    assert store.probe(table, 'row') == row


def test_pipeline_sim_store_implements_the_same_probe_surface():
    from testing.pipeline_sim.store import SimStore

    sim = SimStore(None)
    assert sim.probe('jobs', 'absent') == {}
    sim.rows[('jobs', 'seg')] = job_row()
    assert sim.probe('jobs', 'seg') == job_row()
    assert sim.probe('jobs', 'seg') is not sim.rows[('jobs', 'seg')]


def test_pipeline_sim_probe_is_a_copy(monkeypatch):
    from testing.pipeline_sim.store import SimStore

    sim = SimStore(None)
    sim.rows[('jobs', 'seg')] = job_row()
    seen = sim.probe('jobs', 'seg')
    seen['state'] = 'committed'
    assert sim.probe('jobs', 'seg') == job_row()


def test_postgres_sim_store_accepts_the_operation_kwarg():
    from testing.pipeline_sim.postgres_store import PgSimStore

    assert 'operation' in PgSimStore.run.__code__.co_varnames


def test_batch_replay_runner_accepts_the_operation_kwarg():
    from testing.batch_replay.runner import ResultTransactionLog

    assert 'operation' in ResultTransactionLog.run.__code__.co_varnames


# --------------------------------------------------------------------------
# Section 3 — the static attribution contract
# --------------------------------------------------------------------------

_CONTEXT_NAMES = {'store_operation', 'shadow_operation', 'pull_operation'}


def _is_context_with(node):
    return isinstance(node, (ast.With, ast.AsyncWith)) and any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Name)
        and item.context_expr.func.id in _CONTEXT_NAMES
        for item in node.items
    )


def _store_run_calls(node, in_context, found):
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == 'run'
            and (
                (isinstance(func.value, ast.Name) and func.value.id.endswith('store'))
                or (isinstance(func.value, ast.Attribute) and func.value.attr == 'store')
            )
        ):
            label = None
            for keyword in node.keywords:
                if keyword.arg == 'operation' and isinstance(keyword.value, ast.Constant):
                    label = keyword.value.value
            found.append((label, in_context))
    if isinstance(node, (ast.With, ast.AsyncWith)):
        here = in_context or _is_context_with(node)
        for child in ast.iter_child_nodes(node):
            _store_run_calls(child, here, found)
        return
    for child in ast.iter_child_nodes(node):
        _store_run_calls(child, in_context, found)


def _calls(relative_path):
    found = []
    _store_run_calls(ast.parse((BACKEND / relative_path).read_text()), False, found)
    return found


def _explicit_label(relative_path, label):
    return sum(1 for name, _context in _calls(relative_path) if name == label)


def _unlabeled(relative_path):
    return [(name, context) for name, context in _calls(relative_path) if name is None and not context]


# Every explicit label introduced by this change, one pin per site.


def test_batch_final_pass_plan_is_labeled():
    assert _explicit_label('database/batch_final_pass.py', 'batch_final_pass_plan') == 1


def test_artifact_missing_apply_is_labeled():
    assert _explicit_label('database/batch_pipeline_artifact_missing.py', 'batch_artifact_missing_apply') == 1


def test_artifact_missing_evidence_is_labeled():
    assert _explicit_label('database/batch_pipeline_artifact_missing.py', 'batch_artifact_missing_evidence') == 1


def test_artifact_missing_restore_is_labeled():
    assert _explicit_label('database/batch_pipeline_artifact_missing.py', 'batch_artifact_missing_restore') == 1


def test_content_ledger_accept_is_labeled():
    assert _explicit_label('database/batch_pipeline_intake.py', 'batch_content_ledger_accept') == 1


def test_language_shadow_authorize_is_labeled():
    assert _explicit_label('database/batch_pipeline_language_shadow.py', 'batch_language_shadow_authorize') == 1


def test_language_shadow_claim_is_labeled():
    assert _explicit_label('database/batch_pipeline_language_shadow.py', 'batch_language_shadow_claim') == 1


def test_language_shadow_release_is_labeled():
    assert _explicit_label('database/batch_pipeline_language_shadow.py', 'batch_language_shadow_release') == 1


def test_paid_attempt_settle_is_labeled():
    assert _explicit_label('database/batch_pipeline_paid_attempt.py', 'batch_paid_attempt_settle') == 1


def test_job_policy_load_is_labeled():
    assert _explicit_label('database/batch_pipeline_policy.py', 'batch_job_policy_load') == 1


def test_recovery_policy_refresh_is_labeled():
    assert _explicit_label('database/batch_pipeline_policy.py', 'batch_recovery_policy_refresh') == 1


def test_stage_policy_load_is_labeled():
    assert _explicit_label('database/batch_pipeline_policy.py', 'batch_stage_policy_load') == 1


def test_recovery_claim_wake_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_claim_wake') == 1


def test_recovery_extend_wake_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_extend_wake') == 1


def test_recovery_hold_duration_limit_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_hold_duration_limit') == 1


def test_recovery_hold_invalid_manifest_is_labeled():
    assert (
        _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_hold_invalid_manifest') == 1
    )


def test_recovery_observe_vad_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_observe_vad') == 1


def test_recovery_paid_takeover_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_paid_takeover') == 1


def test_recovery_prepare_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_prepare') == 1


def test_recovery_retry_missing_result_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_retry_missing_result') == 1


def test_recovery_settle_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_settle') == 1


def test_recovery_shorten_wake_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_shorten_wake') == 1


def test_recovery_silence_complete_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_silence_complete') == 1


def test_recovery_silence_prepare_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_silence_prepare') == 1


def test_recovery_start_is_labeled():
    assert _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_start') == 1


def test_recovery_start_duration_limited_is_labeled():
    assert (
        _explicit_label('database/batch_pipeline_quarantine_recovery.py', 'batch_recovery_start_duration_limited') == 1
    )


def test_recognizer_receipt_is_labeled():
    assert _explicit_label('database/batch_pipeline_recognizer_receipts.py', 'batch_recognizer_receipt') == 1


def test_speech_redrive_census_is_labeled():
    assert _explicit_label('database/batch_pipeline_speech_redrive.py', 'batch_speech_redrive_census') == 1


def test_speech_redrive_observe_vad_is_labeled():
    assert _explicit_label('database/batch_pipeline_speech_redrive.py', 'batch_speech_redrive_observe_vad') == 1


def test_speech_redrive_prepare_is_labeled():
    assert _explicit_label('database/batch_pipeline_speech_redrive.py', 'batch_speech_redrive_prepare') == 1


def test_speech_redrive_settle_is_labeled():
    assert _explicit_label('database/batch_pipeline_speech_redrive.py', 'batch_speech_redrive_settle') == 1


def test_speech_redrive_start_is_labeled():
    assert _explicit_label('database/batch_pipeline_speech_redrive.py', 'batch_speech_redrive_start') == 1


def test_artifact_stage_is_labeled():
    assert _explicit_label('database/batch_pipeline_staging.py', 'batch_artifact_stage') == 1


def test_terminal_empty_complete_is_labeled():
    assert _explicit_label('database/batch_pipeline_terminal_empty.py', 'batch_terminal_empty_complete') == 1


def test_terminal_empty_prepare_is_labeled():
    assert _explicit_label('database/batch_pipeline_terminal_empty.py', 'batch_terminal_empty_prepare') == 1


def test_partial_precheck_is_labeled():
    assert _explicit_label('database/record_partial.py', 'batch_partial_precheck') == 1


def test_admission_read_is_labeled():
    assert _contains('utils/batch_pipeline/admission.py', "operation='batch_admission_read'")


def test_admission_seal_is_labeled():
    assert _contains('utils/batch_pipeline/admission.py', "operation='batch_admission_seal'")


def test_cap_hold_check_is_labeled():
    assert _explicit_label('utils/batch_pipeline/cap_hold_admission.py', 'batch_cap_hold_check') == 1


def test_intake_deleted_proof_is_labeled():
    assert _contains('utils/batch_pipeline/intake.py', "operation='batch_intake_deleted_proof'")


def test_intake_status_is_labeled():
    assert _explicit_label('utils/batch_pipeline/intake.py', 'batch_intake_status') == 1


def test_leader_lease_is_labeled():
    assert _explicit_label('utils/batch_pipeline/leader.py', 'batch_leader_lease') == 1


def test_live_record_register_is_labeled():
    assert _explicit_label('utils/batch_pipeline/live.py', 'batch_live_record_register') == 1


def test_live_defer_is_labeled():
    assert _contains('utils/batch_pipeline/live.py', "operation='batch_live_defer'")


def test_live_receipt_read_is_labeled():
    assert _contains('utils/batch_pipeline/live_upload.py', "operation='batch_live_receipt_read'")


def test_live_alias_write_is_labeled():
    assert _contains('utils/batch_pipeline/live_upload.py', "operation='batch_live_alias_write'")


def test_merge_hold_release_is_labeled():
    assert _explicit_label('utils/batch_pipeline/merge.py', 'batch_merge_hold_release') == 1


def test_provider_fence_is_labeled():
    assert _explicit_label('utils/batch_pipeline/provider_stt.py', 'batch_provider_fence') == 1


def test_seal_register_is_labeled():
    assert _explicit_label('utils/batch_pipeline/record_seal_nojob.py', 'batch_seal_register') == 1


def test_recover_requeue_is_labeled():
    assert _explicit_label('utils/batch_pipeline/scheduler.py', 'batch_recover') == 1


def test_cap_hold_status_is_labeled():
    assert _explicit_label('utils/sync/cap_hold_reservations.py', 'batch_cap_hold_status') == 1


def test_every_explicit_store_label_is_a_literal_pattern_match():
    import re

    paths = {
        'database/batch_final_pass.py',
        'database/batch_pipeline_artifact_missing.py',
        'database/batch_pipeline_intake.py',
        'database/batch_pipeline_language_shadow.py',
        'database/batch_pipeline_paid_attempt.py',
        'database/batch_pipeline_policy.py',
        'database/batch_pipeline_quarantine_recovery.py',
        'database/batch_pipeline_recognizer_receipts.py',
        'database/batch_pipeline_speech_redrive.py',
        'database/batch_pipeline_staging.py',
        'database/batch_pipeline_terminal_empty.py',
        'database/record_partial.py',
        'utils/batch_pipeline/admission.py',
        'utils/batch_pipeline/cap_hold_admission.py',
        'utils/batch_pipeline/intake.py',
        'utils/batch_pipeline/leader.py',
        'utils/batch_pipeline/live.py',
        'utils/batch_pipeline/live_upload.py',
        'utils/batch_pipeline/merge.py',
        'utils/batch_pipeline/provider_stt.py',
        'utils/batch_pipeline/record_seal_nojob.py',
        'utils/batch_pipeline/scheduler.py',
        'utils/sync/cap_hold_reservations.py',
    }
    pattern = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
    for path in sorted(paths):
        for name, _context in _calls(path):
            if name is not None:
                assert pattern.fullmatch(name), (path, name)


# No module may reintroduce an anonymous store transaction.


def test_quarantine_recovery_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_quarantine_recovery.py') == []


def test_speech_redrive_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_speech_redrive.py') == []


def test_terminal_empty_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_terminal_empty.py') == []


def test_artifact_missing_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_artifact_missing.py') == []


def test_language_shadow_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_language_shadow.py') == []


def test_policy_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_policy.py') == []


def test_staging_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_staging.py') == []


def test_paid_attempt_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_paid_attempt.py') == []


def test_recognizer_receipts_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_pipeline_recognizer_receipts.py') == []


def test_record_partial_has_no_unlabeled_store_run():
    assert _unlabeled('database/record_partial.py') == []


def test_batch_final_pass_has_no_unlabeled_store_run():
    assert _unlabeled('database/batch_final_pass.py') == []


def test_admission_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/admission.py') == []


def test_leader_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/leader.py') == []


def test_merge_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/merge.py') == []


def test_cap_hold_admission_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/cap_hold_admission.py') == []


def test_record_seal_nojob_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/record_seal_nojob.py') == []


def test_provider_stt_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/provider_stt.py') == []


def test_scheduler_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/scheduler.py') == []


# --------------------------------------------------------------------------
# Section 4 — the labels reach the store at runtime
# --------------------------------------------------------------------------


def test_merge_release_hold_runs_under_its_label():
    from utils.batch_pipeline.merge import OrderedMerge

    store = RecordingStore(rows={('merge_holds', 'owner'): {'held': True}})
    merge = OrderedMerge(store)
    merge.release_hold('owner', force=True)
    assert store.labels == ['batch_merge_hold_release']
    assert store.rows[('merge_holds', 'owner')]['held'] is False


def test_leader_lease_runs_under_its_label():
    store = RecordingStore()
    lease = LeaderLease(store, PUMP_RECOVERY, ttl_seconds=60, clock=lambda: 100)
    assert lease.acquire()
    assert store.labels == ['batch_leader_lease']


def test_paid_attempt_settle_runs_under_its_label():
    from database.batch_pipeline_paid_attempt import mark_spent

    store = RecordingStore(
        rows={('jobs', 'sid'): {'recovery_state': 'running', 'recovery': {'token': 't', 'paid_state': 'attempted'}}}
    )
    # The intent fence may refuse synthetic rows; the label is recorded either way.
    with contextlib.suppress(Exception):
        mark_spent(store, 'sid', 't', 'recovery', 10)
    assert store.labels == ['batch_paid_attempt_settle']


def test_stage_policy_load_runs_under_its_label():
    from database.batch_pipeline_policy import load_stage_policy

    store = RecordingStore(rows={('jobs', 'sid'): {'owner_id': 'owner', 'policy_parts': {}}})
    with contextlib.suppress(Exception):
        load_stage_policy(store, 'sid', 'projection')
    assert store.labels == ['batch_stage_policy_load']


def test_job_policy_load_runs_under_its_label():
    from database.batch_pipeline_policy import load_job_policy

    store = RecordingStore(rows={('jobs', 'sid'): {'owner_id': 'owner', 'policy_parts': {}}})
    with contextlib.suppress(Exception):
        load_job_policy(store, 'sid')
    assert store.labels == ['batch_job_policy_load']


def test_recovery_policy_refresh_runs_under_its_label(monkeypatch):
    import database.batch_pipeline_policy as policy_module

    fresh = SimpleNamespace(recovery_enabled=True, policy_id='p1', to_dict=lambda: {'recovery_enabled': True})
    monkeypatch.setattr(policy_module, 'resolve_stage_policy', lambda owner_id, stage: fresh)
    store = RecordingStore(
        rows={
            (
                'jobs',
                'sid',
            ): {
                'owner_id': 'owner',
                'state': 'quarantined',
                'recovery_state': 'held',
                'recovery': None,
                'policy_parts': {'recovery': {'recovery_enabled': False}},
                'policy_part_sources': {'recovery': 'recorded'},
            }
        }
    )
    with contextlib.suppress(Exception):
        policy_module.refresh_disabled_recovery(store, 'sid', 'owner')
    assert store.labels == ['batch_recovery_policy_refresh']


def test_artifact_stage_runs_under_its_label():
    from database.batch_pipeline_staging import reap_one

    store = RecordingStore(rows={('artifacts', 'key'): {'kind': 'audio'}})
    from datetime import datetime, timezone

    with contextlib.suppress(Exception):
        reap_one(store, 'key', datetime.now(timezone.utc))
    assert store.labels == ['batch_artifact_stage']


def test_partial_precheck_runs_under_its_label():
    from database.record_partial import continuation_refusal

    store = RecordingStore(
        rows={
            ('conversations', 'owner/conv'): {'discarded': False},
            ('jobs', 'seg'): {'state': 'record_pending'},
        }
    )
    pending = {'owner_id': 'owner', 'conversation_id': 'conv', 'segment_id': 'seg'}
    assert continuation_refusal(store, pending) is None
    assert store.labels == ['batch_partial_precheck']


def test_cap_hold_check_runs_under_its_label():
    from utils.batch_pipeline.cap_hold_admission import handoff_projected

    store = RecordingStore(
        rows={
            ('intakes', 'bp_x'): {'owner_id': 'owner', 'content_id': 'content', 'segment_ids': ['s1']},
            ('content', 'owner/content'): {'status': 'completed'},
        }
    )
    # A synthetic result may refuse the validity check; the label is recorded either way.
    with contextlib.suppress(Exception):
        handoff_projected('owner', 'bp_x', store=store)
    assert store.labels == ['batch_cap_hold_check']


def test_intake_status_runs_under_its_label():
    from utils.batch_pipeline.intake import durable_status

    store = RecordingStore(
        rows={
            ('intakes', 'bp_x'): {'lane': 'batch', 'total_files': 1, 'segment_ids': ['s1']},
            ('jobs', 's1'): {'state': 'ready'},
        }
    )
    with contextlib.suppress(Exception):
        durable_status(store, 'owner', 'bp_x')
    assert store.labels == ['batch_intake_status']


def test_final_pass_plan_runs_under_its_label():
    from database.batch_final_pass import load_reference

    store = RecordingStore(
        rows={
            ('jobs', 'seg'): {'owner_id': 'owner', 'projection_binding': {'segment_ids': ['seg']}},
            ('results', 'seg'): {},
        }
    )
    with contextlib.suppress(Exception):
        load_reference(store, 'owner', 'seg', 'conv')
    assert store.labels == ['batch_final_pass_plan']


def test_language_shadow_claim_runs_under_its_label(monkeypatch):
    import database.batch_pipeline_language_shadow as shadow_module

    monkeypatch.setattr(shadow_module, 'language_only_enabled', lambda: True)
    monkeypatch.setattr(shadow_module, 'shadow_percent', lambda: 100)
    monkeypatch.setattr(shadow_module, 'language_probe_limit', lambda: 10)
    store = RecordingStore()
    shadow = shadow_module.LanguageShadowStore(store, clock=lambda: 7200)
    item = SimpleNamespace(owner_id='owner', segment_id='seg', privacy_generation=0, conversation_id=None)
    assert shadow.reserve(item) is True
    assert store.labels == ['batch_language_shadow_claim']


def test_language_shadow_release_runs_under_its_label(monkeypatch):
    import database.batch_pipeline_language_shadow as shadow_module

    monkeypatch.setattr(shadow_module, 'language_only_enabled', lambda: True)
    monkeypatch.setattr(shadow_module, 'shadow_percent', lambda: 100)
    monkeypatch.setattr(shadow_module, 'language_probe_limit', lambda: 10)
    store = RecordingStore(
        rows={
            ('shadow_lid_probes', 'k'): {'reserved_at': 1},
            ('shadow_lid_spend', 'active'): {'slots': [{'key': 'k', 'until': 10}]},
        }
    )
    shadow = shadow_module.LanguageShadowStore(store, clock=lambda: 5)
    item = SimpleNamespace(owner_id='owner', segment_id='seg', privacy_generation=0, conversation_id=None)
    key = __import__('hashlib').sha256(b'owner\0seg').hexdigest()
    store.rows[('shadow_lid_probes', key)] = {'reserved_at': 1}
    store.rows[('shadow_lid_spend', 'active')] = {'slots': [{'key': key, 'until': 10}]}
    shadow.release(item)
    assert store.labels == ['batch_language_shadow_release']


# --------------------------------------------------------------------------
# Section 5 — advisory probes left the ladder
# --------------------------------------------------------------------------


def _contains(relative_path, snippet):
    return snippet in (BACKEND / relative_path).read_text()


def test_pump_owner_lookup_probes():
    assert _contains('utils/batch_pipeline/pump.py', "self.scheduler.store.probe, 'jobs', segment")


def test_merge_release_set_probes():
    assert _contains('utils/batch_pipeline/merge.py', "self.store.probe('jobs', segment_id)")


def test_merge_next_release_probes():
    assert _contains('utils/batch_pipeline/merge.py', "job = self.store.probe('jobs', segment)")


def test_merge_committed_result_probes():
    assert _contains('utils/batch_pipeline/merge.py', "self.store.probe('results', segment_id)")


def test_serving_complete_probes():
    assert _contains('utils/batch_pipeline/serving.py', "self.store.probe('jobs', result.segment_id)")


def test_serving_maintenance_probes():
    assert _contains('utils/batch_pipeline/serving.py', "job = self.store.probe('jobs', segment)")


def test_live_drain_probes():
    assert _contains('utils/batch_pipeline/live.py', "store.probe, 'jobs', segment")


def test_live_upload_route_probe_reads_outside_transactions():
    assert _contains('utils/batch_pipeline/live_upload.py', "store.probe, 'content', f'{uid}/{content_id}'")


def test_intake_prior_upload_probes():
    assert _contains('utils/batch_pipeline/intake.py', "store.probe, 'content', f'{uid}/{content_id}'")


def test_intake_repair_owner_proof_probes():
    assert _contains('utils/batch_pipeline/intake.py', "row = store.probe('content', f'{uid}/{content_id}')")


def test_artifact_reupload_lineage_probes():
    assert _contains('utils/batch_pipeline/artifact_reupload.py', "store.probe('intakes', binding.job_id)")


def test_record_partial_ledger_wait_probes():
    assert _contains('utils/batch_pipeline/record_partial.py', "store.run, lambda tx: tx.get('content'") is False
    assert _contains('utils/batch_pipeline/record_partial.py', "store.probe, 'content'")


def test_seal_sweeper_job_classification_probes():
    assert _contains('utils/batch_pipeline/record_seal_sweeper.py', "job = store.probe('jobs', job_id)")


def test_seal_sweeper_row_classification_probes():
    assert _contains(
        'utils/batch_pipeline/record_seal_sweeper.py', "row = store.probe('conversations', f'{uid}/{cid}')"
    )


def test_seal_repair_job_planning_probes():
    assert _contains('utils/batch_pipeline/record_seal_repair.py', "_job_state(store.probe('jobs', job_id))")


def test_seal_repair_row_planning_probes():
    assert _contains('utils/batch_pipeline/record_seal_repair.py', "row = store.probe('conversations', f'{uid}/{cid}')")


def test_seal_cluster_repair_job_probes():
    assert _contains('utils/batch_pipeline/record_seal_cluster_repair.py', "job = store.probe('jobs', job_id)")


def test_seal_cluster_repair_row_probes():
    assert _contains(
        'utils/batch_pipeline/record_seal_cluster_repair.py', "row = store.probe('conversations', f'{uid}/{cid}')"
    )


def test_merge_release_set_reads_outside_the_ladder():
    from utils.batch_pipeline.merge import OrderedMerge

    store = RecordingStore(rows={('jobs', 'seg'): {'projection_binding': {'segment_ids': ['seg', 's2', 's3']}}})
    merge = OrderedMerge(store)
    assert merge.release_set('seg') == ['seg', 's2', 's3']
    assert store.probes == [('jobs', 'seg')]
    assert store.labels == []


def test_merge_next_release_reads_outside_the_ladder():
    from utils.batch_pipeline.merge import OrderedMerge

    store = RecordingStore(
        rows={
            ('jobs', 'a'): {'owner_key': 'owner', 'merge_pending': True, 'state': 'leased'},
            ('jobs', 'b'): {'owner_key': 'owner', 'merge_pending': True, 'state': 'result_ready'},
        }
    )
    merge = OrderedMerge(store)
    assert merge._next_release('owner', ['a', 'b']) == 'b'
    assert store.probes == [('jobs', 'a'), ('jobs', 'b')]
    assert store.labels == []


def test_merge_committed_result_reads_outside_the_ladder():
    from utils.batch_pipeline.merge import OrderedMerge

    store = RecordingStore(rows={('results', 'seg'): {'projection': {'state': 'ready'}}})
    merge = OrderedMerge(store)
    assert merge.committed_result('seg') == {'projection': {'state': 'ready'}}
    assert store.probes == [('results', 'seg')]
    assert store.labels == []


def test_artifact_reupload_lineage_reads_outside_the_ladder():
    import utils.batch_pipeline.artifact_reupload as reupload

    store = RecordingStore(rows={('intakes', 'job1'): {'repair_lineage': {}}})
    binding = SimpleNamespace(job_id='job1')
    with contextlib.suppress(Exception):
        reupload._repair_evidence(store, binding, [], None)
    assert store.probes == [('intakes', 'job1')]
    assert store.labels == []


def _sweep_read_store():
    from utils.batch_pipeline.record_seal_sweeper import SweepReadStore

    document = Mock()
    document.get.return_value = SimpleNamespace(exists=False, to_dict=lambda: {})
    client = Mock()
    client.collection.return_value.document.return_value = document
    budget = Mock()
    budget.timeout.return_value = 1.0
    return SweepReadStore(SimpleNamespace(client=client, namespace='batch_pipeline_dev'), budget), budget


def test_sweep_read_store_probe_delegates_to_its_budget_checked_get():
    store, _budget = _sweep_read_store()
    assert store.probe('jobs', 'absent') == {}


def test_sweep_read_store_probe_keeps_the_read_budget():
    store, budget = _sweep_read_store()
    store.probe('jobs', 'absent')
    budget.check.assert_called_once()


def test_live_module_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/live.py') == []


def test_live_upload_module_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/live_upload.py') == []


def test_utils_intake_module_has_no_unlabeled_store_run():
    assert _unlabeled('utils/batch_pipeline/intake.py') == []


def test_merge_release_set_hint_reads_missing_rows_as_empty():
    from utils.batch_pipeline.merge import OrderedMerge

    store = RecordingStore()
    merge = OrderedMerge(store)
    assert merge.release_set('absent') == ['absent']
    assert store.probes == [('jobs', 'absent')]
    assert store.labels == []


def test_the_label_is_recorded_even_when_the_body_refuses():
    store = RecordingStore()

    def refusing(tx):
        raise ProjectionBlocked('synthetic refusal')

    with pytest.raises(ProjectionBlocked):
        store.run(refusing, operation='batch_test_store')
    assert store.labels == ['batch_test_store']


def test_the_ambient_label_is_recorded_even_when_the_body_refuses():
    store = RecordingStore()

    def refusing(tx):
        raise ProjectionBlocked('synthetic refusal')

    with store_operation('batch_test_ambient'):
        with pytest.raises(ProjectionBlocked):
            store.run(refusing)
    assert store.labels == ['batch_test_ambient']
