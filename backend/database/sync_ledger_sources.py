"""Which sync uploads fed a conversation, read from the owner's sync content ledger.

Sync staging (``syncing/{uid}/{job_id}/``) and batch-pipeline rows are keyed by
the upload, not by the conversation it became. The ledger row is the durable
link: ``job_id`` names the staging directory, ``batch_pipeline.segment_ids``
names the batch rows, and ``result``/``partial_result`` list the conversations
the upload created or updated. Conversation deletion uses it to find that
audio and transcript state; it never reads or writes audio itself.

Upload-keyed state is shared by every conversation the upload fed, so it is
owed to a deletion only once each of them carries a deletion tombstone: a
shared upload never loses bytes or rows a live sibling still needs. Staging is
also kept while the upload has not completed, because the job still reads it
and may yet feed another conversation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from utils.sync import stage as sync_stage

CONVERSATION_FIELDS = tuple(
    f'{section}.{key}' for section in ('result', 'partial_result') for key in ('new_memories', 'updated_memories')
)
# Only a completed upload has stopped reading its staging and feeding conversations.
SETTLED_STATUS = 'completed'
# Firestore caps array_contains_any at 30 values.
_ANY_LIMIT = 30
# Fed siblings classified per pass (at most two batched point reads each, plus redirect hops for an
# absorbed donor); the durable obligation records the deleted ones and continues on its next pass.
SIBLING_CHECKS_PER_PASS = 200
_SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


@dataclass(frozen=True)
class SyncUpload:
    content_id: str
    job_id: str | None
    conversation_ids: frozenset[str]
    batch_namespace: str | None
    batch_segment_ids: frozenset[str]
    status: str | None = None


@dataclass(frozen=True)
class StagingPlan:
    """What a deletion may do with each staging directory its conversations reach."""

    # Every conversation the upload job fed is tombstoned and the upload completed.
    erasable: tuple[str, ...] = ()
    # A conversation the upload fed is still live: it keeps the bytes; its own deletion erases them.
    shared_live: tuple[str, ...] = ()
    # Every fed conversation is tombstoned, but the upload has not completed: retry later.
    in_flight: tuple[str, ...] = ()
    # Some fed sibling was not classified this pass (over the per-pass cap): decided on a later pass.
    unchecked: tuple[str, ...] = ()
    # Jobs not seen settled (some row not completed, or recorded without rows and never seen completed).
    unsettled: tuple[str, ...] = ()
    # Fed siblings (outside the deletion itself) classified deleted, for the obligation to record.
    deleted_siblings: frozenset[str] = frozenset()


class StagingInFlight(RuntimeError):
    """Staging stays until its upload completes; the durable audio obligation retries."""

    def __init__(self, count: int):
        self.count = count
        super().__init__(f'sync staging retained until its upload completes: uploads={count}')


def _upload(snapshot: Any) -> SyncUpload:
    row = snapshot.to_dict() or {}
    conversations: set[str] = set()
    for section in ('result', 'partial_result'):
        value = row.get(section) or {}
        if isinstance(value, dict):
            for key in ('new_memories', 'updated_memories'):
                conversations.update(cid for cid in value.get(key) or [] if isinstance(cid, str) and cid)
    job_id = row.get('job_id')
    batch = row.get('batch_pipeline') or {}
    namespace = batch.get('namespace') if isinstance(batch, dict) else None
    segments = batch.get('segment_ids') if isinstance(batch, dict) else None
    return SyncUpload(
        content_id=snapshot.id,
        # The id becomes a storage prefix: anything but a plain token is ignored.
        job_id=job_id if isinstance(job_id, str) and _SAFE_ID.match(job_id) else None,
        conversation_ids=frozenset(conversations),
        batch_namespace=namespace if isinstance(namespace, str) and namespace else None,
        batch_segment_ids=frozenset(s for s in segments or [] if isinstance(s, str) and s),
        status=row.get('status') if isinstance(row.get('status'), str) else None,
    )


def _client(firestore_client: Any) -> Any:
    if firestore_client is not None:
        return firestore_client
    from database._client import get_firestore_client

    return get_firestore_client()


def _ledger(uid: str, firestore_client: Any) -> Any:
    """The owner's stage-scoped ledger collection, or None when no stage (so no ledger) exists."""
    try:
        collection = sync_stage.collection_name('sync_content_ledger')
    except sync_stage.InvalidSyncStage:
        # Sync refuses to write a ledger row without a known stage, so none can exist.
        return None
    return _client(firestore_client).collection('users').document(uid).collection(collection)


def _tombstoned(uid: str, conversation_ids: Iterable[str], firestore_client: Any) -> set[str]:
    """The ids among ``conversation_ids`` with a deletion tombstone (point reads; errors propagate)."""
    tombstones = _client(firestore_client).collection('users').document(uid).collection('deleted_conversations')
    return {cid for cid in sorted(set(conversation_ids)) if tombstones.document(cid).get().exists}


