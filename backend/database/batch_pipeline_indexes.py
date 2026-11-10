"""Dedicated batch scheduler indexes, including admissible capacity counts."""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def _asc(field):
    return FirestoreIndexField(field, order='ASCENDING')


BATCH_PIPELINE_INDEX_REQUIREMENTS = (
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
)
