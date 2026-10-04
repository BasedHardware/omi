from __future__ import annotations

import importlib
import unittest.mock
from types import SimpleNamespace

from tests.support.firestore_query_drivers import (
    FROZEN_LATER as T1,
    FROZEN_NOW as T0,
    FROZEN_TODAY as D0,
    SHAPE_UID as UID,
    CallerProfile,
    CoveredByEntry,
    DriverEntry,
    SkipEntry,
    ref_collection,
)

DRIVERS: dict[str, DriverEntry] = {}
COVERED_BY: dict[str, CoveredByEntry] = {}
SKIPS: dict[str, SkipEntry] = {}
BODY_DIGEST = {
    'parakeet.stream_handler._NemoRNNTStreamingDecoder.decode_pcm': '37cecadaf2adcc0650d318d4ac7adb316dade33610927e6ac663f9d386c9edd6',
    'routers.desktop_proxy._read_request_body': 'e71ed271b768274df479a8429ce363d1152a85073b59c8d034445bd8fc87c6b7',
    'utils.multipart._size_limited_stream': 'b77a69f35b7e37aa7b68cc93748bb83fdf159e7e5f98f03ae2ee0d473efe857d',
    'utils.multipart.parse_multipart_form': 'cf7bb921eb61427b97be7c4ab3a8a22fc11b8b2a12788dbe44a1884a1beb58fa',
    'utils.memory.canonical_graph._build_canonical_graph_items_query': '55a8b4ccfc9b7e98d6482495590fdf15f04a6f325485b2345043419846862bbd',
}
LIMIT = (25, 'bounds the read window, not filters or ordering')
NOW = (T0, 'clock changes only the representative range operand')
BUDGET = (None, 'RPC timeout and read accounting only')


def _stub(dotted, value):
    def patcher(client):
        name, attr = dotted.rsplit('.', 1)
        return unittest.mock.patch.object(importlib.import_module(name), attr, return_value=value)

    return patcher


def _driver(
    function,
    *,
    base=None,
    domains=None,
    neutrals=None,
    setup=None,
    patchers=(),
    trials=1,
    profile='request',
    serving=True,
):
    entry = DriverEntry(
        function,
        base=base or {},
        neutrals=neutrals or {},
        setup=setup,
        patchers=patchers,
        trials=trials,
        profiles=(CallerProfile(profile, domains or {}, serving=serving),),
    )
    if function in DRIVERS:
        raise ValueError(function)
    DRIVERS[function] = entry


def _feedback_rows(client, combo, trial):
    session = 'session-1' if trial == 1 else None
    client.queue_results(
        [
            client.snapshot(
                f'users/{UID}/messages/rated', {'id': 'message-1', 'created_at': T0, 'chat_session_id': session}
            )
        ]
    )


def _nested_export(client, combo, trial):
    path = f"users/{UID}/{combo['parent_collection_name']}/parent-1"
    client.queue_results([client.snapshot(path, {})])


def _keyframes(client, combo, trial):
    path = f'users/{UID}/conversation_keyframe_jobs/conv-1'
    client.queue_results([client.snapshot(path, {'conversation_id': 'conv-1', 'started_at': T0, 'finished_at': T1})])
    if trial:
        client.queue_results(
            [
                client.snapshot(
                    f'users/{UID}/screen_activity/screen-{index}',
                    {'captureEligible': False, 'timestamp': '2026-01-01 00:00:00.000'},
                )
                for index in range(501)
            ]
        )


