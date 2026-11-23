"""Recurring row selectors covered by the batch/sync census guard."""

from dataclasses import dataclass, replace
from datetime import date

STATE_FIELDS = frozenset(
    {
        'state',
        'status',
        'stage',
        'projection_state',
        'recovery_state',
        'merge_pending',
        'active',
        'held',
        'dormant',
        'record_lane_owner',
        'summary_lane',
        'retry_started_at',
    }
)

# Writer-owned eligibility/deadline clocks. Capture, commit, creation and
# enqueue timestamps are chronology. A bound against now on those fields
# usually admits the same blocked prefix again.
DUE_FIELDS = frozenset(
    {
        'available_at',
        'due_at',
        'next_attempt_at',
        'next_check_at',
        'retry_at',
        'check_at',
        'lease_until',
        'reclaim_at',
        'repair_after',
        'scan_at',
        'release_by',
        'cleanup_after',
        'write_pending_until',
        'held_deadline_at',
        'projection_finish_due_at',
        'projection_followup_due_at',
        'record_dead_letter_deadline_at',
    }
)

COLLECTION_PREFIXES = ('batch_pipeline_', 'sync_', 'stt_cap_holds')
CALLER_PREFIXES = (
    'database.batch_pipeline_',
    'database.lifecycle_metrics_queries.',
    'database.record_seal_worker.',
    'database.outbox_provider_stt.',
    'utils.batch_pipeline.',
    'utils.processing_backlog_worker.',
)


@dataclass(frozen=True)
class SelectorException:
    owner: str
    reason: str
    max_rows: int
    cadence: str
    expiry: date
    removal: str
    body_digest: str


def _legacy(reason, max_rows, cadence, removal, body_digest, *, owner='batch owner-state / lead2'):
    return SelectorException(owner, reason, max_rows, cadence, date(2026, 12, 18), removal, body_digest)


