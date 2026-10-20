"""Sync dispatch and dormant batch queue index ownership.

The legacy sequencer requirements are preserved exactly; batch requirements
are stage-isolated. Exported through firestore_index_registry only.
"""

from database.firestore_query_types import FirestoreIndexField, FirestoreIndexRequirement


def _asc(field_path: str) -> FirestoreIndexField:
    return FirestoreIndexField(field_path, order='ASCENDING')


# Stage-isolated dormant batch queue. Test namespaces run on the emulator only.
_BATCH_PIPELINE_INDEXES = tuple(
    FirestoreIndexRequirement(f'{namespace}_{name}', f'{namespace}_jobs', 'COLLECTION', fields + (_asc('__name__'),))
    for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    for name, fields in (
        ('merge', (_asc('owner_key'), _asc('merge_pending'), _asc('capture_at'), _asc('segment_id'))),
        (
            'merge_ready',
            (_asc('owner_key'), _asc('merge_pending'), _asc('state'), _asc('capture_at'), _asc('segment_id')),
        ),
        ('merge_ready_age', (_asc('owner_key'), _asc('merge_pending'), _asc('state'), _asc('ready_at'))),
        (
            'merge_fresh',
            (_asc('owner_key'), _asc('merge_pending'), _asc('fresh_capture'), _asc('capture_at'), _asc('segment_id')),
        ),
        ('recovery', (_asc('owner_id'), _asc('recovery_state'))),
        ('lease', (_asc('state'), _asc('lease_until'))),
        ('retry', (_asc('state'), _asc('available_at'))),
        ('result_ready', (_asc('state'), _asc('enqueued_at'))),
        ('predecessor', (_asc('next'), _asc('state'))),
        ('ready_age', (_asc('priority'), _asc('state'), _asc('enqueued_at'))),
        ('retry_age', (_asc('priority'), _asc('retry_started_at'))),
        ('pending_age', (_asc('priority'), _asc('merge_pending'), _asc('enqueued_at'))),
    )
)

_BATCH_PROJECTION_INDEXES = tuple(
    FirestoreIndexRequirement(
        f'{namespace}_projection',
        f'{namespace}_results',
        'COLLECTION',
        (_asc('projection_state'), _asc('committed_at'), _asc('__name__')),
    )
    for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
)

_BATCH_CONTROL_INDEXES = tuple(
    FirestoreIndexRequirement(
        f'{namespace}_control_{priority}_{pool}',
        f'{namespace}_control',
        'COLLECTION',
        (
            _asc(f'p{priority}_active'),
            _asc(f'p{priority}_service'),
            _asc(f'p{priority}_{pool}_available_at'),
            _asc('__name__'),
        ),
    )
    for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev')
    for priority in (0, 1, 2)
    for pool in ('batch', 'live')
)

SYNC_PIPELINE_INDEX_REQUIREMENTS = (
    FirestoreIndexRequirement(
        'sync_backfill_pending_uid_sort',
        'sync_backfill_pending',
        'COLLECTION',
        (_asc('uid'), _asc('sort_at'), _asc('__name__')),
    ),
    FirestoreIndexRequirement(
        'sync_backfill_pending_uid_sort_newest',
        'sync_backfill_pending',
        'COLLECTION',
        (
            _asc('uid'),
            FirestoreIndexField('sort_at', order='DESCENDING'),
            FirestoreIndexField('__name__', order='DESCENDING'),
        ),
    ),
    FirestoreIndexRequirement(
        'sync_backfill_pending_uid_accepted',
        'sync_backfill_pending',
        'COLLECTION',
        (_asc('uid'), _asc('accepted_at'), _asc('__name__')),
    ),
    *_BATCH_PIPELINE_INDEXES,
    *_BATCH_PROJECTION_INDEXES,
    *_BATCH_CONTROL_INDEXES,
)
