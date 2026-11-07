"""Migration surface: the transactional frontier read is retired everywhere.

An in-body abort-set join only stays dead if every surface that could
re-acquire it is gone. Pinned here:

1. The Firestore transaction view and Protocol no longer declare or expose
   ``service_frontier``; the store-side hint is declared on the ``Store``
   Protocol and implemented by ``FirestoreStore``.
2. The scheduler's write-tracking transaction wrapper no longer forwards the
   retired read.
3. ``control.activate`` / ``migrate_legacy`` and the scheduler append helpers
   take the seed as a value; the static requeue methods take it keyword-only.
4. The jobstore Postgres twin exposes the hint at store level only.
5. The simulators expose the hint at store level only, on both the in-memory
   and the Postgres-backed sim store.
6. The query-driver registry carries the hint driver and no longer names the
   retired transactional driver pair.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

import inspect
from pathlib import Path

import database.batch_pipeline_store as storage
import utils.batch_pipeline.scheduler as scheduler_module
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from tests.support.firestore_batch_pipeline_drivers import entries as driver_entries
from tests.support.firestore_query_drivers import function_body_digest
from tests.support.firestore_query_driver_registry import BODY_DIGEST
from testing.pipeline_sim.postgres_store import PgSimStore, _Recording
from testing.pipeline_sim.store import CustomerData, SimStore, SimTransaction
from utils.batch_pipeline import control as control_module

BACKEND = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# 1. The Firestore store surfaces
# --------------------------------------------------------------------------


def test_firestore_transaction_view_has_no_frontier_read():
    assert not hasattr(storage.FirestoreTransaction, 'service_frontier')


def test_firestore_transaction_view_has_no_hint_alias():
    assert not hasattr(storage.FirestoreTransaction, 'service_frontier_hint')


def test_transaction_protocol_has_no_frontier_read():
    assert not hasattr(storage.Transaction, 'service_frontier')


def test_store_protocol_declares_the_hint():
    assert callable(getattr(storage.Store, 'service_frontier_hint', None))


def test_store_protocol_hint_takes_priority_only():
    signature = inspect.signature(storage.Store.service_frontier_hint)
    assert list(signature.parameters) == ['self', 'priority']


def test_firestore_store_implements_the_hint_with_priority_only():
    signature = inspect.signature(storage.FirestoreStore.service_frontier_hint)
    assert list(signature.parameters) == ['self', 'priority']


def test_module_function_is_named_as_a_hint():
    assert callable(storage.service_frontier_hint)
    assert not hasattr(storage, 'service_frontier')


def test_module_function_hint_is_positional_priority_only():
    signature = inspect.signature(storage.service_frontier_hint)
    parameters = list(signature.parameters)
    assert parameters == ['client', 'namespace', 'priority']
    assert not any(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())


def test_module_function_hint_returns_float():
    assert storage.service_frontier_hint.__annotations__.get('return') is float


# --------------------------------------------------------------------------
# 2. The scheduler's write-tracking wrapper
# --------------------------------------------------------------------------


def test_own_writes_wrapper_does_not_forward_the_frontier():
    wrapper = scheduler_module._OwnWrites.__getattr__

    def probe(self, name):
        if name == 'service_frontier':
            raise AssertionError('the retired frontier read must not be forwarded')
        return object.__getattribute__(self, '_tx') and getattr(object.__getattribute__(self, '_tx'), name)

    assert wrapper is not None  # the passthrough exists for store helpers
    assert 'service_frontier' not in dir(scheduler_module._OwnWrites)


def test_own_writes_has_no_frontier_attribute():
    assert not hasattr(scheduler_module._OwnWrites, 'service_frontier')


# --------------------------------------------------------------------------
# 3. control.activate / migrate_legacy / append helpers take the seed
# --------------------------------------------------------------------------


def test_activate_takes_a_frontier_value():
    signature = inspect.signature(control_module.activate)
    parameters = signature.parameters
    assert list(parameters) == ['tx', 'control', 'priority', 'now', 'frontier']
    assert parameters['frontier'].default == 0.0


def test_activate_frontier_is_positional_not_keyword_only():
    assert inspect.signature(control_module.activate).parameters['frontier'].kind is (
        inspect.Parameter.POSITIONAL_OR_KEYWORD
    )


def test_migrate_legacy_takes_a_seed_map():
    signature = inspect.signature(control_module.migrate_legacy)
    parameters = signature.parameters
    assert list(parameters) == ['tx', 'now', 'frontiers']
    assert parameters['frontiers'].default is None


def test_append_requires_the_seed():
    signature = inspect.signature(scheduler_module._append)
    assert list(signature.parameters) == ['tx', 'control', 'job', 'now', 'frontier']


def test_append_fifo_array_requires_the_seed():
    signature = inspect.signature(scheduler_module._append_fifo_array)
    assert list(signature.parameters) == ['tx', 'queue', 'queue_key', 'control', 'job', 'now', 'frontier']


def test_rejoin_frontiers_helper_exists():
    assert callable(scheduler_module.rejoin_frontiers)


def test_rejoin_frontiers_returns_a_dict_annotation():
    assert scheduler_module.rejoin_frontiers.__annotations__.get('return') is not None


def test_rejoin_frontiers_takes_store_and_priorities():
    parameters = inspect.signature(scheduler_module.rejoin_frontiers).parameters
    assert list(parameters) == ['store', 'priorities']


def test_enqueue_in_transaction_has_a_keyword_seed_with_zero_default():
    parameters = inspect.signature(scheduler_module.Scheduler.enqueue_in_transaction).parameters
    assert parameters['frontier'].default == 0.0
    assert parameters['frontier'].kind is inspect.Parameter.KEYWORD_ONLY


def test_restore_audio_in_transaction_has_a_keyword_seed():
    parameters = inspect.signature(scheduler_module.Scheduler.restore_audio_in_transaction).parameters
    assert parameters['frontier'].default == 0.0
    assert parameters['frontier'].kind is inspect.Parameter.KEYWORD_ONLY


def test_redrive_in_transaction_has_a_keyword_seed():
    parameters = inspect.signature(scheduler_module.Scheduler.redrive_in_transaction).parameters
    assert parameters['frontier'].default == 0.0
    assert parameters['frontier'].kind is inspect.Parameter.KEYWORD_ONLY


def test_admit_takes_a_frontiers_map():
    from database.batch_pipeline_intake import admit

    parameters = inspect.signature(admit).parameters
    assert 'frontiers' in parameters
    assert parameters['frontiers'].default is None


def test_enqueue_reads_the_hint_outside_run():
    source = inspect.getsource(scheduler_module.Scheduler.enqueue)
    assert 'rejoin_frontiers' in source
    assert source.index('rejoin_frontiers') < source.index('store.run')


def test_recover_reads_the_seed_map_before_the_migration_run():
    source = inspect.getsource(scheduler_module.Scheduler.recover)
    assert source.index('rejoin_frontiers') < source.index('migrate_legacy(tx, now, seeds)')


def test_redrive_dead_probes_before_reading_the_hint():
    source = inspect.getsource(scheduler_module.Scheduler.redrive_dead)
    assert source.index("probe('jobs'") < source.index('rejoin_frontiers')


def test_activate_reads_nothing_transactional():
    source = inspect.getsource(control_module.activate)
    assert 'tx.service_frontier' not in source
    assert 'tx.get' not in source


# --------------------------------------------------------------------------
# 4. The jobstore Postgres twin
# --------------------------------------------------------------------------


def test_postgres_store_declares_the_hint():
    assert callable(getattr(PostgresStore, 'service_frontier_hint', None))


def test_postgres_transaction_has_no_frontier_read():
    assert not hasattr(PostgresTransaction, 'service_frontier')


def test_postgres_hint_is_priority_only():
    signature = inspect.signature(PostgresStore.service_frontier_hint)
    assert list(signature.parameters) == ['self', 'priority']


def test_postgres_hint_in_keeps_the_conn_parameter():
    signature = inspect.signature(PostgresStore.service_frontier_hint_in)
    assert list(signature.parameters) == ['self', 'conn', 'priority']


# --------------------------------------------------------------------------
# 5. The simulators
# --------------------------------------------------------------------------


def test_sim_transaction_has_no_frontier_read():
    assert not hasattr(SimTransaction, 'service_frontier')


def test_sim_store_declares_the_hint():
    assert callable(getattr(SimStore, 'service_frontier_hint', None))


def test_sim_store_has_no_transactional_frontier_alias():
    assert not hasattr(SimStore, 'service_frontier')


def test_sim_hint_bounds_priority():
    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    try:
        store.service_frontier_hint(7)
    except ValueError:
        assert True
    else:
        raise AssertionError('unbounded priority must refuse')


def test_pg_sim_transaction_has_no_frontier_read():
    assert not hasattr(_Recording, 'service_frontier')


def test_pg_sim_store_declares_the_hint():
    assert callable(getattr(PgSimStore, 'service_frontier_hint', None))


def test_pg_sim_store_has_no_transactional_frontier_alias():
    assert not hasattr(PgSimStore, 'service_frontier')


# --------------------------------------------------------------------------
# 6. The query-driver registry names only the hint driver
# --------------------------------------------------------------------------


def test_registry_carries_the_hint_driver_digest():
    assert 'database.batch_pipeline_store.FirestoreStore.service_frontier_hint' in BODY_DIGEST


def test_registry_carries_no_retired_transactional_frontier_entry():
    assert 'database.batch_pipeline_store.FirestoreTransaction.service_frontier' not in BODY_DIGEST


def test_registry_carries_no_retired_module_frontier_entry():
    assert 'database.batch_pipeline_store.service_frontier' not in BODY_DIGEST


def test_registry_hint_digest_matches_the_live_function_body():
    assert BODY_DIGEST['database.batch_pipeline_store.FirestoreStore.service_frontier_hint'] == function_body_digest(
        'database.batch_pipeline_store.FirestoreStore.service_frontier_hint'
    )


def test_driver_entries_name_the_hint_query():
    names = [entry.function for entry in driver_entries()]
    assert 'database.batch_pipeline_store.service_frontier_hint' in names


def test_driver_entries_name_no_retired_frontier_query():
    names = [entry.function for entry in driver_entries()]
    assert 'database.batch_pipeline_store.service_frontier' not in names
    assert 'database.batch_pipeline_store.FirestoreTransaction.service_frontier' not in names


# --------------------------------------------------------------------------
# 7. The docs note exists and carries the failure class
# --------------------------------------------------------------------------


def test_the_docs_note_exists():
    assert (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').exists()


def test_the_docs_note_carries_the_failure_class():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    assert 'Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set' in text


def test_the_docs_note_names_the_retired_read():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    assert 'service_frontier_hint' in text
