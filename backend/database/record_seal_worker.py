"""Seal discovery hints and expiring metadata claims; no seal authority here."""

from datetime import datetime
import math
import time
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.firestore_read_origin import read_origin
from database._client import run_transactional

CLAIM_SECONDS = 360
BACKOFF_SECONDS = 3600
PAGE_SIZE = 64
ROW_FIELDS = ('status', 'finished_at', 'record_audio_closed', 'record_audio_partial', 'record_lane_owner')


@read_origin('job:record_seal_worker:pending_page')
def pending_page(client, namespace, *, horizon, after=None, limit=PAGE_SIZE):
    """Stable oldest-finish keyset; never scan the closed conversation history."""
    collection = client.collection(f'{namespace}_jobs')
    query = (
        collection.where(filter=FieldFilter('state', '==', 'record_pending'))
        .where(filter=FieldFilter('record_snapshot.finished_at', '<=', horizon))
        .order_by('record_snapshot.finished_at')
        .order_by('__name__')
    )
    if after is not None:
        query = query.start_after({'record_snapshot.finished_at': after[0], '__name__': collection.document(after[1])})
    docs = list(
        query.select(('owner_id', 'conversation_id', 'record_snapshot.finished_at', 'seal_claim'))
        .limit(limit)
        .stream(timeout=10, retry=None)
    )
    cursor = (docs[-1].to_dict()['record_snapshot']['finished_at'], docs[-1].id) if len(docs) == limit else None
    return [(doc.id, doc.to_dict()) for doc in docs], cursor


def conversation_ref(client, job):
    uid, cid = job.get('owner_id'), job.get('conversation_id')
    if not all(isinstance(part, str) and part and '/' not in part for part in (uid, cid)):
        raise ValueError('invalid seal identity')
    return client.collection('users').document(uid).collection('conversations').document(cid)


def is_debt(row):
    return (
        row.get('status') == 'completed'
        and row.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}
        and not row.get('record_audio_closed')
        and not row.get('record_audio_partial')
        and isinstance(row.get('finished_at'), datetime)
        and row['finished_at'].tzinfo is not None
    )


def ready(claim, now):
    if not isinstance(claim, dict) or not all(
        type(claim.get(field, 0)) in (int, float) and math.isfinite(claim.get(field, 0))
        for field in ('expires_at', 'retry_after')
    ):
        return False  # Malformed metadata remains for the sweeper; never pins a page.
    return claim.get('expires_at', 0) <= now and claim.get('retry_after', 0) <= now


def acquire(client, namespace, job_id, *, clock=time.time):
    """Recheck both documents before a walk. The token fences stale release."""
    ref = client.collection(f'{namespace}_jobs').document(job_id)
    token = uuid.uuid4().hex

    @firestore.transactional
    def commit(tx):
        now = clock()
        job = ref.get(transaction=tx).to_dict() or {}
        if job.get('state') != 'record_pending' or not ready(job.get('seal_claim') or {}, now):
            return None
        try:
            row_ref = conversation_ref(client, job)
        except ValueError:
            return None
        row = row_ref.get(transaction=tx).to_dict() or {}
        if not is_debt(row):
            return None
        claim = {'token': token, 'expires_at': now + CLAIM_SECONDS, 'retry_after': 0}
        tx.update(ref, {'seal_claim': claim})
        return {'job_id': job_id, 'token': token, 'path': row_ref.path, 'finished_at': row['finished_at']}

    return run_transactional(client, commit, transient=True)


def release(client, namespace, claim, *, clock=time.time):
    """Persist backoff even for failed/ambiguous attempts; leave proof to sweeper."""
    ref = client.collection(f'{namespace}_jobs').document(claim['job_id'])

    @firestore.transactional
    def commit(tx):
        job = ref.get(transaction=tx).to_dict() or {}
        current = job.get('seal_claim') or {}
        if not isinstance(current, dict) or current.get('token') != claim['token']:
            return False
        tx.update(ref, {'seal_claim': {**current, 'expires_at': 0, 'retry_after': clock() + BACKOFF_SECONDS}})
        return True

    return run_transactional(client, commit, transient=True)
