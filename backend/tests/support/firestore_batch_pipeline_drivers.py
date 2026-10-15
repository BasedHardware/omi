"""Executable query coverage for the dormant batch pipeline's stage namespaces."""

from unittest.mock import patch
from datetime import datetime, timezone

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    return (
        DriverEntry(
            'database.batch_pipeline_staging.unsettled',
            domains={'namespace': namespaces},
            neutrals={
                'before': (datetime(2026, 10, 15, tzinfo=timezone.utc), 'timestamp operand only'),
                'limit': (100, 'bounded page size only'),
            },
        ),
        DriverEntry(
            'utils.sync.reprocess.sweep',
            neutrals={'now': (100.0, 'UTC time operand only'), 'limit': (100, 'bounded page size only')},
            patchers=(lambda client: patch('utils.sync.reprocess.owns_runtime', return_value=True),),
        ),
        DriverEntry(
            'database.batch_pipeline_store.projection_pending',
            domains={'namespace': namespaces},
            neutrals={'limit': (100, 'bounded page size only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.projection_pending',
            covered_by=('database.batch_pipeline_store.projection_pending',),
            reason='thin store adapter forwards namespace and bounded page size unchanged',
            expect_observed=False,
            body_digest='351a3ea949d6033cf3f2003805681af4af223cd0db4a12dc2869e70fb2a74d59',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.first_pending',
            covered_by=('database.batch_pipeline_store.first_pending',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='48a4a9544add4433487df790e5884203eec835b9f8b16ed977c4743b88b596ea',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.due',
            covered_by=('database.batch_pipeline_store.due',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='6082abc15cee6736e23fa3554fbaa74ce65f751082a884e67416eda0757bc5ea',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.oldest',
            covered_by=('database.batch_pipeline_store.oldest',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='ce672d79f4c8c453f5096d0ff9a6a074277caff55c0ae5cb80900698125f0327',
        ),
        DriverEntry(
            'database.batch_pipeline_store.first_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only, no shape change')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.due',
            domains={'namespace': namespaces, 'state': ['leased', 'retry', 'result_ready']},
            neutrals={'now': (1.0, 'timestamp operand only'), 'limit': (100, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest',
            domains={'namespace': namespaces, 'priority': [0, 1, 2], 'ready_only': [False, True]},
        ),
    )