def _inventory_cursors(client, combo, trial):
    if not trial:
        return
    for path in (
        'daily_memory_sweep_control/retry_cursor',
        'daily_memory_sweep_control/canonical_inventory_cursor',
        'daily_memory_sweep_control/onboarding_inventory_cursor',
        'canonical_memory_maintenance_control/cursor',
    ):
        client.documents[path] = {'schema_version': 1, 'last_uid': UID, 'generation': 0}
    seed = f'users/{UID}/memory_state/apply_control'
    client.documents[seed] = {'uid': UID, 'account_generation': 1, 'source_generation': 1}
    for path in ('daily_memory_sweep_control/seed_cursor', 'canonical_memory_maintenance_control/seed_cursor'):
        client.documents[path] = {'schema_version': 1, 'last_uid': seed, 'last_path': seed, 'generation': 0}
    client.documents['knowledge_ledger_migration_control/inventory_cursor'] = {
        'schema_version': 1,
        'last_path': seed,
        'generation': 0,
    }
    client.documents['maintenance_state/frame_request_retention'] = {'cursor_uid': UID, 'retry_cursor_uid': UID}


def _control(client, combo, trial):
    client.documents[f'users/{UID}/memory_state/apply_control'] = {
        'uid': UID,
        'account_generation': 1,
        'source_generation': 1,
    }


def _graph(client, combo, trial):
    module = importlib.import_module('utils.memory.canonical_graph')
    if combo.get('cursor'):
        combo['cursor'] = module._canonical_graph_encode_cursor(
            uid=UID,
            revision=module._CanonicalGraphRevision(1, 1, 'head-1'),
            updated_at=T0,
            memory_id='memory-1',
            secret=b'shape-secret',
        )


def _candidate(client, combo, trial):
    module = importlib.import_module('utils.memory.daily_memory_sweep')
    slot, entity = combo['candidate']
    combo['candidate'] = module.DailySweepCandidate(
        candidate_id='candidate-1',
        kind='fact',
        content='shape fact',
        source_id='source-1',
        source_type='daily_summary',
        slot=slot,
        subject_entity_id=entity,
    )


def _window(client, combo, trial):
    module = importlib.import_module('utils.memory.daily_memory_sweep')
    combo['window'] = module.CompletedLocalDayWindow(T0, T1, 'window-1')


def _summary(client, combo, trial):
    module = importlib.import_module('utils.memory.daily_memory_sweep')
    combo['model_authority'] = module.DailySweepModelAuthority()
    combo['control'] = importlib.import_module('models.memory_apply').MemoryControlState(
        uid=UID, head_commit_id='head-1', account_generation=1, source_generation=1, updated_at=T0
    )
    _control(client, combo, trial)


def _onboarding(client, combo, trial):
    combo['model_authority'] = importlib.import_module('utils.memory.daily_memory_sweep').DailySweepModelAuthority()


def _entity(client, combo, trial):
    combo['entity'] = importlib.import_module('utils.retrieval.tools.entity_timeline_tools').EntityReference(
        kind='person', identifier='person-1'
    )
    client.documents[f'users/{UID}/people/person-1'] = {'name': 'Shape Person'}


def _purge(client, combo, trial):
    client.documents[f'account_deletions/{UID}'] = {'wipe_status': 'pending'}
    client.queue_results([client.snapshot(f'users/{UID}/memory_outbox/processing-1', {'status': 'processing'})])


