"""Runtime query profiles for bounded lifecycle alarm observations."""

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, FROZEN_NOW


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    now = (FROZEN_NOW.timestamp(), 'finite clock operand; cohort floor changes values, not query shape')
    prefix = 'database.lifecycle_metrics_queries.'
    return (
        DriverEntry(prefix + 'record_pending', domains={'namespace': namespaces}, neutrals={'now': now}),
        DriverEntry(prefix + 'nojob', domains={'namespace': namespaces}),
        DriverEntry(prefix + 'vendor_held', domains={'namespace': namespaces}, neutrals={'now': now}),
        DriverEntry(prefix + 'provider_stage', domains={'namespace': namespaces}, neutrals={'now': now}),
        DriverEntry(prefix + 'enrichment', neutrals={'now': now}),
        DriverEntry(prefix + 'blocked_byok', neutrals={'now': now}),
        DriverEntry(prefix + 'enrichment_summary_repair'),
        DriverEntry(
            'utils.lifecycle_pair_census.sample',
            neutrals={'now': now},
            domains={
                'state': [
                    {
                        'phase': phase,
                        **(
                            {'cursor': path}
                            if mode == 'legacy'
                            else {'cursors': {phase: path}} if mode == 'map' else {}
                        ),
                    }
                    for phase in ('jobs', 'queued', 'processing')
                    for path in [
                        (
                            'conversation_finalization_jobs/previous'
                            if phase == 'jobs'
                            else 'users/shape-user/conversations/previous'
                        )
                    ]
                    for mode in ('none', 'legacy', 'map')
                ]
            },
        ),
        CoveredByEntry(
            prefix + '_where',
            covered_by=tuple(
                prefix + name
                for name in (
                    'record_pending',
                    'nojob',
                    'vendor_held',
                    'provider_stage',
                    'enrichment',
                    'blocked_byok',
                    'enrichment_summary_repair',
                )
            ),
            reason='pure filter builder; terminal observations execute inside the named sampler drivers',
            expect_observed=False,
            body_digest='51d3e38b20df6800101fbf671471d2538c487d9c702698c6a9ad221c43f89a79',
        ),
    )
