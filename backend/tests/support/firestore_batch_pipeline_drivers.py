"""Executable query coverage for the dormant batch pipeline's stage namespaces."""

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    return (
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.first_pending',
            covered_by=('database.batch_pipeline_store.first_pending',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='97a1fed292df7a57f6fc815cdacb16d6cc0b661c06fd047b9c1a43b34cdd3312',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.due',
            covered_by=('database.batch_pipeline_store.due',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='a122cbb68303e136d2721efaab34739a66fcc882634b9448a63d8320ad4a87e7',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.oldest',
            covered_by=('database.batch_pipeline_store.oldest',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='46202441b59dfb6a878bb1571be4c04b094a30110b8dc2af6351c96a86d14e6a',
        ),
        DriverEntry(
            'database.batch_pipeline_store.first_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only, no shape change')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.due',
            domains={'namespace': namespaces, 'state': ['leased', 'retry']},
            neutrals={'now': (1.0, 'timestamp operand only'), 'limit': (100, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest',
            domains={'namespace': namespaces, 'priority': [0, 1, 2], 'ready_only': [False, True]},
        ),
    )
