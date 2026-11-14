"""Dedicated batch scheduler indexes, including admissible capacity counts."""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def _asc(field):
    return FirestoreIndexField(field, order='ASCENDING')


def _desc(field):
    return FirestoreIndexField(field, order='DESCENDING')


BATCH_PIPELINE_INDEX_REQUIREMENTS = (
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_fresh_guard_{"pending" if pending else "total"}',
            f'batch_pipeline_{stage}_results',
            'COLLECTION',
            (_asc('fresh_capture'),)
            + ((_asc('projection_state'),) if pending else ())
            + (_asc('committed_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
        for pending in (False, True)
    ),
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_{"fresh_" if fresh else ""}pending_nonterminal',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            tuple(
                _asc(field)
                for field in ('owner_key', 'merge_pending')
                + (('fresh_capture',) if fresh else ())
                + ('capture_at', 'segment_id', 'state', '__name__')
            ),
        )
        for stage in ('prod', 'dev')
        for fresh in (False, True)
    ),
    # Repair keeps the existing ascending index for result-ready consumers and rollback.
    *(
        FirestoreIndexRequirement(
            f'{namespace}_record_repair_newest',
            f'{namespace}_jobs',
            'COLLECTION',
            (_asc('state'), _desc('enqueued_at'), _desc('__name__')),
        )
        for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    ),
    *(
        FirestoreIndexRequirement(
            f'{namespace}_record_repair_deadline',
            f'{namespace}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('record_dead_letter_deadline_at'), _asc('__name__')),
        )
        for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    ),
    FirestoreIndexRequirement(
        'record_seal_repair_newest_completed',
        'conversations',
        'COLLECTION_GROUP',
        (_asc('record_lane_owner'), _asc('status'), _desc('finished_at'), _desc('__name__')),
    ),
    # Shared by result-ready draining and oldest-first record-pending repair.
    # Moved from sync_pipeline_indexes; retain its existing registry identity.
    *(
        FirestoreIndexRequirement(
            f'{namespace}_result_ready',
            f'{namespace}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('enqueued_at'), _asc('__name__')),
        )
        for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    ),
    *(
        FirestoreIndexRequirement(
            f'{namespace}_seal_pending_finished',
            f'{namespace}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('record_snapshot.finished_at'), _asc('__name__')),
        )
        for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    ),
    FirestoreIndexRequirement(
        'record_seal_repair_oldest_completed',
        'conversations',
        'COLLECTION_GROUP',
        (_asc('record_lane_owner'), _asc('status'), _asc('finished_at'), _asc('__name__')),
    ),
    # Newest-first operator discovery for the reversible no-speech terminal.
    # Equality on owner/status, then the capture clock descending.
    FirestoreIndexRequirement(
        'record_no_speech_newest',
        'conversations',
        'COLLECTION_GROUP',
        (_asc('record_lane_owner'), _asc('status'), _desc('created_at'), _desc('__name__')),
    ),
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_ramp_owner_load',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('owner_id'), _asc('enqueued_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_ready_predecessor',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('owner_key'), _asc('priority'), _asc('state'), _asc('next'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_capacity_ready',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (
                _asc('priority'),
                _asc('state'),
                _asc('merge_pending'),
                _asc('compute_decision.outcome'),
                _asc('available_at'),
                _asc('__name__'),
            ),
        )
        for stage in ('prod', 'dev')
    ),
    # 2-hour timeliness alarm: committed units whose projection receipt is quarantined (job recovery_state held).
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_timeliness_assignment_held',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('recovery_state'), _asc('enqueued_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Current replacement-object clock; legacy objects reuse the enqueue index.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_staged_input_age',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('recovery_state'), _asc('audio_staged_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Additive expiry markers retain the legacy quarantine_held state.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_projection_expired_age',
            f'batch_pipeline_{stage}_results',
            'COLLECTION',
            (_asc('held_expired_reason'), _asc('projection_state'), _asc('committed_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Its terminal_empty count: failed held, empty_asr, no measured held VAD speech.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_timeliness_terminal_empty',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (
                _asc('state'),
                _asc('recovery_state'),
                _asc('recovery.failure.reason'),
                _asc('measured_held_vad_speech_seconds'),
                _asc('enqueued_at'),
                _asc('__name__'),
            ),
        )
        for stage in ('prod', 'dev')
    ),
    # W3 census (SCA-1921): declarative only, no live index creation.
    # Settled-not-delivered count and the exact custody clock of unmerged results.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_settled_not_delivered',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('provider_intent.settled_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Fresh-capture wait gauge per state; fresh_capture is stamped at admission.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_fresh_oldest',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('fresh_capture'), _asc('enqueued_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Provider outbox census oldest age and the 31-day custody leg.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_provider_outbox_created',
            f'batch_pipeline_{stage}_provider_stt_outbox',
            'COLLECTION',
            (_asc('state'), _asc('created_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Runnable-vs-parked provider stock; due_at is the wake clock.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_provider_outbox_due',
            f'batch_pipeline_{stage}_provider_stt_outbox',
            'COLLECTION',
            (_asc('state'), _asc('due_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Custody horizon for assignment and quarantine holds on result receipts.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_projection_held_deadline',
            f'batch_pipeline_{stage}_results',
            'COLLECTION',
            (_asc('projection_state'), _asc('held_deadline_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Fleet-wide memory-outbox census. The existing same-field index is
    # COLLECTION-scoped and serves only the per-user worker page; rows live under
    # {user_root}/memory_outbox, so the census needs the group-scoped twin.
    FirestoreIndexRequirement(
        'memory_outbox_group_status_available_at',
        'memory_outbox',
        'COLLECTION_GROUP',
        (_asc('status'), _asc('available_at'), _asc('__name__')),
    ),
    # W3 census exporter (SCA-2119). Oldest-age readings order each stock by its
    # own clock, so every (state, clock) pair the registry declares needs its own
    # composite. Declarative only: code never creates these in production.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_jobs_{name}',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc(field), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
        for name, field in (
            ('held_deadline', 'held_deadline_at'),
            ('superseded', 'superseded_at'),
        )
    ),
    # Recovery-intent census: recovery_state equality ordered by acceptance.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_recovery_age',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('recovery_state'), _asc('enqueued_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
    ),
    # Ready split: runnable (unattempted/allowed) ordered by acceptance, and
    # parked holds ordered by the refusal clock. Two stocks, two composites,
    # because Firestore requires an inequality field to lead the ordering and a
    # split expressed as one filtered query would poison the oldest age.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_ready_{name}',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (_asc('state'), _asc('compute_decision.outcome'), _asc(field), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
        for name, field in (('runnable', 'enqueued_at'), ('parked', 'compute_decision.at'))
    ),
    # Allowance/budget holds: equality on the decision outcome, a bounded
    # reason set, then the decision clock. The count and the oldest age use the
    # same composite; ``in`` on a leading field is served by this ordering.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_compute_hold',
            f'batch_pipeline_{stage}_jobs',
            'COLLECTION',
            (
                _asc('compute_decision.outcome'),
                _asc('compute_decision.reason'),
                _asc('compute_decision.at'),
                _asc('__name__'),
            ),
        )
        for stage in ('prod', 'dev')
    ),
    # Speaker final-pass outbox: open rows and closed receipts waiting for their
    # repair write. No acceptance clock exists, so ``due_at`` is the best clock.
    *(
        FirestoreIndexRequirement(
            f'{stage}_batch_census_speaker_outbox_{name}',
            f'batch_pipeline_{stage}_speaker_final_pass_outbox',
            'COLLECTION',
            (_asc(field), _asc('due_at'), _asc('__name__')),
        )
        for stage in ('prod', 'dev')
        for name, field in (('open', 'outcome'), ('terminal', 'terminal_pending'))
    ),
    # Enrichment outbox: the whole collection is one stock (no filter), and the
    # two durable sub-stocks filter on a boolean before the acceptance clock.
    *(
        FirestoreIndexRequirement(
            f'enrichment_outbox_{name}',
            'sync_reprocess_outbox',
            'COLLECTION',
            (_asc(field), _asc('first_pending_at'), _asc('__name__')),
        )
        for name, field in (('parked', 'age_gate_parked'), ('sync_hold', 'sync_hold'))
    ),
    # Live admission and the later ledger stages, collection-group scoped.
    FirestoreIndexRequirement(
        'pipeline_ledger_group_stage_admitted_at',
        'pipeline_ledger',
        'COLLECTION_GROUP',
        (_asc('stage'), _asc('admitted_at'), _asc('__name__')),
    ),
)
