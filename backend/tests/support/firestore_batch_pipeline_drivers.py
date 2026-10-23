"""Executable query coverage for the dormant batch pipeline's stage namespaces."""

from datetime import datetime, timezone

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, ref_collection


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    return (
        DriverEntry(
            'utils.batch_pipeline.redrive_scope.owner_jobs',
            base={'collection': ref_collection('batch_pipeline_prod_jobs'), 'uid': 'synthetic-owner'},
            neutrals={
                'page_size': (200, 'bounded page size only'),
                'read_budget': (20000, 'aggregate scan bound only'),
            },
        ),
        DriverEntry('database.batch_pipeline_shadow.pool_busy', domains={'namespace': namespaces}),
        DriverEntry(
            'database.batch_pipeline_shadow.stale_jobs',
            domains={'namespace': namespaces},
            neutrals={'before': (7200.0, 'cutoff operand only; single-field bounded query')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_shadow.ShadowStore._busy',
            covered_by=('database.batch_pipeline_shadow.pool_busy',),
            reason='thin adapter forwards the owning client and stage-qualified namespace unchanged',
            expect_observed=False,
            body_digest='3be03e458c8e65c535fed1475cbfae9c97421970c89dc751e2f4eaa4a46a4467',
        ),
        CoveredByEntry(
            'database.batch_pipeline_shadow.ShadowStore.reap',
            covered_by=('database.batch_pipeline_shadow.stale_jobs',),
            reason='bounded orchestration delegates its only query to stale_jobs; finish uses document transactions',
            expect_observed=False,
            body_digest='e5ea33125389c09c8ad556fab4a6319142f223e4dfa655095dcd89c64e976a8d',
        ),
        CoveredByEntry(
            'database.batch_ramp.ramp_admission_policy',
            covered_by=('database.batch_ramp.read_owner_load',),
            reason='admission wrapper delegates both metadata queries to the owner-load reader',
            expect_observed=False,
            body_digest='af9830f4381f5f9d880199ed21df739af633db7a327d7e723ac4d409585c9a01',
        ),
        DriverEntry(
            'database.batch_ramp.read_owner_load',
            base={'uid': 'synthetic-owner'},
            domains={'stage': ['prod', 'dev']},
            neutrals={
                'now': (100000.0, 'timestamp operand only'),
                'incoming_audio_seconds': (0, 'pure aggregation only'),
            },
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.ready_predecessor',
            covered_by=('database.batch_pipeline_store.ready_predecessor',),
            reason='thin adapter forwards the transaction-bound predecessor query unchanged',
            expect_observed=False,
            body_digest='345662386754d78758580d321467fcd012838fc0a9ae8194eeb7b3e6ede54f14',
        ),
        DriverEntry(
            'database.batch_pipeline_store.ready_predecessor',
            base={'owner_key': 'owner-hash', 'segment_id': 'segment-head'},
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
            neutrals={'transaction': (None, 'transaction binding only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.service_frontier',
            covered_by=('database.batch_pipeline_store.service_frontier',),
            reason='thin adapter forwards the transaction-bound frontier query unchanged',
            expect_observed=False,
            body_digest='74aa1993996cdc9ca93a1141de64dfc7e05a9d831a67860ddbb8a64d55520a02',
        ),
        CoveredByEntry(
            'database.batch_pipeline_staging.reap',
            covered_by=('database.batch_pipeline_staging.unsettled',),
            reason='thin orchestration delegates the sole query to unsettled; sum counts transaction results',
            expect_observed=False,
            body_digest='39b0e41ad13a7bc50bb8f987b6f78d11253663fd15baf39ca6663fb9f1fde377',
        ),
        DriverEntry(
            'database.batch_pipeline_staging.unsettled',
            domains={'namespace': namespaces},
            neutrals={
                'before': (datetime(2026, 10, 15, tzinfo=timezone.utc), 'timestamp operand only'),
                'limit': (100, 'bounded page size only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_quarantine_recovery.recovery_candidates',
            domains={
                'namespace': namespaces,
                'owner_id': ['synthetic-owner', None],
                'after_id': [None, 'held-09'],
            },
            neutrals={'limit': (10, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_quarantine_recovery.held_candidates',
            domains={'namespace': namespaces, 'after_id': [None, 'held-09']},
            neutrals={'limit': (32, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.projection_page',
            domains={
                'namespace': namespaces,
                'after': [None, (2.0, 'result-100')],
                'states': [('pending', 'persisted', 'ready'), ('pending',), ('persisted', 'ready')],
            },
            neutrals={'limit': (100, 'bounded page size only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.projection_successor',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces, 'previous': [None, 'segment-head']},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.projection_successor',
            covered_by=('database.batch_pipeline_store.projection_successor',),
            reason='store adapter forwards namespace, owner and predecessor unchanged',
            expect_observed=False,
            body_digest='96adabf372104327c5a8065ef2ff06621648ee242b3415d04b047d50ded9e6b1',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.projection_pending',
            covered_by=('database.batch_pipeline_store.projection_page',),
            reason='legacy first-page adapter discards the cursor only',
            expect_observed=False,
            body_digest='52cc913cca9086557133a8f7118b9980ce5f13649897207fafcfa221513a5629',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.projection_page',
            covered_by=('database.batch_pipeline_store.projection_page',),
            reason='store adapter forwards namespace, limit, keyset cursor and drain states unchanged',
            expect_observed=False,
            body_digest='bc9fe5cd08a05748eaa118af15031abdcb1a68d91d7f0b74bf177a27eb980a94',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.projection_pending',
            covered_by=('database.batch_pipeline_store.projection_page',),
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
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.control_candidate',
            covered_by=('database.batch_pipeline_store.control_candidate',),
            reason='thin store adapter forwards namespace and bounded query arguments unchanged',
            expect_observed=False,
            body_digest='73808da191932dbe29ef2a4d06712add5c584fb0b6e93f980ff666c08df60288',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.oldest_retry',
            covered_by=('database.batch_pipeline_store.oldest_retry',),
            reason='thin store adapter forwards namespace and bounded query arguments unchanged',
            expect_observed=False,
            body_digest='8d77904364b37100b5816f0252831ef6cf8807930dba8671cdc56bf603340315',
        ),
        DriverEntry(
            'database.batch_pipeline_store.service_frontier',
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
            neutrals={'transaction': (None, 'transaction binding only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.control_candidate',
            domains={'namespace': namespaces, 'priority': [0, 1, 2], 'pool': ['batch', 'live']},
            neutrals={'now': (1.0, 'eligibility timestamp operand only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest_retry',
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
        ),
        DriverEntry(
            'database.batch_pipeline_store.first_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only, no shape change')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.first_ready_pending',
            covered_by=('database.batch_pipeline_store.first_ready_pending',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='9999bc14a1c88206f5d98e34284f7895c179c73ab563bf813b179faa417076ba',
        ),
        DriverEntry(
            'database.batch_pipeline_store.first_ready_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'transaction': (None, 'transaction binding only, no shape change')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.longest_ready_pending',
            covered_by=('database.batch_pipeline_store.longest_ready_pending',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='c36f3f2504728cdf4473b0443f0371b3c15e124eb1a2f740fab411eee14f6337',
        ),
        DriverEntry(
            'database.batch_pipeline_store.longest_ready_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.fresh_pending',
            covered_by=('database.batch_pipeline_store.fresh_pending',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='d9b3d9c6a869efec2ed3ff0379930dbe43de3cadc01bba28c96051986be058c2',
        ),
        DriverEntry(
            'database.batch_pipeline_store.fresh_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'limit': (8, 'bounded page size')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.held_merge_owners',
            covered_by=('database.batch_pipeline_store.held_merge_owners',),
            reason='thin store adapter delegates unchanged query arguments to the named query builder',
            expect_observed=False,
            body_digest='55ac8d67e8e3e3fb689c9e9e086084a6acbcd7f5bb3b0b3f6186f5014cafc143',
        ),
        DriverEntry(
            'database.batch_pipeline_store.held_merge_owners',
            domains={'namespace': namespaces, 'after': [None, 'owner-hash']},
            neutrals={'limit': (50, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.due',
            domains={'namespace': namespaces, 'state': ['leased', 'retry', 'result_ready', 'record_pending']},
            neutrals={'now': (1.0, 'timestamp operand only'), 'limit': (100, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest',
            domains={'namespace': namespaces, 'priority': [0, 1, 2], 'ready_only': [False, True]},
        ),
    )
