"""Runtime query profiles for bounded lifecycle alarm observations."""

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, FROZEN_NOW


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    now = (FROZEN_NOW.timestamp(), 'finite clock operand; cohort floor changes values, not query shape')
    prefix = 'database.lifecycle_metrics_queries.'
    return (
        DriverEntry(prefix + 'record_pending', domains={'namespace': namespaces}, neutrals={'now': now}),
        DriverEntry(prefix + 'nojob', domains={'namespace': namespaces}),
        DriverEntry(prefix + 'enrichment', neutrals={'now': now}),
        DriverEntry(prefix + 'blocked_byok', neutrals={'now': now}),
        CoveredByEntry(
            prefix + '_where',
            covered_by=tuple(prefix + name for name in ('record_pending', 'nojob', 'enrichment', 'blocked_byok')),
            reason='pure filter builder; terminal observations execute inside the named sampler drivers',
            expect_observed=False,
            body_digest='0d9e02e0256fca2a42cc5ea34e8ef05cf4aab3f2d25ea8f953575b6d851e5b33',
        ),
    )
