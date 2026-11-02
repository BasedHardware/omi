"""Dedicated batch scheduler indexes, including admissible capacity counts."""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def _asc(field):
    return FirestoreIndexField(field, order='ASCENDING')


BATCH_PIPELINE_INDEX_REQUIREMENTS = (
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
)
