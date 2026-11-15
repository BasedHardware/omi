"""Delivery-only producer fence for completion-owned recording notes."""

import uuid

from config.record_audio import require_record_audio_barrier
from database import pipeline_ledger
from utils.sync import processing_hold
from utils.sync.processing_hold import MAX_HOLD_SECONDS

RETRY_SECONDS = 120  # Existing enrichment delivery cadence; no additional poller.


def inspect(client, uid, producers):
    """Read current custody, including upload revision, before a paid callback."""
    blocked, snapshots = [], {}
    for capture_id, revision in producers.items():
        ref = client.collection('users').document(uid).collection('conversations').document(capture_id)
        snapshot = ref.get()
        row = snapshot.to_dict() or {}
        snapshots[capture_id] = row
        try:
            require_record_audio_barrier(row)
            if row.get('record_audio_partial') or not row.get('record_audio_closed'):
                raise ValueError('partial record is not complete')
            if row.get('record_upload_revision') != revision:
                raise ValueError('new upload has not projected')
        except ValueError:
            blocked.append((ref, snapshot, row))
    return blocked, snapshots


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


def merge_producers(existing, incoming):
    result = dict(existing or {})
    for capture_id, revision in (incoming or {}).items():
        prior = result.get(capture_id)
        result[capture_id] = (
            max(prior, revision)
            if prior is not None and revision is not None
            else (prior if revision is None else revision)
        )
    return result


def admit(row, client, *, now):
    """Mutate a due row only when custody refuses; shared by both delivery adapters."""
    if not row.get('record_notes_producers'):
        return None, []
    blocked, sources = inspect(client, row['uid'], row['record_notes_producers'])
    if not blocked:
        canonical = sources.get(row['conversation_id'])
        if canonical is None:
            canonical = (
                client.collection('users')
                .document(row['uid'])
                .collection('conversations')
                .document(row['conversation_id'])
                .get()
                .to_dict()
                or {}
            )
        if processing_hold.FIELD in canonical and processing_hold.enabled_for(canonical):
            # Refreshes need a callback context even before completion; do not restart quiet.
            row['sync_hold'] = True
            origin = (canonical.get(processing_hold.FIELD) or {}).get('merge_first')
            row['merge_hold' if origin else 'sync_hold_requested'] = True
        return None, []
    until = deadline(row)
    if now >= until:
        row.update(
            dormant=True,
            due_at=None,
            lease_until=0,
            owner=None,
            record_notes_producer_timeout_at=now,
            record_notes_producers={},
        )
        return 'stale', blocked
    due = min(now + RETRY_SECONDS, until)
    row.update(
        due_at=due,
        task_due_at=due,
        task_token=uuid.uuid4().hex,
        deferred_reason='record_producer_pending',
        wake_check_after=due,
    )
    return 'deferred', []