# Exceptions pin the executable builder and its response bound. A cursor in
# one page proves neither that a caller advances it nor that it stops at EOF.
EXCEPTIONS: dict[str, SelectorException] = {
    'utils.batch_pipeline.parked_sweep.parked_page': _legacy(
        'SCA-3880 diagnosis includes parked rows even when no decision is due',
        100,
        'two streams per admitted UTC hour',
        'Replace with a bounded aggregate producer when approved',
        'da2b485ed38e298907a382661ed5a05399d922ee1c3f06a5281cf54f1108d879',
        owner='omi-pipeline',
    ),
    'database.batch_census_export.sample_entry': _legacy(
        'A single clock-only row accompanies the aggregate stock count',
        1,
        'census publisher tick',
        'Replace with a stamped stock age counter',
        'c847de7312f7c9597ab1d31b2ef02b6142679459ef9ca32b9c12ee45f560e209',
    ),
    'database.batch_pipeline_allowance_migration.apply_page': _legacy(
        'Legacy allowance migration checkpoints progress after successful fenced work',
        100,
        'operator-paced one-off page',
        'Remove the migration after old retry stock is retired',
        'e35642c43b85be89615421ae50a40dc92ea4339e10489e6d4b17f2e1c0da414f',
    ),
    'database.batch_pipeline_delivered_share.delivered_share_page': _legacy(
        'Fixed healthy-age audit cohort with explicit truncation',
        5000,
        'one elected sample per 300 seconds',
        'Move to retained admission and acknowledgement deltas',
        'f97812675cfa48f7538cc1e71f73008c8321914890b536d27501670623a0b005',
    ),
    'database.batch_pipeline_privacy_queries.predecessor_documents': _legacy(
        'Keyed predecessor existence check by unique next segment',
        1,
        'per erasure or recovery link repair',
        'Use an explicit predecessor pointer on the scoped row',
        '836c8042c4375b7c745bca10f5ad0d7a97d9ab47e350e0e567975625b0e022da',
    ),
    'database.batch_pipeline_projection_release.assignment_held_page_ids': _legacy(
        'Legacy held assignment without indexed recheck deadline',
        128,
        'held release pass or bounded continuation',
        'Select only due held assignment obligations',
        '9d78139625c8b2e6ad26ddeca7b7112a97c38cf12591ec37bad882ee25d4dbe1',
    ),
    'database.batch_pipeline_projection_release.expired_page_ids': _legacy(
        'Legacy terminal-hold audit page can wrap',
        128,
        'held release pass or bounded continuation',
        'Use terminal disposition and expiry events',
        '663f9a4e441c9736c8b9535063053406db89757a2837fd5691747a9b11274401',
    ),
    'database.batch_pipeline_projection_release.held_page_ids': _legacy(
        'Legacy projection holds lack a per-row wait deadline',
        128,
        'held release pass or bounded continuation',
        'Select only due held projection obligations',
        'c11beeb296e7598f70469206b31c5f380c1ce146a769f11f3eb1622bacf2bd60',
    ),
    'database.batch_pipeline_quarantine_recovery.dead_held_candidates': _legacy(
        'Revisits dead-letter rows during compatibility recovery',
        64,
        'held maintenance pass',
        'Select explicitly recoverable due debt',
        '9fb189fd290b893b22a2aad89f5f8442d0b30467532ea2a98c4d8018d7e27951',
    ),
    'database.batch_pipeline_quarantine_recovery.held_candidates': _legacy(
        'Legacy held candidate page lacks actionable deadline',
        64,
        'held maintenance or operator recovery pass',
        'Select indexed per-row recovery deadline',
        'b306b2cb803f1a5d41c2c641a16238ca0332f25e17e1edf6642b612767dd8093',
    ),
    'database.batch_pipeline_quarantine_recovery.input_expiring_candidates': _legacy(
        'Legacy missing-stage fallback uses enqueue age as an expiry hint',
        128,
        'held input expiry pass per clock',
        'Qualify a stamped input expiry deadline',
        '09da7b2912e046db6f0f12cd3a97f317827a24ec958d107bcc07a8d733a8eb9d',
    ),
    'database.batch_pipeline_quarantine_recovery.recovery_candidates': _legacy(
        'Legacy quarantine state page precedes execution fences',
        64,
        'recovery pass or targeted owner recovery',
        'Use a due recovery inbox and retire state scan',
        '5478f61d1c0e469d9fd933d112eec9600ce004b0b61e04b9753edc9535a8bf2d',
    ),
    'database.batch_pipeline_shadow.pool_busy': _legacy(
        'Compatibility readiness hint can sample ready stock without the due clock',
        501,
        'shadow idle offer',
        'Consume native owner-ready signal',
        '3271526b1874264be83007b0e309aa2d7371c7d2a47fc73e06ca3fd8fc9db582',
    ),
    'database.batch_pipeline_store.FirestoreStore.allowance_page': _legacy(
        'Legacy allowance inventory walks the owner on an elected tick',
        100,
        'allowance recheck per owner page',
        'Consume due tagged holds from owner ledger',
        'd8107c29516ad6f8d65326dabcbd0b6748cf7445c8c16446577a31fa7c15a30b',
    ),
    'database.batch_pipeline_store.FirestoreStore.packing_candidates': _legacy(
        'Projected owner prefix includes intervening unready rows to detect order barriers',
        17,
        'at most one in flight per process at sampled leases',
        'Retire with the packing experiment',
        '7b14ddbc399882c0616a59f5319cd5d169cdbd54c9f8d53da60c5c9b1fc2a643',
    ),
    'database.batch_pipeline_store.due': _legacy(
        'Result-ready compatibility branch uses enqueue chronology',
        500,
        'serving recovery or result drain pass',
        'Retire legacy result-ready drain after owner wake qualification',
        'd455f63f4e511824ad3f8a1f8e2c547103a59fb3215eeaa7c7e15ecc8cddf6f0',
    ),
    'database.batch_pipeline_store.first_ready_pending': _legacy(
        'Merge waits on a compatibility result prefix',
        1,
        'per merge owner head decision',
        'Use the indexed owner result head',
        'a6400a6f21ee7da939a745b27b010b027b42f3703a8c8021bf415fba926d14f8',
    ),
    'database.batch_pipeline_store.fresh_first_pending': _legacy(
        'Fresh head selection uses merge stock and capture ordering',
        1,
        'per merge or pull owner head decision',
        'Use the indexed owner fresh head',
        'd86a166225044ba735efb7deefe16690c8e4c8ec99cc346280cd7c7ae6f6ca08',
    ),
    'database.batch_pipeline_store.fresh_pending': _legacy(
        'Existing fresh result and predecessor ordering',
        32,
        'per bounded owner merge pass',
        'Use the indexed owner fresh head',
        'ce0661bf89c35c56442397fc4787146dcf76b16b3ce978da53ff78d44ee51e63',
    ),
    'database.batch_pipeline_store.held_merge_owners': _legacy(
        'Legacy held marker page lacks per-owner recheck clock',
        100,
        'held owner maintenance pass',
        'Use owner recheck deadline',
        '13aa38693bb7a0d90097e97cd3e92fcd8fbe8d3f9857a58af1abad2f04362e69',
    ),
    'database.batch_pipeline_store.longest_ready_pending': _legacy(
        'Oldest ready sibling determines bounded legacy head wait',
        1,
        'per merge owner head decision',
        'Use owner head wait deadline',
        '8b8995f03dd5487d71b15651c38e49ff742767e2c5bf7f8f06fcb629824031d3',
    ),
    'database.batch_pipeline_store.oldest': _legacy(
        'Bounded queue gauge reports truncation instead of healthy zero',
        501,
        'queue-age publisher refresh',
        'Publish elected transition age samples',
        '37d3d523882ce5ba6cc0a5e863d04e8d42101d38b279cd502226ad163ffb137e',
    ),
    'database.batch_pipeline_store.oldest_admissible_ready': _legacy(
        'Bounded age hint rechecks admission clocks in application code',
        20,
        'capacity publisher refresh',
        'Publish a versioned due-age sample',
        '483802c7a625f43aed89a5717307373bbeed2bfc9778e14e9ef6d7a2b1b534e0',
    ),
    'database.batch_pipeline_store.oldest_retry': _legacy(
        'The retry clock lower bound measures age across dispositioned rows',
        501,
        'queue-age publisher refresh',
        'Publish elected retry-age samples',
        '35e2e1cffa1bfd49035334a0f06abe1cbd9b8af5b840eb9a417c26d0d756a842',
    ),
    'database.batch_pipeline_store.pending_page': _legacy(
        'Indexed compatibility capture-order prefix includes non-ready rows',
        160,
        'per bounded merge or pull owner decision',
        'Use indexed owner head and due projection events',
        'd8b65c2f63c59201f71cd1b25a72bd8eb0706cca7491421ab697744955619a1d',
    ),
    'database.batch_pipeline_store.projection_page': _legacy(
        'Legacy assignment and follow-up paths can revisit a state prefix',
        200,
        'projection sweep or bounded continuation',
        'Migrate to durable projection wake and qualified due readers',
        '316ffc0964dd270cd73c7e019125723cbeb88f64819d217463e68535975269c0',
    ),
    'database.batch_pipeline_store.protected_capture_page': _legacy(
        'Capture window enforces service cohort while availability is checked locally',
        25,
        'bounded protected pull or retry pass',
        'Select due owner head by protected service group',
        'd3e4d37956edb6ef6553c0bcd4b9616925408271654e673e14d94e3edf5f876e',
    ),
    'database.batch_pipeline_store.ready_owners': _legacy(
        'Durable compatibility cursor wraps at pass exhaustion',
        1,
        'one row per owner during bounded drain discovery',
        'Consume the native owner due index',
        'f1baf1d323a037e2801c4d84e7366b3e0b451d41bfd507a43bccbf8a43e4e180',
    ),
    'database.batch_pipeline_store.ready_pending': _legacy(
        'Compatibility sibling scan uses capture order',
        160,
        'per blocked sibling merge page',
        'Use exact due projectable sibling links',
        '2913c6114269ccdc457332b03500c46a801ce1f3f2efba0b042255aa6b2de611',
    ),
    'database.batch_pipeline_store.ready_predecessor': _legacy(
        'Keyed unique next-segment predecessor lookup',
        2,
        'per scheduler head splice',
        'Retire FIFO splice with indexed head selection',
        'ed109d15aa03ae331d901c47b2ab4089dabc26dd7de9ad0df43b718e19ce41d4',
    ),
    'database.batch_pipeline_store.timeliness_sample': _legacy(
        'Bounded current age probe preserves release guard',
        20,
        'timeliness publisher refresh',
        'Publish versioned age samples',
        'bb1b9b5e5078d9411d6e413d0e8f21d5fb69698dcfd61b2865c130ccca5b9a97',
    ),
    'database.batch_pipeline_store.timeliness_sample.<locals>.committed_walk': _legacy(
        'Bounded committed cohort samples projection debt',
        50,
        'timeliness publisher refresh',
        'Publish versioned projection debt samples',
        'e54553be452b3edce7c486fbe50a81ec362fca9317ba15199a8bf5872506e332',
    ),
    'database.batch_pipeline_store.timeliness_sample.<locals>.first': _legacy(
        'Age audit samples one cohort head',
        1,
        'timeliness publisher refresh',
        'Publish versioned age samples',
        'e5508540a5f9060dcf6ca67e049d01a2348cc07754b387c67492e259a20d147a',
    ),
    'database.batch_pipeline_store.timeliness_sample.<locals>.first_valid_clock': _legacy(
        'Clock-only audit measures the oldest matching row',
        1,
        'timeliness publisher refresh',
        'Publish versioned age samples',
        '007010141499393c3a16af93bf2795c13bb252966cfdfcca5d642d8bb40508f5',
    ),
    'database.batch_pipeline_store.timeliness_sample.<locals>.walk': _legacy(
        'Bounded cohort page examines held debt',
        20,
        'timeliness publisher refresh',
        'Publish versioned age samples',
        'a313956aa4902d258910a4864cad206fbeaf4fdea1eb2ea6d064f7acd90fcddc',
    ),
    'database.cap_hold_redrive.fleet_snapshot': _legacy(
        'Oldest hold age audit accompanies count aggregation',
        1,
        'elected cap-hold gauge tick',
        'Publish aged hold distribution from owner transitions',
        '54e8d24f17d471a0a1093e1fb2ec04958085dcb58090105826e18f1ce022cbd0',
    ),
    'database.cap_hold_redrive.page': _legacy(
        'Compatibility bounded state page rechecks owner in the handler',
        50,
        'cap-hold recovery pass',
        'Select only actionable due holds',
        'c85ff7dbd8ed51bed8d8cb08021320807e3e19e11fa01c95fa0dcee13c5c8325',
    ),
    'database.lifecycle_metrics_queries.blocked_byok': _legacy(
        'Bounded BYOK time-window audit is separate from action selection',
        1000,
        'lifecycle gauge refresh',
        'Publish age distribution from lifecycle transitions',
        '0b1e65036e7db932ce672473195f8060b73b055c6e91fbae70d203c87c2d5995',
    ),
    'database.lifecycle_metrics_queries.enrichment': _legacy(
        'Bounded lane age sample surfaces old debt and cap',
        1000,
        'lifecycle gauge refresh',
        'Publish age distribution from enrichment transitions',
        '69cddf42201bc5d800614992ada8c09126d377eef3734f1c842a08de989e5cbc',
    ),
    'database.lifecycle_metrics_queries.nojob': _legacy(
        'Bounded no-job audit reconciles recorded custody by keyed existence',
        128,
        'lifecycle gauge refresh',
        'Keep independently sampled custody audit with due/revision evidence',
        '6019e44ec31184e74ef1fd3bcc442ca34fb3943f50421b377c24a951b0eb675e',
    ),
    'database.lifecycle_metrics_queries.provider_stage': _legacy(
        'One stage age sample accompanies capped aggregate',
        1,
        'lifecycle gauge refresh',
        'Publish stage age from CAS transitions',
        'e8105374d20ef71fc2b3f1c48e1b987d28f02f3f540cd2f3d22a7d7232c6d3ee',
    ),
    'database.lifecycle_metrics_queries.record_pending': _legacy(
        'Bounded cohort head alongside capped aggregate',
        1000,
        'lifecycle gauge refresh',
        'Publish due intake age from native record wake',
        'c29efbe288718aa2c754bdab64c884ed3d69856bcf65131c47a0c71e48d93471',
    ),
    'database.lifecycle_metrics_queries.vendor_held': _legacy(
        'One vendor-hold age sample accompanies capped aggregate',
        1,
        'lifecycle gauge refresh',
        'Publish vendor-hold age from transition events',
        'fb5ee9832ae5fa5f8a298194fc51d070e7e0d75e6cbe6b9c108226e89ffb8dd2',
    ),
    'database.outbox_provider_stt.FirestoreProviderSttOutbox.claim': _legacy(
        'Legacy open candidates recheck due and lease after selection',
        100,
        'per provider worker pull',
        'Retire legacy state-first provider claims',
        'af8624d2b1b48dee230e2b15b8321db8d03f7f3e4bd712145bcae5fb508b41a7',
    ),
    'database.outbox_provider_stt.FirestoreProviderSttOutbox.sweep': _legacy(
        'Wrapping compatibility provider sweep checks due only after loading',
        500,
        'provider wake backstop tick',
        'Select only actionable due provider wakes',
        '6588b6d522fa48ef361b80752381e41491c281501b45d3df586a5c4f67d58176',
    ),
    'database.record_seal_worker.pending_page': _legacy(
        'Legacy seal readiness depends on capture barrier checks after page',
        64,
        'record seal worker tick',
        'Use native due record intake wake',
        '36efb44fd6219aa259981a2f04ef8fd8c8977eb6342f79b946f7f48b7df66698',
    ),
    'utils.batch_pipeline.record_seal_cluster_repair.discover': _legacy(
        'Bounded no-job scan examines recorded custody',
        128,
        'seal repair discovery pass',
        'Use native seal-snapshot obligation',
        'e13094fa201c06e0a40655dc31bdf9199b14d727cf6898fc9e9d0ec31575c845',
    ),
    'utils.batch_pipeline.record_seal_cluster_repair.discover_jobs.<locals>.page_for': _legacy(
        'Legacy capture and enqueue branches remain while newer deadline qualifies',
        128,
        'seal repair discovery pass',
        'Retire age-only repair queries after deadline coverage',
        'fdf4526b74d1915d15d7afdd80e114a460759ecdce7bdd022626b2405a0c99a5',
    ),
    'utils.batch_pipeline.record_seal_sweeper.discover_pending': _legacy(
        'Compatibility pending-state pass rechecks own deadline after selection',
        32,
        'serving recovery tick',
        'Use native due seal repair clock',
        '3d1a55e35828c27c9b23d4a86901a6b69b4f740b5bf043b36a468e50ff019d34',
    ),
    'utils.processing_backlog_worker._page': _legacy(
        'Hold cursor advances under a bounded recovery budget',
        50,
        'processing recovery pass',
        'Use actionable due hold ledger',
        'd6214d09167635eb7a881d57699e2c8beeee60baa73dfc5716b5b9ee5f161b9b',
    ),
    'utils.sync.held_audio_summary._load_rows': _legacy(
        'Bounded owner-scoped stock read serves a user-visible summary',
        20,
        'requested held-audio summary',
        'Serve exact owner-held census projection',
        '01af0cd6a97ef43cf3cb00987d6da176d425aa64b6e4d8c75999a65cd6e053d7',
    ),
}