def _read_all(client: Any, collection: Any, ids: list[str]) -> dict[str, Any]:
    """Point-read ``ids`` from one collection (one batched ``get_all`` when the client has it)."""
    if not ids:
        return {}
    refs = [collection.document(cid) for cid in ids]
    get_all = getattr(client, 'get_all', None)
    if get_all is None:
        return {cid: ref.get() for cid, ref in zip(ids, refs)}
    found = {snapshot.id: snapshot for snapshot in get_all(refs)}
    return {cid: found[cid] for cid in ids if cid in found}


def _deleted_siblings(uid: str, ids: Iterable[str], deleting: set[str], firestore_client: Any) -> set[str]:
    """The ids among ``ids`` whose conversation is deleted; read errors propagate.

    Deleted means: tombstoned; no row (tombstones are written before rows are
    deleted, so that conversation is gone); a soft-deleted row
    (``conversations_db.is_soft_deleted``) that redirects nowhere; or an absorbed
    merge donor (``sync_merged_into``) whose redirect chain, resolved by the
    sync redirect resolver, ends deleted or at a conversation in ``deleting``.
    A donor absorbed into a live survivor is live: its upload is the survivor's audio.
    """
    from database.conversations import is_soft_deleted
    from database.sync_conversation_snapshot import resolve_snapshot

    ids = sorted(set(ids))
    if not ids:
        return set()
    client = _client(firestore_client)
    user = client.collection('users').document(uid)
    tombstones = _read_all(client, user.collection('deleted_conversations'), ids)
    deleted = {cid for cid, snapshot in tombstones.items() if snapshot.exists}
    rows = _read_all(client, user.collection('conversations'), [cid for cid in ids if cid not in deleted])
    for cid in ids:
        if cid in deleted:
            continue
        snapshot = rows.get(cid)
        row = (snapshot.to_dict() or {}) if snapshot is not None and snapshot.exists else None
        if row is None:
            deleted.add(cid)
        elif is_soft_deleted(row):
            successor = row.get('sync_merged_into')
            if not isinstance(successor, str) or not successor:
                deleted.add(cid)
                continue
            survivor = resolve_snapshot(uid, cid, client_factory=lambda: client)
            if survivor is None or survivor.conversation_id in deleting:
                deleted.add(cid)
    return deleted


def uploads_for_conversations(
    uid: str, conversation_ids: Iterable[str | None], *, firestore_client: Any = None
) -> list[SyncUpload]:
    """Every ledger row that lists any of ``conversation_ids``; read errors propagate."""
    ids = sorted({cid for cid in conversation_ids if cid})
    if not uid or not ids:
        return []
    ledger = _ledger(uid, firestore_client)
    if ledger is None:
        return []
    found: dict[str, SyncUpload] = {}
    for field in CONVERSATION_FIELDS:
        for start in range(0, len(ids), _ANY_LIMIT):
            chunk = ids[start : start + _ANY_LIMIT]
            for snapshot in ledger.where(filter=FieldFilter(field, 'array_contains_any', chunk)).stream():
                found.setdefault(snapshot.id, _upload(snapshot))
    return [found[key] for key in sorted(found)]


def _job_rows(
    uid: str, conversation_ids: list[str], extra_jobs: Iterable[str], firestore_client: Any
) -> dict[str, dict[str, SyncUpload]]:
    """Every ledger row of each upload job that fed these conversations (plus ``extra_jobs``), by job."""
    uploads = uploads_for_conversations(uid, conversation_ids, firestore_client=firestore_client)
    job_ids = sorted({upload.job_id for upload in uploads if upload.job_id} | set(extra_jobs))
    if not job_ids:
        return {}
    ledger = _ledger(uid, firestore_client)
    by_job: dict[str, dict[str, SyncUpload]] = {job: {} for job in job_ids}
    if ledger is None:
        return by_job
    for upload in uploads:
        if upload.job_id in by_job:
            by_job[upload.job_id][upload.content_id] = upload
    for job in job_ids:
        for snapshot in ledger.where(filter=FieldFilter('job_id', '==', job)).stream():
            row = _upload(snapshot)
            if row.job_id == job:
                by_job[job][row.content_id] = row
    return by_job


@dataclass(frozen=True)
class StagingSources:
    """What the durable audio obligation records from the ledger before it can expire."""

    # Staging job -> every conversation its ledger rows fed (merged across passes, never shrinks).
    fed: dict[str, list[str]]
    # Jobs whose ledger rows were all seen ``completed``: only these count as settled once the rows expire.
    settled: frozenset[str]


def staging_sources(
    uid: str,
    conversation_ids: Iterable[str],
    *,
    extra_jobs: Iterable[str] = (),
    firestore_client: Any = None,
) -> StagingSources:
    """Each staging job these conversations reach (plus ``extra_jobs``), its fed conversations and settled state.

    The durable audio obligation records this on its first run and again on
    every pass that left staging waiting: ledger rows expire (45 days) while an
    obligation may stay held longer, and the record keeps the prefix, its
    sibling set and whether it was ever seen settled known after they are gone.
    """
    conversation_ids = [cid for cid in conversation_ids if cid]
    extra = [job for job in extra_jobs if _SAFE_ID.match(str(job))]
    if not uid or (not conversation_ids and not extra):
        return StagingSources({}, frozenset())
    by_job = _job_rows(uid, conversation_ids, extra, _client(firestore_client))
    fed = {job: sorted({cid for row in rows.values() for cid in row.conversation_ids}) for job, rows in by_job.items()}
    settled = frozenset(
        job for job, rows in by_job.items() if rows and all(row.status == SETTLED_STATUS for row in rows.values())
    )
    return StagingSources(fed, settled)


