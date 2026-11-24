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


def _gone(uid: str, conversation_ids: Iterable[str], firestore_client: Any) -> set[str]:
    """Untombstoned ids whose conversation row is absent too (point reads; errors propagate)."""
    rows = _client(firestore_client).collection('users').document(uid).collection('conversations')
    return {cid for cid in sorted(set(conversation_ids)) if not rows.document(cid).get().exists}


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


def staging_sources(uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None) -> dict[str, list[str]]:
    """Each staging job these conversations reach, with every conversation that job fed.

    The durable audio obligation records this on its first run: ledger rows
    expire (45 days) while an obligation may stay held longer, and the record
    keeps both the prefix and its sibling set known after they are gone.
    """
    conversation_ids = [cid for cid in conversation_ids if cid]
    if not uid or not conversation_ids:
        return {}
    by_job = _job_rows(uid, conversation_ids, (), _client(firestore_client))
    return {job: sorted({cid for row in rows.values() for cid in row.conversation_ids}) for job, rows in by_job.items()}


def staging_plan(
    uid: str,
    conversation_ids: Iterable[str],
    *,
    recorded: Mapping[str, Iterable[str]] | None = None,
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
    authoritative alongside the ledger: a recorded job is always considered,
    its recorded siblings always count, and once its ledger rows have expired
    the upload is past any processing, so it is settled.
    """
    conversation_ids = [cid for cid in conversation_ids if cid]
    recorded = {job: list(ids) for job, ids in (recorded or {}).items() if _SAFE_ID.match(str(job))}
    if not uid or (not conversation_ids and not recorded):
        return StagingPlan()
    firestore_client = _client(firestore_client)
    by_job = _job_rows(uid, conversation_ids, recorded, firestore_client)
    if not by_job:
        return StagingPlan()
    fed_by_job = {
        job: {cid for row in rows.values() for cid in row.conversation_ids} | set(recorded.get(job, ()))
        for job, rows in by_job.items()
    }
    fed = set().union(*fed_by_job.values())
    deleted = set(conversation_ids) | _tombstoned(uid, fed - set(conversation_ids), firestore_client)
    deleted |= _gone(uid, fed - deleted, firestore_client)
    erasable, shared_live, in_flight = [], [], []
    for job in sorted(by_job):
        rows = by_job[job].values()
        if not fed_by_job[job] <= deleted:
            shared_live.append(job)
        elif any(row.status != SETTLED_STATUS for row in rows):
            in_flight.append(job)
        else:
            erasable.append(job)
    return StagingPlan(tuple(erasable), tuple(shared_live), tuple(in_flight))


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