# Native Store ports retain the same exception owner and removal condition.
_SQL_PORTS = (
    (
        'PostgresStore.packing_candidates',
        'FirestoreStore.packing_candidates',
        17,
        'fab5c720c3aed731bebafc4b8da8ce25f0f2b932e2e1b50dc34632faad9ea962',
    ),
    (
        'PostgresStore.allowance_page',
        'FirestoreStore.allowance_page',
        100,
        '97c620ed0174520f305a9d143d3794f1a38c45d196936c329ca479adad30e70f',
    ),
    ('PostgresStore.due', 'due', 100, 'c3e6159d781d54bcf3f6c1c8598ecdb3c3c40e3544cb73e7e4e4cec4c1285d04'),
    (
        'PostgresStore.protected_page_in',
        'protected_capture_page',
        100,
        '2a75a103b0cec81d3fc6b370c037a9af4009fc922319b067db60bf75555801f6',
    ),
    ('PostgresStore.oldest', 'oldest', 501, 'ea3844ae53f999df384604161bd8ba1f873d8008587d8c8458fc55d8e14d820c'),
    (
        'PostgresStore.oldest_admissible_ready',
        'oldest_admissible_ready',
        20,
        'e566f34594dcaf7c1ea49a00af569de2c983f36654d1413f3bfb4d3d8c6c09de',
    ),
    (
        'PostgresStore.longest_ready_pending',
        'longest_ready_pending',
        1,
        'f5206834ba56e8cc5fccaabe07b5ed2aaa37632e72aa8ceaec3a2fd6fe0c26e2',
    ),
    (
        'PostgresStore.fresh_pending',
        'fresh_pending',
        32,
        '846a4419b6e632047b99589b0d70f068f483a5c534f71844616e18d49a14bb8d',
    ),
    (
        'PostgresStore.ready_pending',
        'ready_pending',
        160,
        'd5dc921b3138dab5327187efb438929cffded5c32f0aa4160c31690795ad6bf0',
    ),
    (
        'PostgresStore.ready_owners',
        'ready_owners',
        1,
        'b13dd7b6983ece5d8aca44d3fd0f42e4a6f2e2dd976f9ddbf449dc529efabcb6',
    ),
    (
        'PostgresStore.held_merge_owners',
        'held_merge_owners',
        100,
        '0bfaa2d046d66532cb928ed0d04286bb165a191a1325e926333cd34dc00333f4',
    ),
    (
        'PostgresStore.oldest_retry',
        'oldest_retry',
        501,
        '3c90270b73e52703a861a21900fb4c3a8599fa031397714263022a1f23edcb0f',
    ),
    (
        'PostgresStore._projection_page',
        'projection_page',
        200,
        'bacb761635ccee366b1f9c66339a9831923c014b0a2bf05f4a30f2e1670bea51',
    ),
    (
        'PostgresStore.first_pending_in',
        'first_ready_pending',
        1,
        '24b61e9b4f91a6bc1602110b44be64167f2587c6ada251fc29efa5cc5f9819a5',
    ),
    (
        'PostgresStore.pending_page_in',
        'pending_page',
        160,
        'a468b4a9c79f4d3ddca8e23bdfd46a0ca59c2021d1ee17108cfb9a2794d8b1fb',
    ),
    (
        'PostgresTransaction._fresh_first',
        'fresh_first_pending',
        1,
        '23cde8ff0e6dddd0eb41525dbc622930681c2a444bef13cf1dd442f29b687eed',
    ),
)
SQL_EXCEPTIONS = {
    f'database.jobstore.postgres_store.{method}': replace(
        EXCEPTIONS[f'database.batch_pipeline_store.{firestore}'], max_rows=limit, body_digest=digest
    )
    for method, firestore, limit, digest in _SQL_PORTS
}
