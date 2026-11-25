"""Per-owner v3 backfill run ledger. The run document holds counts, windows and outcomes only.

A live re-derive also keeps its undo priors (the touched rows' stored documents) in the run's
`priors` subcollection, at the same protection level as the rows they copy.

`users/{uid}/conversations_v3_backfill_runs/{run_id}` lives under the owner, so account deletion
erases it with the account. A run is a planned list of partitions (each a silence-bounded slice of
the window); the Cloud Tasks chain walks them in order and every step is recorded here, which makes
a run resumable, idempotent and the unit that undo targets.
"""

import json
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversation_payload import (
    read_conversation_payload,
    read_payload_children_for_delete,
    stage_conversation_payload,
)
from utils.conversation_payload import PAYLOAD_FIELD, ConversationProjectionTooLarge, InvalidConversationPayload
from utils.conversations.v3 import Conflict

COLLECTION = 'conversations_v3_backfill_runs'
# The run mode whose ledger keeps undo priors (utils.conversations.v3.backfill.LIVE_MODE).
LIVE_MODE = 'rederive-live'
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


def update_run(
    uid, run_id, *, status=None, partition=None, patch=None, expect=None, expected_drain_seq=None, firestore_client=None
):
    """Record one step. `partition` is (index, fields) merged into that partition's counts.

    `expect` refuses the write unless the run is in one of those states, so a stopped run (undoing,
    undone, blocked) cannot be advanced by a late task.
    `expected_drain_seq` also requires the partition to still be in notes at the observed sequence.
    Use it for every notes continuation and commit, even when the scan cursor did not move.
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
            current = partitions[index]
            if expected_drain_seq is not None and (
                current.get('status') != 'notes' or int(current.get('drain_seq') or 0) != expected_drain_seq
            ):
                return None
            partitions[index] = {**current, **fields}
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


# Live re-derive undo ledger: per touched row, its stored document before the run (or that the run
# created it) and the claims it held, under the run itself so account deletion purges it with the run.
PRIORS = 'conversations_v3_rederive_priors'
# Page inline priors. A copy of a chunked row gets its own bounded transaction.
PRIORS_PAGE_BYTES = 4 * 1024 * 1024
PRIORS_PAGE_DOCS = 100


def _priors(client, uid, run_id):
    return run_ref(client, uid, run_id).collection(PRIORS)


def _check_copy_account(tx, client, uid):
    deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
    if account_deletion_marker_blocks_access(
        marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('wipe_status')
    ):
        raise Conflict('account_deletion')


def save_priors(uid, run_id, entries, *, firestore_client=None):
    """Record the first prior before the commit that changes its row."""
    client = firestore_client or get_firestore_client()
    coll = _priors(client, uid, run_id)
    pages, page, size = [], [], 0
    for entry in entries:
        if PAYLOAD_FIELD in (entry.get('raw') or {}):
            if entry.get('source_revision') is None:
                raise Conflict('document_too_large')
            if page:
                pages.append(page)
                page, size = [], 0
            pages.append([entry])
            continue
        amount = len(json.dumps(entry, default=str).encode())
        if page and (size + amount > PRIORS_PAGE_BYTES or len(page) >= PRIORS_PAGE_DOCS):
            pages.append(page)
            page, size = [], 0
        page.append(entry)
        size += amount

    @firestore.transactional
    def write(tx, batch):
        # Fenced like the commit: no copy of a row is written once the owner's account deletion began.
        _check_copy_account(tx, client, uid)
        # A conversation the owner deleted since the load is never copied (the commit refuses it too).
        user = client.collection('users').document(uid)
        recorded = {entry['id']: coll.document(entry['id']).get(transaction=tx) for entry in batch}
        copies = {}
        for entry in batch:
            if user.collection('deleted_conversations').document(entry['id']).get(transaction=tx).exists:
                raise Conflict('target_deleted')
        # A copy is only ever at the row's current protection level (a migration since the load fails it).
        for entry in batch:
            if entry.get('raw') is None:
                continue
            current = user.collection('conversations').document(entry['id']).get(transaction=tx)
            row = (current.to_dict() or {}) if current.exists else {}
            if row.get('deleted'):
                raise Conflict('target_deleted')
            level = row.get('data_protection_level', 'standard') if current.exists else None
            if level is not None and level != entry['raw'].get('data_protection_level', 'standard'):
                raise Conflict('source_changed')
            if PAYLOAD_FIELD in entry['raw']:
                run = run_ref(client, uid, run_id).get(transaction=tx)
                if (
                    not current.exists
                    or current.update_time != entry['source_revision']
                    or row.get('is_locked')
                    or level == 'private'
                    or row.get(PAYLOAD_FIELD) != entry['raw'][PAYLOAD_FIELD]
                    or (run.to_dict() or {}).get('mode') != LIVE_MODE
                ):
                    raise Conflict('source_changed')
                if not recorded[entry['id']].exists:
                    try:
                        logical = read_conversation_payload(client, tx, current)
                    except (ConversationProjectionTooLarge, InvalidConversationPayload) as exc:
                        raise Conflict('undo_payload_unavailable') from exc
                    copies[entry['id']] = {
                        **entry,
                        'raw': logical,
                        'raw_protection_level': level,
                        'payload_fields': sorted(logical.keys() - row.keys()),
                    }
            elif PAYLOAD_FIELD in row:
                raise Conflict('source_changed')
        # A resumed attempt keeps the first copy: it holds the row and claim positions from before the run.
        for entry in batch:
            snapshot = recorded[entry['id']]
            if snapshot.exists:
                continue
            copy = {**copies.get(entry['id'], entry), 'recorded_at': datetime.now(timezone.utc)}
            copy.pop('source_revision', None)
            if 'payload_fields' in copy:
                try:
                    stage_conversation_payload(tx, snapshot, copy, spill_fields={'raw'}, allow_promotion=True)
                except ConversationProjectionTooLarge as exc:
                    raise Conflict('document_too_large') from exc
            else:
                tx.set(coll.document(entry['id']), copy)

    for batch in [*pages, page] if page else pages:
        write(client.transaction(), batch)
    return len(entries)


PRIORS_READ_PAGE = 200


def _write_cleanup_pages(client, operation, ids):
    def write(page):
        try:
            return operation(client.transaction(), page)
        except ConversationProjectionTooLarge:
            if len(page) == 1:
                raise
            middle = len(page) // 2
            return write(page[:middle]) + write(page[middle:])

    return sum(write(ids[start : start + PRIORS_PAGE_DOCS]) for start in range(0, len(ids), PRIORS_PAGE_DOCS))


def _prior_children_for_cleanup(tx, snapshots):
    children, size = [], 0
    for snapshot in snapshots:
        data = snapshot.to_dict() or {}
        size += len(json.dumps(data, default=str).encode())
        if PAYLOAD_FIELD in data:
            refs, cost = read_payload_children_for_delete(tx, snapshot.reference)
            children.extend(refs)
            size += cost
        if size > PRIORS_PAGE_BYTES or len(children) + len(snapshots) >= 500:
            raise ConversationProjectionTooLarge('prior cleanup exceeds the transaction budget')
    return children


def drop_priors(uid, run_id, conversation_ids, *, firestore_client=None):
    """Delete these conversations' priors and their owned chunks from one run."""
    client = firestore_client or get_firestore_client()
    coll = _priors(client, uid, run_id)
    ids = sorted(set(conversation_ids))

    @firestore.transactional
    def drop(tx, page):
        refs = [coll.document(cid) for cid in page]
        children = _prior_children_for_cleanup(tx, [ref.get(transaction=tx) for ref in refs])
        for ref in [*children, *refs]:
            tx.delete(ref)
        return len(refs)

    return _write_cleanup_pages(client, drop, ids)


