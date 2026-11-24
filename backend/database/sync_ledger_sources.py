"""Which sync uploads fed a conversation, read from the owner's sync content ledger.

Sync staging (``syncing/{uid}/{job_id}/``) and batch-pipeline rows are keyed by
the upload, not by the conversation it became. The ledger row is the durable
link: ``job_id`` names the staging directory, ``batch_pipeline.segment_ids``
names the batch rows, and ``result``/``partial_result`` list the conversations
the upload created or updated. Conversation deletion uses it to find that
audio and transcript state; it never reads or writes audio itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from utils.sync import stage as sync_stage

CONVERSATION_FIELDS = tuple(
    f'{section}.{key}' for section in ('result', 'partial_result') for key in ('new_memories', 'updated_memories')
)
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
    )


def uploads_for_conversations(
    uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None
) -> list[SyncUpload]:
    """Every ledger row that lists any of ``conversation_ids``; read errors propagate."""
    ids = sorted({cid for cid in conversation_ids if isinstance(cid, str) and cid})
    if not uid or not ids:
        return []
    try:
        collection = sync_stage.collection_name('sync_content_ledger')
    except sync_stage.InvalidSyncStage:
        # Sync refuses to write a ledger row without a known stage, so none can exist.
        return []
    if firestore_client is None:
        from database._client import get_firestore_client

        firestore_client = get_firestore_client()
    ledger = firestore_client.collection('users').document(uid).collection(collection)
    found: dict[str, SyncUpload] = {}
    for field in CONVERSATION_FIELDS:
        for start in range(0, len(ids), _ANY_LIMIT):
            chunk = ids[start : start + _ANY_LIMIT]
            for snapshot in ledger.where(filter=FieldFilter(field, 'array_contains_any', chunk)).stream():
                found.setdefault(snapshot.id, _upload(snapshot))
    return [found[key] for key in sorted(found)]


def staging_job_ids(uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None) -> list[str]:
    """Staging directories of every upload that fed these conversations.

    Like the raw-sync originals, a staging directory shared with another
    conversation goes too: its audio must not outlive a deleted conversation.
    """
    uploads = uploads_for_conversations(uid, conversation_ids, firestore_client=firestore_client)
    return sorted({upload.job_id for upload in uploads if upload.job_id})


def owed_batch_segments(
    uid: str, conversation_ids: Iterable[str], *, firestore_client: Any = None
) -> dict[str, set[str]]:
    """Batch segment ids per namespace owed by these deleted conversations.

    An upload's segments are owed only once every conversation it fed carries
    a deletion tombstone, so a shared upload never erases a live sibling's
    pipeline rows. Rows still matched by conversation identity are unaffected.
    """
    if firestore_client is None:
        from database._client import get_firestore_client

        firestore_client = get_firestore_client()
    uploads = [
        upload
        for upload in uploads_for_conversations(uid, conversation_ids, firestore_client=firestore_client)
        if upload.batch_namespace and upload.batch_segment_ids
    ]
    if not uploads:
        return {}
    tombstones = firestore_client.collection('users').document(uid).collection('deleted_conversations')
    deleted = {
        cid
        for cid in sorted({cid for upload in uploads for cid in upload.conversation_ids})
        if tombstones.document(cid).get().exists
    }
    owed: dict[str, set[str]] = {}
    for upload in uploads:
        if upload.conversation_ids <= deleted:
            owed.setdefault(upload.batch_namespace, set()).update(upload.batch_segment_ids)
    return owed
