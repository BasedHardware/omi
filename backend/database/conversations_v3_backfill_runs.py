"""Per-owner v3 backfill run ledger. Counts, windows and outcomes only; never user content.

`users/{uid}/conversations_v3_backfill_runs/{run_id}` lives under the owner, so account deletion
erases it with the account. A run is a planned list of partitions (each a silence-bounded slice of
the window); the Cloud Tasks chain walks them in order and every step is recorded here, which makes
a run resumable, idempotent and the unit that undo targets.
"""

from datetime import datetime, timezone

from google.cloud import firestore

from database._client import get_firestore_client

COLLECTION = 'conversations_v3_backfill_runs'
# Terminal run states; the task route refuses work for a run in one of these or undoing.
FINISHED = frozenset({'committed', 'blocked', 'undone'})
STOPPED = FINISHED | {'undoing'}


def run_ref(client, uid, run_id):
    return client.collection('users').document(uid).collection(COLLECTION).document(run_id)


def create_run(uid, run_id, record, *, firestore_client=None):
    """Create a planned run once; an existing run id is never overwritten."""
    client = firestore_client or get_firestore_client()
    ref = run_ref(client, uid, run_id)

    @firestore.transactional
    def create(tx):
        if ref.get(transaction=tx).exists:
            return False
        now = datetime.now(timezone.utc)
        tx.set(ref, {**record, 'run_id': run_id, 'status': 'planned', 'created_at': now, 'updated_at': now})
        return True

    return create(client.transaction())


def get_run(uid, run_id, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    snapshot = run_ref(client, uid, run_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def list_runs(uid, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    return [
        doc.to_dict() or {}
        for doc in client.collection('users').document(uid).collection(COLLECTION).limit(200).stream()
    ]


def update_run(uid, run_id, *, status=None, partition=None, patch=None, expect=None, firestore_client=None):
    """Record one step. `partition` is (index, fields) merged into that partition's counts.

    `expect` refuses the write unless the run is in one of those states, so a stopped run (undoing,
    undone, blocked) cannot be advanced by a late task.
    """
    client = firestore_client or get_firestore_client()
    ref = run_ref(client, uid, run_id)

    @firestore.transactional
    def update(tx):
        snapshot = ref.get(transaction=tx)
        if not snapshot.exists:
            return None
        run = snapshot.to_dict() or {}
        if expect is not None and run.get('status') not in expect:
            return None
        changes = {**(patch or {}), 'updated_at': datetime.now(timezone.utc)}
        if status is not None:
            changes['status'] = status
        if partition is not None:
            index, fields = partition
            partitions = [dict(p) for p in run.get('partitions') or []]
            partitions[index] = {**partitions[index], **fields}
            changes['partitions'] = partitions
        tx.update(ref, changes)
        return {**run, **changes}

    return update(client.transaction())


# Start markers: a planned run's handoff from the operator to the sweep. The operator tier writes
# Firestore but cannot create Cloud Tasks, so the service's own sweep dispatches the first step. They
# live under users/{uid}, so account deletion's recursive purge removes them with the owner's data.
STARTS = 'conversations_v3_backfill_starts'


def _starts(client, uid):
    return client.collection('users').document(uid).collection(STARTS)


def mark_start(uid, run_id, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    _starts(client, uid).document(run_id).set({'run_id': run_id, 'created_at': datetime.now(timezone.utc)})


def pending_starts(limit, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    return [
        {'uid': doc.reference.parent.parent.id, 'run_id': doc.id}
        for doc in client.collection_group(STARTS).limit(limit).stream()
    ]


def clear_start(uid, run_id, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    _starts(client, uid).document(run_id).delete()