def _live_run_ids(uid, *, firestore_client=None):
    """Every live re-derive run of an owner, in id-ordered pages (no cap on how many runs)."""
    client = firestore_client or get_firestore_client()
    found, cursor = [], None
    while True:
        query = (
            client.collection('users')
            .document(uid)
            .collection(COLLECTION)
            .where(filter=FieldFilter('mode', '==', LIVE_MODE))
            .order_by('__name__')
            .select(())
            .limit(PRIORS_READ_PAGE)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        found.extend(doc.id for doc in page)
        if len(page) < PRIORS_READ_PAGE:
            return found
        cursor = page[-1]


def purge_conversation_priors(uid, conversation_ids, reason, *, firestore_client=None, keep_level=None):
    """The owner deleted or re-protected these conversations: no undo copy of them is kept.

    Each existing prior becomes a stub with no content (``purged``: reason), in every live re-derive
    run of the owner, so that run's undo refuses as a whole rather than restoring around them. With
    ``keep_level``, copies already at that protection level, and copies of created rows (which hold no
    row), are kept.
    """
    client = firestore_client or get_firestore_client()
    ids = sorted(set(conversation_ids))
    runs = _live_run_ids(uid, firestore_client=client)

    @firestore.transactional
    def purge(tx, page, run_id):
        coll = _priors(client, uid, run_id)
        found = {}
        for cid in page:
            snapshot = coll.document(cid).get(transaction=tx)
            data = (snapshot.to_dict() or {}) if snapshot.exists else None
            if (
                data is None
                or data.get('purged') == reason
                or (keep_level and (data.get('purged') or data.get('created')))
            ):
                continue
            level = data.get('raw_protection_level', (data.get('raw') or {}).get('data_protection_level', 'standard'))
            if keep_level and level == keep_level:
                continue
            found[cid] = snapshot
        for ref in _prior_children_for_cleanup(tx, list(found.values())):
            tx.delete(ref)
        for cid in found:
            tx.set(coll.document(cid), {'id': cid, 'purged': reason, 'recorded_at': datetime.now(timezone.utc)})
        return len(found)

    purged = 0
    for run_id in runs:
        purged += _write_cleanup_pages(client, lambda tx, page: purge(tx, page, run_id), ids)
    return purged


def _read_prior(client, uid, snapshot):
    data = snapshot.to_dict() or {}
    if PAYLOAD_FIELD not in data:
        return data

    @firestore.transactional
    def load(tx):
        _check_copy_account(tx, client, uid)
        current = snapshot.reference.get(transaction=tx)
        try:
            return read_conversation_payload(client, tx, current)
        except (ConversationProjectionTooLarge, InvalidConversationPayload) as exc:
            raise Conflict('undo_payload_unavailable') from exc

    return load(client.transaction(read_only=True))


def get_priors(uid, run_id, conversation_ids, *, firestore_client=None):
    """The priors of these conversations in one run (by-id reads; missing ones are left out)."""
    client = firestore_client or get_firestore_client()
    coll = _priors(client, uid, run_id)
    found = []
    for cid in sorted(set(conversation_ids)):
        snapshot = coll.document(cid).get()
        if snapshot.exists and (data := _read_prior(client, uid, snapshot)) is not None:
            found.append({**data, 'id': cid})
    return found


def list_priors(uid, run_id, *, firestore_client=None):
    """Every prior of one run, in id-ordered pages."""
    client = firestore_client or get_firestore_client()
    found, cursor = [], None
    while True:
        query = _priors(client, uid, run_id).order_by('__name__').limit(PRIORS_READ_PAGE)
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        found.extend({**data, 'id': doc.id} for doc in page if (data := _read_prior(client, uid, doc)) is not None)
        if len(page) < PRIORS_READ_PAGE:
            return found
        cursor = page[-1]
