"""Notes for a live window once listen sealed its last recording on speech quiet.

Batch recordings carry no transcript until they seal, so quiet is listen's own VAD
quiet seal: a sealed recording without the rotation cap stamp. The five-minute close
and final processing are unchanged; final processing reuses these notes when no
speech followed (summary_covers_through >= finished_at).
"""

import hashlib
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException
from google.cloud import firestore

from config.conversations_v3 import quiet_notes_enabled
from database import conversations_v3 as store, conversations_v3_leases as leases
from utils.conversations.v3 import metrics, policy, summary
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3.triggers import task_base
from utils.executors import run_blocking, db_executor

logger = logging.getLogger(__name__)

# Paid quiet attempts per window; final processing still owns the result.
CAP = 2


def proven(row, recordings):
    """The live window's last speech is in a transcribed recording listen sealed on quiet."""
    if row.get('status') != 'in_progress' or row.get('home_hidden') or row.get('is_locked'):
        return False
    covers, end = row.get('summary_covers_through'), row.get('finished_at')
    if covers and end and covers >= end:
        return False
    members = [recordings[rid] for rid in row.get('v3_recording_ids') or [] if rid in recordings]
    spoken = [r for r in members if r.get('transcript_segments') and r.get('started_at')]
    if not spoken:
        return False
    last = max(spoken, key=store.speech_end)
    return bool(
        last.get('status') == 'completed'
        and last.get('finished_at')
        and last.get(policy.ROTATION_CAP_FIELD) is None
        and not last.get('_v3_page_continues')
        and not policy.transcription_pending(last)
    )


def enqueue(uid, row):
    # One task per window end: a retry or a second pass over the same speech dedupes.
    key = hashlib.sha256(f"{uid}:{row['id']}:{row['finished_at'].isoformat()}".encode()).hexdigest()[:40]
    enqueue_named_task(
        os.getenv('CONVERSATIONS_V3_TASKS_QUEUE', 'conversations-v3'),
        task_base() + '/v1/conversations-v3/reconcile',
        'conversations-v3-quiet-' + key,
        {'uid': uid, 'quiet_notes': row['id']},
    )


def _load(uid, cid):
    client = store.get_firestore_client()
    snapshot = store.user_conversations(client, uid).document(cid).get()
    return store.decode_row(uid, snapshot) if snapshot.exists else None


def _reserve(uid, cid, token, *, firestore_client=None):
    """Count one paid attempt under the held summary lease; False once the window spent CAP."""
    client = firestore_client or store.get_firestore_client()
    ref = leases.lease_ref(client, uid, 'summary-' + cid)

    @firestore.transactional
    def spend(tx):
        lease = ref.get(transaction=tx).to_dict() or {}
        spent = int(lease.get('quiet_notes') or 0)
        if lease.get('token') != token or spent >= CAP:
            return False
        tx.update(ref, {'quiet_notes': spent + 1})
        return True

    return spend(client.transaction())


def _live(row):
    return bool(
        row
        and row.get('v3_derived')
        and row.get('status') == 'in_progress'
        and not row.get('deleted')
        and not row.get('home_hidden')
        and not row.get('is_locked')
        and not row.get('recording')
    )


async def run(uid, cid):
    if not quiet_notes_enabled(uid):
        return 'disabled'
    row = await run_blocking(db_executor, _load, uid, cid)
    if not _live(row):
        return 'skipped'
    from utils.conversations.v3 import service
    from utils.generated_compute import require_generated_compute

    try:
        await run_blocking(db_executor, require_generated_compute, uid, 'conversation_v3_summary_open')
    except HTTPException:
        return 'denied'
    # The outline (kind, title, visibility) runs as it does when the owner opens the row.
    if await service.reconcile(uid, on_open=True, conversation_id=cid) == 'busy':
        return 'busy'
    row = await run_blocking(db_executor, _load, uid, cid)
    if row is None or not _live(row) or summary.fresh(row) or not summary.summary_eligible(row):
        return 'skipped'
    try:
        token = await summary.prepare(uid, row)
    except HTTPException:
        return 'busy'
    if token is None:
        return 'skipped'
    if not await run_blocking(db_executor, _reserve, uid, cid, token):
        await run_blocking(db_executor, leases.release, uid, 'summary-' + cid, token)
        return 'capped'
    metrics.MODEL_CALLS.labels('quiet_notes').inc()
    outcome = 'failed'
    # stream() owns the write, its revision fence and the lease release.
    async for frame in summary.stream(uid, row, token=token):
        if frame.startswith('done:'):
            outcome = 'stored'
    logger.info(
        'event=v3_quiet_notes outcome=%s speech_end_to_notes_seconds=%.0f',
        outcome,
        (datetime.now(timezone.utc) - row['finished_at']).total_seconds(),
    )
    return outcome
