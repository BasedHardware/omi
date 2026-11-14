"""Runtime query profiles for bounded lifecycle alarm observations."""

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, FROZEN_NOW


def _audio_silence_rows(client, combo, _trial):
    created = FROZEN_NOW
    for index in range(2):
        client.documents[f'users/shape-user/conversations/c{index}'] = {
            'created_at': created,
            'source': 'omi',
            'record_upload_sessions': {},
        }
        client.documents[f'sync_reprocess_outbox/o{index}'] = {
            'uid': 'shape-orphan',
            'first_pending_at': created.timestamp(),
        }
        client.documents[f'{combo["namespace"]}_jobs/j{index}'] = {
            'owner_id': 'shape-job-user',
            'enqueued_at': created.timestamp(),
            'record_snapshot': {'source': 'desktop'},
        }


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    now = (FROZEN_NOW.timestamp(), 'finite clock operand; cohort floor changes values, not query shape')
    prefix = 'database.lifecycle_metrics_queries.'
    return (
        DriverEntry(prefix + 'record_pending', domains={'namespace': namespaces}, neutrals={'now': now}),
        DriverEntry(
            'database.audio_silence_census.sample',
            domains={'namespace': namespaces},
            neutrals={
                'now': now,
                'read_budget': (4000, 'hard modeled-read ceiling only'),
                'page_limit': (1, 'force bounded-page candidate aggregation coverage'),
            },
            setup=_audio_silence_rows,
        ),
        DriverEntry(prefix + 'nojob', domains={'namespace': namespaces}),
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
                for name in ('record_pending', 'nojob', 'enrichment', 'blocked_byok', 'enrichment_summary_repair')
            ),
            reason='pure filter builder; terminal observations execute inside the named sampler drivers',
            expect_observed=False,
            body_digest='51d3e38b20df6800101fbf671471d2538c487d9c702698c6a9ad221c43f89a79',
        ),
    )