def staging_plan(
    uid: str,
    conversation_ids: Iterable[str],
    *,
    recorded: Mapping[str, Iterable[str]] | None = None,
    settled: Iterable[str] = (),
    known_deleted: Iterable[str] = (),
    max_checks: int = SIBLING_CHECKS_PER_PASS,
    firestore_client: Any = None,
) -> StagingPlan:
    """Sort the staging directories of the uploads that fed these conversations.

    A directory is keyed by upload job, so every ledger row naming that job is
    read, not only the rows that list these conversations. It is erasable only
    when no conversation any of those rows fed is live and every row has
    completed. A fed conversation is not live when it is tombstoned, when it is
    one of ``conversation_ids`` (the deletion asking: the conversation and its
    merge donors, whose audio it owns even before their tombstones land), or
    when neither its row nor a tombstone exists (tombstones are written before
    rows are deleted, so that conversation is gone). Read errors propagate: the
    durable obligation retries them.

    ``recorded`` (job id -> fed conversation ids, from ``staging_sources``) is
    authoritative alongside the ledger: a recorded job is always considered and
    its recorded siblings always count. Once its ledger rows have expired, a
    recorded job is settled only if it is in ``settled`` (a pass saw every row
    completed); otherwise it stays in flight, held rather than erased, because
    a conversation it fed after the record could be unknown.

    A fed sibling is classified by ``_deleted_siblings`` (an absorbed merge
    donor counts as its survivor). At most ``max_checks`` siblings not already
    in ``known_deleted`` (deleted siblings an earlier pass recorded) are read
    per call; a job with an unread sibling and no live one is ``unchecked``.
    ``deleted_siblings`` returns every sibling known deleted, to record.
    """
    conversation_ids = [cid for cid in conversation_ids if cid]
    recorded = {job: list(ids) for job, ids in (recorded or {}).items() if _SAFE_ID.match(str(job))}
    if not uid or (not conversation_ids and not recorded):
        return StagingPlan()
    firestore_client = _client(firestore_client)
    by_job = _job_rows(uid, conversation_ids, recorded, firestore_client)
    if not by_job:
        return StagingPlan()
    settled_jobs = set(settled)
    fed_by_job = {
        job: {cid for row in rows.values() for cid in row.conversation_ids} | set(recorded.get(job, ()))
        for job, rows in by_job.items()
    }
    fed = set().union(*fed_by_job.values())
    deleting = set(conversation_ids)
    known = set(known_deleted) - deleting
    pending = sorted(fed - deleting - known)
    checked, unread = set(pending[: max(max_checks, 0)]), set(pending[max(max_checks, 0) :])
    found = _deleted_siblings(uid, checked, deleting, firestore_client)
    live = checked - found
    erasable, shared_live, in_flight, unchecked, unsettled = [], [], [], [], []
    for job in sorted(by_job):
        rows = by_job[job].values()
        if any(row.status != SETTLED_STATUS for row in rows) or (not rows and job not in settled_jobs):
            unsettled.append(job)
        if fed_by_job[job] & live:
            shared_live.append(job)
        elif fed_by_job[job] & unread:
            unchecked.append(job)
        elif job in unsettled:
            in_flight.append(job)
        else:
            erasable.append(job)
    return StagingPlan(
        tuple(erasable),
        tuple(shared_live),
        tuple(in_flight),
        tuple(unchecked),
        tuple(unsettled),
        frozenset((known | found) & fed),
    )


def staging_job_ids(uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None) -> list[str]:
    """Staging directories a deletion of these conversations may erase now (see ``staging_plan``)."""
    return list(staging_plan(uid, conversation_ids, firestore_client=firestore_client).erasable)


def owed_batch_segments(
    uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None
) -> dict[str, set[str]]:
    """Batch segment ids per namespace owed by these deleted conversations.

    An upload's segments are owed only once every conversation it fed carries
    a deletion tombstone, so a shared upload never erases a live sibling's
    pipeline rows. Rows still matched by conversation identity are unaffected.
    """
    firestore_client = _client(firestore_client)
    uploads = [
        upload
        for upload in uploads_for_conversations(uid, conversation_ids, firestore_client=firestore_client)
        if upload.batch_namespace and upload.batch_segment_ids
    ]
    if not uploads:
        return {}
    deleted = _tombstoned(uid, {cid for upload in uploads for cid in upload.conversation_ids}, firestore_client)
    owed: dict[str, set[str]] = {}
    for upload in uploads:
        if upload.batch_namespace and upload.conversation_ids <= deleted:
            owed.setdefault(upload.batch_namespace, set()).update(upload.batch_segment_ids)
    return owed