def _purge_patcher(client):
    module = importlib.import_module('utils.memory.canonical_memory_adapter')
    original = module.purge_canonical_derived_user_data

    def invoke(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except RuntimeError as exc:
            if str(exc) != 'canonical provider purge deferred until leased projection work drains':
                raise
            return None

    return unittest.mock.patch.object(module, 'purge_canonical_derived_user_data', invoke)


def _rejected_cache(client):
    return unittest.mock.patch.object(
        importlib.import_module('utils.memory.rejected_memory_feedback'), '_feedback_cache', {}
    )


def _mirror_fence(client):
    module = importlib.import_module('utils.memory.jit_ledger_mirror_snapshot')
    return unittest.mock.patch.object(
        module, '_read_fence', return_value=module.LedgerMirrorFence(UID, 1, 1, 0, 'head-1', 1)
    )


def _mirror_cursor(client, combo, trial):
    if combo.get('cursor'):
        module = importlib.import_module('utils.memory.jit_ledger_mirror_snapshot')
        combo['cursor'] = module._encode_cursor(
            uid=UID,
            epoch_id=module.LedgerMirrorFence(UID, 1, 1, 0, 'head-1', 1).epoch_id,
            last_memory_id='memory-1',
            chain_revision='a' * 64,
            scanned_count=1,
            projected_count=0,
            secret=b'shape-secret',
            now_epoch_seconds=int(T0.timestamp()),
        )


def _mirror_cursor_clock(client):
    module = importlib.import_module('utils.memory.jit_ledger_mirror_snapshot')
    original = module._decode_cursor
    return unittest.mock.patch.object(
        module,
        '_decode_cursor',
        lambda cursor, **kwargs: original(cursor, **{**kwargs, 'now_epoch_seconds': int(T0.timestamp())}),
    )


_driver('database.serving_query_reads.list_active_desktop_prompt_snapshots')
_driver('database.serving_query_reads.list_desktop_release_snapshots')
_driver('database.serving_query_reads.find_fair_use_case_snapshots', base={'case_ref': 'case-1'})
_driver(
    'services.conversation_keyframes.reconcile_conversation_keyframe_jobs',
    base={'uid': UID, 'device_id': 'device-1', 'account_generation': 1},
    neutrals={'device_retention_seconds': (None, 'local pruning only'), 'limit': LIMIT},
    setup=_keyframes,
    trials=2,
)
_driver(
    'services.conversation_keyframes.prune_expired_conversation_keyframe_jobs',
    base={'uid': UID},
    neutrals={'now': NOW, 'limit': LIMIT},
    profile='maintenance-keyframe-retention',
    serving=False,
)
_driver(
    'services.frame_request_retention._load_user_page',
    base={'user_limit': 16},
    setup=_inventory_cursors,
    trials=2,
    profile='maintenance-frame-retention',
    serving=False,
)
_driver(
    'services.users.data_export_iterators.iter_user_subcollection',
    base={'uid': UID},
    domains={
        'collection_name': [
            'frame_requests',
            'frame_vision_receipts',
            'conversation_keyframe_jobs',
            'candidates',
            'goals',
            'workstreams',
            'staged_tasks',
            'task_recurrence_inbox',
            'task_feedback',
            'task_outcomes',
            'task_interventions',
            'task_attention_overrides',
            'task_context_snapshots',
            'task_open_loop_snapshots',
            'chat_first_proactive_intents',
            'chat_first_dead_letters',
            'chat_first_deferrals',
            'daily_memory_sweep_sources',
            'daily_memory_sweep_daily_summary_staged',
            'daily_memory_sweep_onboarding_staged',
            'daily_memory_sweep_model_invocations',
            'jit_trigger_feedback',
            'jit_proactivity_events',
            'jit_proactivity_daily_budgets',
            'jit_proactivity_candidate_turns',
            'memory_review_queue',
            'memory_corrections',
            'memory_items',
            'memory_operations',
            'memory_commits',
            'memory_deletion_receipts',
            'memory_source_replacements',
            'memory_ledger_reopens',
            'memory_lineage',
            'memory_historical_overrides',
            'memory_evidence',
        ]
    },
    profile='export-portability',
)
for parent, child in [
    ('goals', 'events'),
    ('goals', 'goal_history'),
    ('workstreams', 'events'),
    ('workstreams', 'artifact_refs'),
    ('workstreams', 'continuation_checkpoints'),
]:
    key = 'services.users.data_export_iterators.iter_user_nested_subcollection'
    profile = CallerProfile(
        f'export-{parent}-{child}', {'parent_collection_name': [parent], 'child_collection_name': [child]}
    )
    if key not in DRIVERS:
        DRIVERS[key] = DriverEntry(key, base={'uid': UID}, setup=_nested_export)
    DRIVERS[key].profiles += (profile,)
_driver('utils.conversations.meeting_context_pack.load_people_documents', base={'uid': UID})
_driver(
    'utils.email.day3_reengagement._conversation_signals',
    base={'uid': UID, 'signup_at': T0},
    profile='scheduled-day3-email',
)
_driver(
    'utils.email.day3_reengagement.collect_day3_candidates',
    base={'now': T0},
    neutrals={'limit': LIMIT},
    profile='scheduled-day3-email',
)
_driver(
    'utils.experiments.enrollment_counts',
    base={'experiment_id': 'experiment-1'},
    neutrals={'variants': (('control', 'treatment'), 'post-read tally only')},
    profile='operational-enrollment-audit',
    serving=False,
)
_driver(
    'utils.feedback_context._find_message',
    base={'uid': UID, 'message_id': 'message-1'},
    domains={'metadata_only': [False, True]},
)
_driver(
    'utils.feedback_context.resolve_chat_context',
    base={'uid': UID, 'message_id': 'message-1'},
    domains={'chat_session_id': [None, 'session-1']},
    neutrals={'follow_up_window_seconds': (300, 'changes time operand only')},
    setup=_feedback_rows,
    trials=2,
    profile='scheduled-feedback-report',
)
_driver(
    'utils.memory.belief_backfill._default_item_reader',
    base={'uid': UID},
    domains={'start_after': [None, 'memory-1']},
    neutrals={'limit': LIMIT},
    profile='operational-belief-backfill',
    serving=False,
)
_driver(
    'utils.memory.canonical_consolidation.list_pending_consolidation_items',
    base={'uid': UID},
    domains={'start_after': [None, (T0, 'memory-1')]},
    neutrals={'now': NOW, 'limit': LIMIT},
    profile='maintenance-consolidation',
    serving=False,
)
_driver(
    'utils.memory.canonical_required_processing.list_pending_required_processing_items',
    base={'uid': UID},
    neutrals={'limit': LIMIT},
    profile='maintenance-required-processing',
    serving=False,
)
_driver(
    'jobs.short_term_lifecycle_worker.fetch_expired_short_term_memory_items_firestore',
    base={'uid': UID},
    neutrals={'now': NOW, 'limit': LIMIT},
    profile='maintenance-short-term-expiry',
    serving=False,
)
_driver(
    'jobs.short_term_lifecycle_worker.fetch_expiry_urgent_short_term_memory_items_firestore',
    base={'deadline': T1},
    neutrals={'limit': LIMIT},
    profile='maintenance-global-expiry',
    serving=False,
)
_driver(
    'utils.memory.canonical_short_term_maintenance_cron.count_active_short_term',
    base={'uid': UID},
    neutrals={'cap': (11, 'caps tally only')},
    profile='maintenance-short-term-count',
    serving=False,
)
for function in (
    'utils.memory.canonical_short_term_maintenance_cron._seed_registry_from_existing_memory_states',
    'utils.memory.canonical_short_term_maintenance_cron.bounded_canonical_memory_uid_inventory',
    'utils.memory.daily_memory_sweep_inventory._read_retry_uids',
    'utils.memory.daily_memory_sweep_inventory._seed_registry',
    'utils.memory.daily_memory_sweep_inventory.bounded_canonical_daily_sweep_uids',
    'utils.memory.daily_memory_sweep_inventory.bounded_daily_memory_sweep_uid_inventory',
    'utils.memory.knowledge_ledger_drain.bounded_ledger_drain_inventory',
):
    neutrals = {'limit': LIMIT}
    if function.endswith(
        (
            'bounded_canonical_memory_uid_inventory',
            'bounded_canonical_daily_sweep_uids',
            'bounded_daily_memory_sweep_uid_inventory',
        )
    ):
        neutrals['persist_cursor'] = (False, 'controls point-write persistence, not query shape')
    if function.endswith('bounded_daily_memory_sweep_uid_inventory'):
        neutrals['return_page'] = (False, 'return packaging only')
    if function.endswith('bounded_ledger_drain_inventory'):
        neutrals['uid_allowlist'] = (None, 'collection-group scan profile; allowlisted mode uses point reads only')
    _driver(
        function,
        neutrals=neutrals,
        setup=_inventory_cursors,
        trials=2,
        profile='maintenance-resumable-inventory',
        serving=False,
    )
_driver(
    'utils.memory.canonical_graph._read_canonical_graph_page_once',
    base={'uid': UID, 'limit': 25},
    domains={'cursor': [None, 'resumed']},
    setup=_graph,
    patchers=(
        _stub('utils.memory.canonical_graph._canonical_graph_cursor_secret', b'shape-secret'),
        _stub(
            'utils.memory.canonical_graph._read_canonical_graph_revision',
            SimpleNamespace(account_generation=1, commit_sequence=1, head_commit_id='head-1'),
        ),
    ),
)
_driver(
    'utils.memory.canonical_memory_adapter.read_canonical_scan_page',
    base={'uid': UID},
    domains={'start_after': [None, (T0, 'memory-1')]},
    neutrals={
        'limit': LIMIT,
        'device_scope_request': (None, 'post-read visibility only'),
        'include_pending_processing': (False, 'post-read visibility only'),
        'include_archive': (False, 'post-read visibility only'),
        'now': NOW,
        'budget': BUDGET,
        'view': ('released', 'post-read temporal visibility only'),
        'as_of': (None, 'post-read temporal visibility only'),
        'item_filter': (None, 'post-read predicate only'),
    },
)
_driver(
    'utils.memory.canonical_memory_adapter.purge_canonical_derived_user_data',
    base={'uid': UID},
    setup=_purge,
    patchers=(_purge_patcher,),
    profile='account-deletion-leased-work-probe',
)
_driver(
    'utils.memory.daily_memory_sweep.cleanup_expired_daily_memory_sweep_stages',
    base={'uid': UID},
    neutrals={'now': NOW, 'limit': LIMIT},
    profile='maintenance-stage-retention',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep.assert_no_live_pre_lock_claims',
    base={'now': T0},
    neutrals={'uids': (None, 'post-read scope filter only')},
    profile='operational-rollout-audit',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._invoke_model_once_claimed',
    base={'uid': UID, 'invocation_id': 'invocation-1', 'candidate_builder': lambda: ()},
    domains={
        'account_generation': [1],
        'source_generation': [1],
        'sweep_generation': [1],
        'window_id': ['window-1'],
        'input_digest': ['digest-1'],
    },
    neutrals={
        'now': NOW,
        'admission_id': ('admission-1', 'point-write identity only'),
        'invocation_evidence': (None, 'output diagnostics only'),
        'before_provider_dispatch': (None, 'non-query provider callback'),
    },
    setup=_control,
    profile='maintenance-fenced-model-claim',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._consume_attested_window_skip',
    base={'uid': UID, 'account_generation': 1, 'source_generation': 1, 'sweep_generation': 1, 'window_id': 'window-1'},
    setup=_control,
    profile='maintenance-attested-window',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._pending_receipt_dates',
    base={'uid': UID, 'through': D0, 'account_generation': 1, 'source_generation': 1},
    neutrals={'sweep_generation': (1, 'post-read generation check only')},
    profile='maintenance-receipt-recovery',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._find_active_slot_or_subject',
    base={'uid': UID},
    domains={'candidate': [(None, None), ('role', None), (None, 'person-1'), ('role', 'person-1')]},
    setup=_candidate,
    profile='maintenance-occupant-proof',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._read_completed_day_conversation_sources',
    base={'uid': UID, 'max_conversations': 8, 'max_summary_characters': 1000},
    domains={'window': [None]},
    setup=_window,
    profile='maintenance-completed-day',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._produce_onboarding_sources',
    base={'uid': UID, 'max_candidates': 8},
    domains={'model_authority': [None]},
    neutrals={
        'model_extractor': (None, 'provider callback is unreachable for an exhausted source scan'),
        'account_generation': (1, 'receipt point-read fence only'),
        'source_generation': (1, 'point-read/write fence only'),
        'sweep_generation': (1, 'point-read/write fence only'),
    },
    setup=_onboarding,
    profile='maintenance-onboarding',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._read_daily_sweep_folder_options',
    base={'uid': UID},
    profile='maintenance-folder-taxonomy',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep.produce_completed_day_daily_summary_sources',
    base={'uid': UID, 'local_date': D0, 'timezone_name': 'UTC'},
    domains={'control': [None], 'model_authority': [None]},
    neutrals={
        'agent_runner': (None, 'no provider call for an exhausted source scan'),
        'window_override': (None, 'uses the supplied local-date window'),
        'sweep_generation': (1, 'fixed production generation'),
        'qa_run_id': (None, 'production profile, not QA'),
    },
    setup=_summary,
    profile='maintenance-completed-day-summary',
    serving=False,
)
_driver(
    'utils.memory.daily_memory_sweep._iter_active_standing_triggers',
    base={'uid': UID},
    profile='maintenance-standing-triggers',
    serving=False,
)
_driver(
    'utils.memory.jit_ledger_mirror_snapshot.read_authoritative_ledger_mirror_page',
    base={'uid': UID},
    domains={'cursor': [None, 'resumed']},
    neutrals={'page_size': LIMIT},
    setup=_mirror_cursor,
    patchers=(
        _mirror_fence,
        _mirror_cursor_clock,
        _stub('utils.memory.jit_ledger_mirror_snapshot.cursor_secret', b'shape-secret'),
    ),
)
_driver(
    'utils.memory.non_active_route_audit._fetch_non_active_route_docs',
    base={'uid': UID},
    domains={'run_id': [None, 'run-1']},
    profile='operational-non-active-route-audit',
    serving=False,
)
_driver(
    'utils.memory.product_memory_read_service.iter_authoritative_product_memory_items',
    base={'uid': UID},
    neutrals={'budget': BUDGET},
)
_driver(
    'utils.memory.product_memory_read_service.iter_authoritative_product_memory_items_newest_first',
    base={'uid': UID, 'limit': 25},
    domains={'start_after': [None, (T0, 'memory-1')]},
    neutrals={'budget': BUDGET},
)
_driver(
    'utils.memory.product_memory_read_service.fetch_authoritative_product_memory_items_for_source',
    base={'uid': UID, 'source_id': 'source-1'},
    neutrals={'page_size': LIMIT},
)
_driver(
    'utils.memory.product_memory_read_service.fetch_authoritative_superseded_memory_items_for_targets',
    base={'uid': UID},
    domains={'target_memory_ids': [['memory-1'], ['memory-1', 'memory-2'], [f'memory-{index}' for index in range(31)]]},
    neutrals={'page_size': LIMIT},
)
_driver(
    'utils.memory.rejected_memory_feedback.get_recent_rejected_memory_feedback',
    base={'uid': UID},
    neutrals={'now': NOW},
    patchers=(_rejected_cache,),
)
_driver(
    'utils.retrieval.tools.entity_timeline_tools._resolve_entity_aliases',
    base={'uid': UID},
    domains={'entity': [None]},
    setup=_entity,
)
_driver(
    'utils.retrieval.tools.screen_activity_tools._keyword_screen_matches',
    base={'uid': UID, 'query': 'shape', 'limit': 10},
    domains={'start_ts': [None, int(T0.timestamp())], 'end_ts': [None, int(T1.timestamp())]},
)
_driver('utils.sync.recording_session_target._candidate_rows', base={'uid': UID, 'recording_session_id': 'recording-1'})
DRIVERS['utils.task_intelligence.chat_first_materialization_health._documents'] = DriverEntry(
    'utils.task_intelligence.chat_first_materialization_health._documents',
    profiles=(
        CallerProfile(
            'operational-materialization-health',
            {'uid': [None, UID], 'limit': [25], 'min_created_at': [None, T0]},
            serving=False,
        ),
        CallerProfile(
            'scheduled-materialization-health',
            {'uid': [None], 'limit': [None], 'min_created_at': [T0]},
            serving=True,
        ),
    ),
)
_driver(
    'utils.x_connector.run_x_sync_job',
    neutrals={'job_started_at': (None, 'model budget clock only')},
    profile='scheduled-x-sync',
)

COVERED_BY['utils.memory.product_memory_read_service._fetch_authoritative_memory_query_pages'] = CoveredByEntry(
    'utils.memory.product_memory_read_service._fetch_authoritative_memory_query_pages',
    (
        'utils.memory.product_memory_read_service.fetch_authoritative_product_memory_items_for_source',
        'utils.memory.product_memory_read_service.fetch_authoritative_superseded_memory_items_for_targets',
    ),
    'terminal paging helper observed in both targeted caller drivers',
)
COVERED_BY['utils.other.list_budget.budgeted_stream_list'] = CoveredByEntry(
    'utils.other.list_budget.budgeted_stream_list',
    ('utils.memory.canonical_memory_adapter.read_canonical_scan_page',),
    'terminal budget helper observed in canonical scan driver',
)
_driver(
    'utils.other.list_budget.budgeted_stream_iter',
    base={'query': ref_collection(f'users/{UID}/memory_items'), 'budget': None},
    neutrals={'retry': (None, 'optional retry override; forwarded to stream, no filter effect')},
    profile='request-budgeted-iterator',
)


def _fixture_state(client, combo, trial):
    client.documents[f'users/{UID}/chat_first_e2e_harness/state'] = {'fixture_case': 'enabled', 'fixture_revision': 1}


_driver(
    'utils.task_intelligence.chat_first_e2e_fixture._existing_feature_refs',
    base={'uid': UID},
    profile='operational-offline-fixture',
    serving=False,
)
_driver(
    'utils.task_intelligence.chat_first_e2e_fixture._snapshot_from_rows',
    base={'uid': UID},
    neutrals={'prepared_state': (None, 'point-read state source only')},
    setup=_fixture_state,
    profile='operational-offline-fixture',
    serving=False,
)
_driver(
    'utils.task_intelligence.chat_first_e2e_fixture.advance_fixture_clock',
    base={'uid': UID, 'seconds': 1},
    setup=_fixture_state,
    patchers=(_stub('utils.task_intelligence.chat_first_e2e_fixture._require_harness', None),),
    profile='operational-offline-fixture',
    serving=False,
)
COVERED_BY['utils.memory.canonical_graph._build_canonical_graph_items_query'] = CoveredByEntry(
    'utils.memory.canonical_graph._build_canonical_graph_items_query',
    ('utils.memory.canonical_graph._read_canonical_graph_page_once',),
    'pure builder; real first/resumed page terminals execute in the named consumer',
    expect_observed=False,
    body_digest=BODY_DIGEST['utils.memory.canonical_graph._build_canonical_graph_items_query'],
)
for key, reason in {
    'parakeet.stream_handler._NemoRNNTStreamingDecoder.decode_pcm': 'AST false positive: torch.where selects tensor elements, not a Firestore query',
    'routers.desktop_proxy._read_request_body': 'AST false positive: Request.stream reads the incoming HTTP body',
    'utils.multipart._size_limited_stream': 'AST false positive: Request.stream reads the incoming multipart HTTP body',
    'utils.multipart.parse_multipart_form': 'AST false positive: Request.stream reads the incoming multipart HTTP body',
}.items():
    SKIPS[key] = SkipEntry(key, reason, BODY_DIGEST[key])
