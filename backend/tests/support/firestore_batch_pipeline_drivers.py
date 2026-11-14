"""Executable query coverage for the dormant batch pipeline's stage namespaces."""

from datetime import datetime, timezone
from itertools import cycle
from types import SimpleNamespace
from unittest.mock import patch

from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, ref_collection


def _projection_debt_on(client):
    from utils import record_projection_rebuild

    return patch.object(record_projection_rebuild, 'durable_debt_enabled', lambda: True)


def _repair_age_orders(client):
    from config import refactor_modes

    return patch.object(refactor_modes, 'record_seal_repair_age_order', side_effect=cycle((False, True)))


def _poll_skip_modes(client):
    from database import batch_pipeline_store

    return patch.object(batch_pipeline_store, 'held_poll_skip_enabled', side_effect=cycle((False, True)))


def entries():
    namespaces = ['batch_pipeline_prod', 'batch_pipeline_dev']
    return (
        DriverEntry(
            'database.batch_pipeline_delivered_share.delivered_share_page',
            domains={'namespace': namespaces},
            neutrals={
                'now': (2000000000.0, 'fixed cohort clock; no shape change'),
                'limit': (5000, 'bounded page size only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_fresh_guard.fresh_committed_counts',
            domains={'namespace': namespaces},
            neutrals={'now': (2000000000.0, 'fixed cohort clock; no shape change')},
        ),
        DriverEntry(
            'database.batch_pipeline_coalescing.due',
            domains={
                'namespace': namespaces,
                'producer_enabled': [False, True],
                'after': [None, {'scan_at': 1.0, 'id': 'synthetic-cursor'}],
            },
            neutrals={'now': (3000000.0, 'immutable release/lease deadline operand only')},
        ),
        CoveredByEntry(
            'database.record_custody_receipts.prune',
            covered_by=('database.record_custody_receipts.expired_page',),
            reason='bounded cleanup delegates its only query to expired_page; deletes use document batches',
            expect_observed=False,
            body_digest='a01ec56fc4132450ccd96a0eb11f59bfbdfdb8e7760e8c8d565f11ccd3af8e23',
        ),
        DriverEntry(
            'database.record_custody_receipts.expired_page',
            neutrals={
                'now': (2000000000.0, 'expiry cutoff only'),
                'budget': (
                    SimpleNamespace(check=lambda: None, timeout=lambda maximum=10: maximum),
                    'RPC deadline only',
                ),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_record_dead_letter.record_dead_letter_stock',
            domains={'namespace': namespaces},
        ),
        DriverEntry(
            'utils.record_projection_rebuild.run',
            domains={'mode': ['apply', 'plan']},
            neutrals={'budget': (SimpleNamespace(check=lambda: None, timeout=lambda: 10), 'RPC deadline only')},
            patchers=(_projection_debt_on,),
        ),
        DriverEntry(
            'database.record_seal_worker.pending_page',
            domains={'namespace': namespaces, 'after': [None, (datetime(2026, 10, 1, tzinfo=timezone.utc), 'pending')]},
            neutrals={
                'horizon': (datetime(2026, 11, 1, tzinfo=timezone.utc), 'finite pass cutoff only'),
                'limit': (64, 'bounded page size only'),
            },
        ),
        DriverEntry(
            'utils.batch_pipeline.record_seal_cluster_repair.discover',
            domains={
                'after': [
                    None,
                    {
                        'path': 'users/synthetic/conversations/old',
                        'finished_at': datetime(2026, 10, 1, tzinfo=timezone.utc),
                    },
                ]
            },
            neutrals={
                'budget': (SimpleNamespace(check=lambda: None, timeout=lambda: 10), 'RPC deadline only'),
                'max_rows': (1024, 'in-memory candidate cap only'),
                'max_scan': (10000, 'aggregate scan bound only'),
                'advance_rows': (1024, 'resume checkpoint only; no filter or ordering change'),
                'selected_cursors': (None, 'output-only selected metadata; no filter or ordering change'),
            },
        ),
        DriverEntry(
            'utils.batch_pipeline.record_seal_cluster_repair.discover_jobs',
            trials=2,
            patchers=(_repair_age_orders,),
            domains={
                'urgent': [False, True],
                'after': [
                    None,
                    {
                        'path': 'batch_pipeline_prod_jobs/old',
                        'finished_at': datetime(2026, 10, 1, tzinfo=timezone.utc),
                    },
                    {
                        'path': 'batch_pipeline_prod_jobs/old',
                        'enqueued_at': 1.0,
                        'horizon': datetime(2026, 10, 1, tzinfo=timezone.utc),
                    },
                ],
            },
            neutrals={
                'budget': (SimpleNamespace(check=lambda: None, timeout=lambda: 10), 'RPC deadline only'),
                'max_rows': (8, 'in-memory candidate cap only'),
                'max_scan': (128, 'aggregate scan bound only'),
                'selected_cursors': (None, 'output-only selected metadata; no filter or ordering change'),
                'invalid_clock_counts': (None, 'content-free aggregate output only; no query shape change'),
                'progress': (lambda _: None, 'content-free fallback diagnostic only'),
                'metric_ages': (None, 'output-only validated gauge samples; no filter or ordering change'),
            },
        ),
        DriverEntry(
            'utils.batch_pipeline.record_seal_sweeper.discover_pending',
            domains={'namespace': namespaces},
            neutrals={
                'budget': (None, 'RPC timeout and retry only; no filter or ordering change'),
                'limit': (32, 'bounded discovery page size only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_store.ready_for_capacity',
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
            neutrals={'now': (1.0, 'availability cutoff only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.ready_for_capacity',
            covered_by=('database.batch_pipeline_store.ready_for_capacity',),
            reason='thin adapter forwards the client, namespace, priority and availability cutoff',
            expect_observed=False,
            body_digest='975eabd92f43ba5da3d847439f4d8e3592525ccd31c11dcac6463365535eac10',
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest_admissible_ready',
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
            neutrals={'now': (1.0, 'admissibility cutoff applied in memory only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.oldest_admissible_ready',
            covered_by=('database.batch_pipeline_store.oldest_admissible_ready',),
            reason='thin adapter forwards the client, namespace, priority and admissibility cutoff',
            expect_observed=False,
            body_digest='293687cc6708d7ab2f673cb2984e6bb8cbfe581fa526db8c1040fd011dc00107',
        ),
        DriverEntry(
            'utils.batch_pipeline.redrive_scope.owner_jobs',
            base={'collection': ref_collection('batch_pipeline_prod_jobs'), 'uid': 'synthetic-owner'},
            neutrals={
                'page_size': (200, 'bounded page size only'),
                'read_budget': (20000, 'aggregate scan bound only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_shadow.pool_busy',
            domains={'namespace': namespaces},
            neutrals={'now': (7200.0, 'lease, retry and recording-window timestamp operand only')},
        ),
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
            body_digest='bf2a9290745e8dd01ebb927b03ed67b08fac05fdb43fd76f81f2dcfa54e0b85a',
        ),
        CoveredByEntry(
            'database.batch_pipeline_shadow.ShadowStore.reap',
            covered_by=('database.batch_pipeline_shadow.stale_jobs',),
            reason='bounded orchestration delegates its only query to stale_jobs; finish uses document transactions',
            expect_observed=False,
            body_digest='014a779e64fb2ab2baded6c4baef3ae9528bd080b8b7bafbd0e68948e8c418d4',
        ),
        CoveredByEntry(
            'database.batch_ramp.ramp_admission_policy',
            covered_by=('database.batch_ramp.read_owner_load',),
            reason='admission wrapper delegates both metadata queries to the owner-load reader; '
            'the intake-outcome evidence kwarg adds no query',
            expect_observed=False,
            body_digest='2d702e87308e65426820bbe9b4b89f492a966a01bc056fa39d63ed3a8545d649',
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
            'database.batch_pipeline_store.reseed_hinted_activation',
            covered_by=('database.batch_pipeline_store.service_frontier',),
            reason='post-commit re-seed: the frontier query unchanged (no transaction) plus one direct control doc get',
            expect_observed=False,
            body_digest='b962f088769367e4902876ef9dd91de299238b945f13610829e5f1f1acd8d449',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.run',
            covered_by=('database.batch_pipeline_store.service_frontier',),
            reason='queries only through reseed_hinted_activation after the body transaction commits',
            expect_observed=False,
            body_digest='d7cced46951bbfea06f7c501288ee41c76d972f6149aa7ead6e3c31573055b52',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.service_frontier',
            covered_by=('database.batch_pipeline_store.service_frontier',),
            reason='thin adapter forwards the frontier query unchanged; lever admission_frontier_hint (default on) drops only the transaction binding',
            expect_observed=False,
            body_digest='56b1e013fd6925c981be2186d76458211b724187b771ddc5ebb0eaa47820c44b',
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
            'database.batch_pipeline_quarantine_recovery.dead_held_candidates',
            domains={'namespace': namespaces, 'after_id': [None, 'held-09']},
            neutrals={'limit': (32, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_quarantine_recovery.held_expired_stock',
            domains={'namespace': namespaces},
        ),
        DriverEntry(
            'database.batch_pipeline_quarantine_recovery.held_candidates',
            domains={'namespace': namespaces, 'after_id': [None, 'held-09']},
            neutrals={'limit': (32, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_quarantine_recovery.input_expiring_candidates',
            domains={
                'namespace': namespaces,
                'after': [
                    None,
                    {
                        'enqueued_at': {'at': 1.0, 'id': 'held-09'},
                        'audio_staged_at': {'at': 1.0, 'id': 'held-10'},
                    },
                ],
            },
            neutrals={'now': (3000000.0, 'expiry cutoff operand only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.projection_page',
            domains={
                'namespace': namespaces,
                'after': [None, (2.0, 'result-100'), (2.0, 3.0, 'result-100')],
                'states': [
                    ('pending', 'persisted', 'ready'),
                    ('pending',),
                    ('persisted', 'ready'),
                    ('pending', 'persisted', 'ready', 'quarantine_held'),
                ],
                'due_before': [None, 3000000.0],
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
            reason='store adapter forwards namespace, limit, keyset cursor, drain states and the optional finish clock unchanged',
            expect_observed=False,
            # Re-reviewed 2026-11-11: the adapter gained the optional `due_before` finish clock and
            # forwards it unchanged; the cursor is now typed `tuple | None`. No query, read or bound
            # changed, and the forwarded shape is still the recorded `projection_page` driver.
            body_digest='93b2b60f115fd6139a36a571d40468e76d7962b5ffa8ca861e9572cfc0790785',
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
            body_digest='d82ee8b1c03be61b104e25304d6a0a732a9b59453fd302f4e7794a75622d65ad',
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
            neutrals={'transaction': (None, 'transaction binding only'), 'timeout': (None, 'RPC deadline only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.control_candidates',
            covered_by=('database.batch_pipeline_store.control_candidates',),
            reason='thin store adapter forwards namespace and bounded query arguments unchanged',
            expect_observed=False,
            body_digest='c1ce9e8170a7fde0e6a82c44a2db0c0c18909cba723e9cefd402cfe1f7993df9',
        ),
        DriverEntry(
            'database.batch_pipeline_store.control_candidates',
            domains={
                'namespace': namespaces,
                'priority': [0, 1, 2],
                'pool': ['batch', 'live'],
                'worker_id': ['', 'worker-a'],
                'fanout': [None, 16, 64],
            },
            neutrals={'now': (1.0, 'eligibility timestamp operand only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.control_candidate',
            domains={
                'namespace': namespaces,
                'priority': [0, 1, 2],
                'pool': ['batch', 'live'],
                'worker_id': ['', 'worker-a'],
            },
            neutrals={
                'now': (1.0, 'eligibility timestamp operand only'),
                'exclude': ((), 'in-memory exclusion only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest_retry',
            domains={'namespace': namespaces, 'priority': [0, 1, 2]},
        ),
        DriverEntry(
            'database.batch_pipeline_store.timeliness_sample',
            domains={
                'namespace': namespaces,
                'terminal_empty_processed': [False, True],
            },
            neutrals={
                'epoch': (1.0, 'cohort boundary operand only'),
                'now': (10000.0, 'SLA cutoff operand only; due > epoch drives the new-breach counts'),
                'sla': (7200.0, 'SLA width operand only'),
            },
        ),
        DriverEntry(
            'database.batch_pipeline_store.timeliness_all_time_counts',
            domains={'namespace': namespaces},
        ),
        DriverEntry(
            'database.batch_pipeline_store.first_pending',
            trials=2,
            patchers=(_poll_skip_modes,),
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces, 'skip_terminal': [False, True]},
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
            'database.batch_pipeline_store.fresh_first_pending',
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces, 'ready': [False, True]},
            neutrals={'transaction': (None, 'transaction binding only, no shape change')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.fresh_first_pending',
            covered_by=('database.batch_pipeline_store.fresh_first_pending',),
            reason='thin transactional adapter selects the ready equality without changing query ordering',
            expect_observed=False,
            body_digest='3eda52b96735afad17b1471efc6e912998c1d9720a02fff4ce80260099bd7f59',
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreTransaction.fresh_first_ready_pending',
            covered_by=('database.batch_pipeline_store.fresh_first_pending',),
            reason='thin transactional adapter selects the ready equality without changing query ordering',
            expect_observed=False,
            body_digest='bd2a5ddf5a4c4b1d0bbc6145621622530adb9b1a158c13f8f1691fa2786725ec',
        ),
        DriverEntry(
            'database.batch_pipeline_store.fresh_pending',
            trials=2,
            patchers=(_poll_skip_modes,),
            base={'owner_key': 'owner-hash'},
            domains={'namespace': namespaces},
            neutrals={'limit': (8, 'bounded page size')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.ready_owners',
            domains={
                'namespace': namespaces,
                'after_owner_key': [None, 'synthetic-cursor'],
                'ceiling_owner_key': [None, 'synthetic-ceiling'],
                'descending': [False, True],
            },
            neutrals={'limit': (2, 'bounded owner count only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_store.FirestoreStore.ready_owners',
            covered_by=('database.batch_pipeline_store.ready_owners',),
            reason='thin store adapter forwards the owner cursor unchanged',
            expect_observed=False,
            body_digest='b5d53e56900da07d2069cd1068218cb1515895a8dfd35f91dab9d06390cd02cf',
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
        CoveredByEntry(
            'database.batch_pipeline_store.promote_record_recoveries',
            covered_by=('database.batch_pipeline_store.due',),
            reason='bounded promotion delegates its waiting-state query to due; promotion uses document transactions',
            expect_observed=False,
            body_digest='ce853ebe262f00a49241f670f28e23dfa0951d37cda42e1da34a966899c1ecd1',
        ),
        DriverEntry(
            'database.batch_pipeline_store.due',
            domains={
                'namespace': namespaces,
                'state': ['leased', 'retry', 'result_ready', 'record_pending', 'record_recovery_waiting'],
                'limit': [1, 100, 500, 999],
            },
            neutrals={'now': (1.0, 'timestamp operand only')},
        ),
        DriverEntry(
            'database.batch_pipeline_store.oldest',
            domains={'namespace': namespaces, 'priority': [0, 1, 2], 'ready_only': [False, True]},
        ),
        DriverEntry(
            'database.batch_pipeline_projection_release.expired_page_ids',
            domains={'namespace': namespaces, 'after_id': [None, 'result-100']},
            neutrals={'limit': (32, 'bounded page size only; equality single-field index')},
        ),
        DriverEntry(
            'database.batch_pipeline_projection_release.held_page_ids',
            domains={'namespace': namespaces, 'after_id': [None, 'result-100']},
            neutrals={'limit': (128, 'bounded page size only; equality is served by the automatic single-field index')},
        ),
        DriverEntry(
            'database.batch_pipeline_projection_release.assignment_held_page_ids',
            domains={'namespace': namespaces, 'after_id': [None, 'job-100']},
            neutrals={'limit': (128, 'bounded page size only')},
        ),
        CoveredByEntry(
            'database.batch_pipeline_projection_release.release_page',
            covered_by=(
                'database.batch_pipeline_projection_release.held_page_ids',
                'database.batch_pipeline_projection_release.assignment_held_page_ids',
            ),
            reason='thin 2-tuple wrapper over release_page_settled; no queries of its own',
            expect_observed=False,
            body_digest='15ce4bf78a33ea401c5eeb56e895c088a75ffc45471d268784f7f174e6474f30',
        ),
        CoveredByEntry(
            'database.batch_pipeline_projection_release.release_page_settled',
            covered_by=(
                'database.batch_pipeline_projection_release.held_page_ids',
                'database.batch_pipeline_projection_release.assignment_held_page_ids',
            ),
            reason='bounded release scan delegates queries to both page builders; resets are document transactions',
            expect_observed=False,
            body_digest='d863e83874910f88595eb18925f58f8129e1665d7b14dbde81179c443a75c632',
        ),
        CoveredByEntry(
            'database.batch_pipeline_projection_release.release_scan_pass',
            covered_by=(
                'database.batch_pipeline_projection_release.held_page_ids',
                'database.batch_pipeline_projection_release.assignment_held_page_ids',
            ),
            reason='thin 2-tuple wrapper over release_scan_pass_settled; no queries of its own',
            expect_observed=False,
            body_digest='92308c42482933a9adde1ca3fc20dff803d3c7c3be88d134d608e532061a1d22',
        ),
        CoveredByEntry(
            'database.batch_pipeline_projection_release.release_scan_pass_settled',
            covered_by=(
                'database.batch_pipeline_projection_release.held_page_ids',
                'database.batch_pipeline_projection_release.assignment_held_page_ids',
            ),
            reason='two durable cursors share release_page_settled; cursor reads and writes are document operations',
            expect_observed=False,
            body_digest='0b064975a7115e66ee082bdf546b2b9bcfc75cbdf14bf08e67ccb595027c4de2',
        ),
    )
