"""Live metadata reads for sync decisions that never consume photos or text.

These reads are deliberately not cached: redirect/deletion/cleanup revisions
must be checked again after external bridge effects, including audio copying.
"""

from typing import Any

from prometheus_client import Counter

from config.firestore_read_levers import lever_enabled
from models.finalization_owner import ENGINE_FIELD, EPOCH_FIELD

READS = Counter(
    'omi_sync_backfill_metadata_reads_total',
    'Sync metadata-only reads, without conversation photo hydration',
    ['operation'],
)

BRIDGE_FIELDS = [
    ENGINE_FIELD,
    EPOCH_FIELD,
    'sync_bridge_pending',
    'id',
    'deleted',
    'sync_merged_into',
    'sync_merged_from',
    'smart_merge.role',
    'sync_content_revision',
    'sync_bridge_cleaned_revision',
    'sync_bridge_audio_target',
    'private_cloud_sync_enabled',
]
# The sync route hands this row to the registered-record router as its loaded
# conversation, so it also carries the record-finality markers that router
# reads (``live_upload.coverage_final``); a field missing here reads as "not
# final" and keeps the retryable wait. Same single document read.
PROVENANCE_FIELDS = [
    'id',
    'client_device_id',
    'started_at',
    'finished_at',
    'record_lane_owner',
    'source',
    'uses_custom_stt',
    'deleted',
    'record_audio_closed',
    'record_audio_partial',
    'record_sealed_at',
    'record_seal_refused_at',
    'record_upload_sessions',
]


def read_metadata(database: Any, uid: str, conversation_id: str, *, operation: str) -> dict | None:
    if not lever_enabled('backfill_task_reads', uid):
        return database.get_conversation(uid, conversation_id)
    fields = BRIDGE_FIELDS if operation == 'bridge' else PROVENANCE_FIELDS
    row = database.get_conversation_raw_snapshot(uid, conversation_id, field_paths=fields)
    READS.labels(operation=operation).inc()
    # Existence and truthiness must agree even for a legacy document without
    # the stored id field. No caller uses this synthesized id for routing.
    if row is not None:
        row.setdefault('id', conversation_id)
    return row
