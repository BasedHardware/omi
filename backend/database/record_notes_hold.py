"""Delivery-only producer fence for completion-owned recording notes."""

from config.record_audio import require_record_audio_barrier
from database import pipeline_ledger
from utils.sync.processing_hold import MAX_HOLD_SECONDS

RETRY_SECONDS = 120  # Existing enrichment delivery cadence; no additional poller.


def inspect(client, uid, producers):
    """Read current custody, including upload revision, before a paid callback."""
    blocked = []
    for capture_id, revision in producers.items():
        ref = client.collection('users').document(uid).collection('conversations').document(capture_id)
        snapshot = ref.get()
        row = snapshot.to_dict() or {}
        try:
            require_record_audio_barrier(row)
            if row.get('record_audio_partial') or not row.get('record_audio_closed'):
                raise ValueError('partial record is not complete')
            if row.get('record_upload_revision') != revision:
                raise ValueError('new upload has not projected')
        except ValueError:
            blocked.append((ref, snapshot, row))
    return blocked


def deadline(row):
    return float(row['first_pending_at']) + MAX_HOLD_SECONDS


def record_timeout(client, uid, blocked, *, now):
    """After the real outbox park commits, record its fenced lifecycle outcome."""
    for ref, snapshot, row in blocked:
        pipeline_ledger.advance(
            uid,
            ref.id,
            pipeline_ledger.failed_stage('timeout'),
            reason='timeout',
            now=now,
            end_at=row.get('finished_at'),
            revision=max(1, pipeline_ledger.source_revision(snapshot)),
            reopen=True,
            source_ref=ref,
            owner_ref=client.collection('users').document(uid),
            firestore_client=client,
        )
