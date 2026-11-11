"""Firestore folder adapter. Module functions are the typed application surface."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.document_ids import system_folder_doc_id
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.ports.base import MutationConflict, Page, RevisionConflict
from database.ports.folders import (
    CATEGORY_TO_FOLDER_MAPPING as CATEGORY_TO_FOLDER_MAPPING,
    SYSTEM_FOLDERS,
    FolderCreate,
    FolderEntity,
    FolderUpdate,
    resolve_category_folder_id as resolve_category_folder_id,
)

logger = logging.getLogger(__name__)


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _order_key(value: Any) -> tuple:
    # Query order remains Firestore's order; this also supports lenient scalar
    # legacy order fields when applying the byte-order id tie break.
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, datetime):
        return (3, value.timestamp())
    if isinstance(value, str):
        return (4, value.encode())
    return (5, repr(value))


def port_mutation_digest(entity: str, operation: str, data: Any) -> str:
    return hashlib.sha256(json.dumps([entity, operation, data], sort_keys=True, default=str).encode()).hexdigest()


def read_port_mutation(owner: Any, transaction: Any, mutation_id: str | None, digest: str) -> dict[str, Any] | None:
    if mutation_id is None:
        return None
    snapshot = owner.collection('port_mutations').document(mutation_id).get(transaction=transaction)
    if not snapshot.exists:
        return None
    receipt = _typed_doc(snapshot)
    if receipt.get('result_digest') != digest:
        raise MutationConflict(mutation_id)
    return receipt


def write_port_mutation(
    owner: Any, transaction: Any, mutation_id: str | None, digest: str, entity: str, entity_id: str, **extra: Any
) -> None:
    if mutation_id is not None:
        transaction.set(
            owner.collection('port_mutations').document(mutation_id),
            {
                'entity': entity,
                'entity_id': entity_id,
                'result_digest': digest,
                'created_at': datetime.now(timezone.utc),
                **extra,
            },
        )


def check_port_revision(space_id: str, entity: str, entity_id: str, data: dict[str, Any], expected: int | None) -> int:
    revision = data.get('revision', 1)
    revision = revision if type(revision) is int else 1
    if expected is not None and expected != revision:
        raise RevisionConflict(space_id, entity, entity_id, revision)
    return revision


class FirestoreFolders:
    """Legacy documents read as revision 1 until stamped.

    Blind metadata writes increment by 2: Firestore initializes an absent numeric
    field from zero, so Increment(1) would reuse the legacy token 1. Revisions
    are opaque monotonic CAS tokens, not an operation count. Read/CAS writes
    increment by 1 once a stored revision exists.
    """

    def __init__(self, space_id: str, *, firestore_client: Any = None, transaction: Any = None):
        self.space_id = space_id
        self.client = firestore_client if firestore_client is not None else get_firestore_client()
        self.transaction = transaction
        self.owner = self.client.collection('users').document(space_id)

    @property
    def ref(self) -> Any:
        return self.owner.collection('folders')

    def _read(self, ref: Any) -> Any:
        return ref.get(transaction=self.transaction) if self.transaction is not None else ref.get()

    def _stream(self, query: Any) -> Iterable[Any]:
        return query.stream(transaction=self.transaction) if self.transaction is not None else query.stream()

    def _write(self, operation: str, ref: Any, *args: Any) -> None:
        if self.transaction is None:
            getattr(ref, operation)(*args)
        else:
            getattr(self.transaction, operation)(ref, *args)

    def _atomic(self, method: str, *args: Any, **kwargs: Any) -> Any:
        @firestore.transactional
        def apply(transaction):
            repo = FirestoreFolders(self.space_id, firestore_client=self.client, transaction=transaction)
            return getattr(repo, method)(*args, **kwargs)

        return run_transactional(self.client, apply)

    @staticmethod
    def _entity(data: dict[str, Any], entity_id: str) -> FolderEntity:
        # Storage is lenient, including malformed known fields. Preserve the original
        # field set so wire validators can still reject missing required fields.
        values: dict[str, Any] = {**data, 'id': entity_id}
        return FolderEntity.model_construct(**values)

    def list(self, *, limit: int | None = None, cursor: str | None = None) -> Page[FolderEntity]:
        if limit is not None and limit <= 0:
            raise ValueError('limit must be positive')
        # Keep the serving query shape; keyset filtering is over the existing ordered
        # result, so the cursor survives deletion without adding an index requirement.
        rows = [self._entity(_typed_doc(doc), doc.id) for doc in self._stream(self.ref.order_by('order'))]
        rows.sort(key=lambda row: (_order_key(row.order), row.id.encode()))
        if cursor is not None:
            order, entity_id = json.loads(base64.urlsafe_b64decode(cursor))
            rows = [
                row
                for row in rows
                if (_order_key(row.order), row.id.encode()) > (_order_key(order), entity_id.encode())
            ]
        items = rows if limit is None else rows[:limit]
        next_cursor = None
        if items and len(items) < len(rows):
            next_cursor = base64.urlsafe_b64encode(json.dumps([items[-1].order, items[-1].id]).encode()).decode()
        return Page(items, next_cursor)

    def get(self, folder_id: str) -> FolderEntity | None:
        doc = self._read(self.ref.document(folder_id))
        return self._entity(_typed_doc(doc), folder_id) if getattr(doc, 'exists', False) else None

    def create(self, draft: FolderCreate, *, mutation_id: str | None = None) -> FolderEntity:
        if mutation_id is not None and self.transaction is None:
            return self._atomic('create', draft, mutation_id=mutation_id)
        digest = port_mutation_digest('folders', 'create', draft.model_dump())
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if receipt is not None:
            current = self.get(receipt['entity_id'])
            if current is None:
                assert mutation_id is not None
                raise MutationConflict(mutation_id)
            return current
        existing = list(self._stream(self.ref.order_by('order', direction=firestore.Query.DESCENDING).limit(1)))
        raw_order = _typed_doc(existing[0]).get('order') if existing else 0
        max_order = raw_order if type(raw_order) is int else 0
        folder_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        row = FolderEntity(
            id=folder_id,
            name=draft.name,
            description=draft.description,
            color=draft.color or '#6B7280',
            icon=draft.icon or '📁',
            created_at=now,
            updated_at=now,
            order=max_order + 1,
        )
        self._write('set', self.ref.document(folder_id), row.model_dump())
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', folder_id)
        return row

    def update(
        self,
        folder_id: str,
        patch: FolderUpdate,
        *,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> FolderEntity | None:
        if self.transaction is None and (expected_revision is not None or mutation_id is not None):
            return self._atomic(
                'update', folder_id, patch, expected_revision=expected_revision, mutation_id=mutation_id
            )
        digest = port_mutation_digest('folders', 'update', [folder_id, patch.model_dump(exclude_unset=True)])
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        current = self.get(folder_id)
        if current is None or receipt is not None:
            return current
        revision = check_port_revision(self.space_id, 'folders', folder_id, current.model_dump(), expected_revision)
        data = {
            k: v
            for k, v in patch.model_dump(exclude_unset=True).items()
            if v is not None or k not in ('name', 'color', 'icon', 'order')
        }
        if data:
            data['updated_at'] = datetime.now(timezone.utc)
            try:
                self._write(
                    'update',
                    self.ref.document(folder_id),
                    {**data, 'revision': firestore.Increment(1 if 'revision' in current.model_fields_set else 2)},
                )
            except NotFound:
                return None
            current = current.model_copy(update={**data, 'revision': revision + 1})
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', folder_id)
        return current

    def get_by_category_mapping(self, category_mapping: str) -> FolderEntity | None:
        return next((f for f in self.list().items if f.category_mapping == category_mapping), None)

    def delete(
        self,
        folder_id: str,
        *,
        move_to_folder_id: str | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> bool:
        if self.transaction is None and (mutation_id is not None or expected_revision is not None):
            return self._atomic(
                'delete',
                folder_id,
                move_to_folder_id=move_to_folder_id,
                expected_revision=expected_revision,
                mutation_id=mutation_id,
            )
        digest = port_mutation_digest('folders', 'delete', [folder_id, move_to_folder_id])
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if receipt is not None:
            return True
        if expected_revision is not None:
            current = self.get(folder_id)
            if current is None:
                return False
            check_port_revision(self.space_id, 'folders', folder_id, current.model_dump(), expected_revision)
        target_folder_id = move_to_folder_id
        if not target_folder_id:
            default = next((f for f in self.list().items if f.is_default and f.id != folder_id), None)
            target_folder_id = default.id if default else None
        query = self.owner.collection('conversations').where(filter=FieldFilter('folder_id', '==', folder_id))
        if self.transaction is not None:
            snapshots = list(self._stream(query))
            target = self.get(target_folder_id) if target_folder_id else None
            target_count = self._count(target_folder_id) if target_folder_id else 0
            for snapshot in snapshots:
                self._write('update', snapshot.reference, {'folder_id': target_folder_id})
            if target:
                self._write(
                    'update',
                    self.ref.document(target_folder_id),
                    {
                        'conversation_count': target_count
                        + sum(_typed_doc(s).get('discarded') is False for s in snapshots),
                        'revision': firestore.Increment(2),
                    },
                )
        else:
            references = []
            for doc in query.select([]).stream():
                references.append(doc.reference)
                if len(references) >= 450:
                    _rehome_folder_conversations(self.client, references, folder_id, target_folder_id)
                    references = []
            if references:
                _rehome_folder_conversations(self.client, references, folder_id, target_folder_id)
            if target_folder_id:
                self.refresh_conversation_count(target_folder_id)
        self._write('delete', self.ref.document(folder_id))
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', folder_id)
        return True

    def reorder(self, folder_ids: list[str], *, mutation_id: str | None = None) -> bool:
        if mutation_id is not None and self.transaction is None:
            return self._atomic('reorder', folder_ids, mutation_id=mutation_id)
        digest = port_mutation_digest('folders', 'reorder', folder_ids)
        if read_port_mutation(self.owner, self.transaction, mutation_id, digest) is not None:
            return True
        writer = self.transaction if self.transaction is not None else self.client.batch()
        for i, folder_id in enumerate(folder_ids):
            writer.update(
                self.ref.document(folder_id),
                {
                    'order': i,
                    'updated_at': datetime.now(timezone.utc),
                    'revision': firestore.Increment(2),
                },
            )
        if self.transaction is None:
            writer.commit()
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', '')
        return True

    def initialize_system(self, *, mutation_id: str | None = None) -> list[FolderEntity]:
        if mutation_id is not None and self.transaction is None:
            return self._atomic('initialize_system', mutation_id=mutation_id)
        digest = port_mutation_digest('folders', 'initialize_system', None)
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if list(self._stream(self.ref.limit(1))):
            rows = self.list().items
            if receipt is None:
                write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', '')
            return rows
        if receipt is not None:
            return []
        now = datetime.now(timezone.utc)
        rows = []
        for i, config in enumerate(SYSTEM_FOLDERS):
            row = FolderEntity(
                id=system_folder_doc_id(self.space_id, config['category_mapping']),
                **config,
                created_at=now,
                updated_at=now,
                order=i,
                is_system=True,
                is_default=config['category_mapping'] == 'other',
            )
            self._write('set', self.ref.document(row.id), row.model_dump())
            rows.append(row)
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', '')
        return rows

    def conversations_in_folder(
        self, folder_id: str, *, limit: int = 100, offset: int = 0, include_discarded: bool = False
    ) -> list[dict]:
        query = self.owner.collection('conversations').where(filter=FieldFilter('folder_id', '==', folder_id))
        if not include_discarded:
            query = query.where(filter=FieldFilter('discarded', '==', False))
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING).offset(offset).limit(limit)
        rows = []
        for doc in self._stream(query):
            data = _typed_doc(doc)
            if not data.get('deleted'):
                rows.append({**data, 'id': doc.id})
        return rows

    def _count(self, folder_id: str) -> int:
        query = (
            self.owner.collection('conversations')
            .where(filter=FieldFilter('folder_id', '==', folder_id))
            .where(filter=FieldFilter('discarded', '==', False))
        )
        result = (
            query.count().get(transaction=self.transaction) if self.transaction is not None else query.count().get()
        )
        return int(result[0][0].value or 0)

    def refresh_conversation_count(
        self, folder_id: str, *, expected_revision: int | None = None, mutation_id: str | None = None
    ) -> int:
        if self.transaction is None and (expected_revision is not None or mutation_id is not None):
            return self._atomic(
                'refresh_conversation_count', folder_id, expected_revision=expected_revision, mutation_id=mutation_id
            )
        digest = port_mutation_digest('folders', 'refresh_count', folder_id)
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if receipt is not None:
            return receipt['count']
        current = self.get(folder_id) if self.transaction is not None or expected_revision is not None else None
        if current is not None:
            check_port_revision(self.space_id, 'folders', folder_id, current.model_dump(), expected_revision)
        count = self._count(folder_id)
        if self.transaction is not None and current is None:
            write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', folder_id, count=count)
            return count
        try:
            self._write(
                'update',
                self.ref.document(folder_id),
                {
                    'conversation_count': count,
                    'revision': firestore.Increment(2),
                },
            )
        except NotFound:
            logger.warning(f'folder {folder_id} no longer exists; skipping conversation_count refresh')
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', folder_id, count=count)
        return count

    def move_conversation(self, conversation_id: str, folder_id: str | None, *, mutation_id: str | None = None) -> bool:
        if self.transaction is not None or mutation_id is not None:
            if self.transaction is None:
                return self._atomic('move_conversation', conversation_id, folder_id, mutation_id=mutation_id)
            return bool(self._move_many([conversation_id], folder_id, mutation_id, 'move'))
        ref = self.owner.collection('conversations').document(conversation_id)
        doc = ref.get()
        if not getattr(doc, 'exists', False):
            return False
        old = _typed_doc(doc).get('folder_id')
        try:
            ref.update({'folder_id': folder_id, 'folder_user_set': True})
        except NotFound:
            return False
        if old:
            self.refresh_conversation_count(str(old))
        if folder_id:
            self.refresh_conversation_count(folder_id)
        return True

    def bulk_move_conversations(
        self, conversation_ids: list[str], folder_id: str, *, mutation_id: str | None = None
    ) -> int:
        if self.transaction is not None or mutation_id is not None:
            if self.transaction is None:
                return self._atomic('bulk_move_conversations', conversation_ids, folder_id, mutation_id=mutation_id)
            return self._move_many(conversation_ids, folder_id, mutation_id, 'bulk_move')
        if not conversation_ids:
            return 0
        ref = self.owner.collection('conversations')
        docs = self.client.get_all([ref.document(cid) for cid in conversation_ids])
        affected: Set[str] = set()
        batch = self.client.batch()
        moved = count = 0
        for doc in docs:
            if doc is None or not getattr(doc, 'exists', False):
                continue
            old = _typed_doc(doc).get('folder_id')
            if old:
                affected.add(str(old))
            batch.update(doc.reference, {'folder_id': folder_id, 'folder_user_set': True})
            moved += 1
            count += 1
            if count >= 450:
                batch.commit()
                batch = self.client.batch()
                count = 0
        if count:
            batch.commit()
        affected.add(folder_id)
        for fid in affected:
            self.refresh_conversation_count(fid)
        return moved

    def _move_many(self, ids: list[str], target: str | None, mutation_id: str | None, operation: str) -> int:
        digest = port_mutation_digest('folders', operation, [ids, target])
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if receipt is not None:
            return receipt['count']
        docs = [self._read(self.owner.collection('conversations').document(cid)) for cid in dict.fromkeys(ids)]
        docs = [doc for doc in docs if doc.exists]
        deltas: dict[str, int] = {}
        for doc in docs:
            data = _typed_doc(doc)
            if data.get('discarded') is False:
                old = data.get('folder_id')
                if old:
                    deltas[old] = deltas.get(old, 0) - 1
                if target:
                    deltas[target] = deltas.get(target, 0) + 1
        counts = {fid: self._count(fid) + delta for fid, delta in deltas.items() if self.get(fid) is not None}
        for doc in docs:
            self._write('update', doc.reference, {'folder_id': target, 'folder_user_set': True})
        for fid, count in counts.items():
            self._write(
                'update', self.ref.document(fid), {'conversation_count': count, 'revision': firestore.Increment(2)}
            )
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'folders', target or '', count=len(docs))
        return len(docs)


def _rehome_folder_conversations(
    client: Any, references: List[Any], source_folder_id: str, target_folder_id: Optional[str]
) -> None:
    """Keep the established 450-document membership fence and retry choreography."""

    @firestore.transactional
    def rehome(write_transaction):
        snapshots = list(client.get_all(references, field_paths=['folder_id'], transaction=write_transaction))
        for snapshot in snapshots:
            if snapshot.exists and _typed_doc(snapshot).get('folder_id') == source_folder_id:
                write_transaction.update(snapshot.reference, {'folder_id': target_folder_id})

    run_with_transaction_contention_retry(client.transaction, rehome, operation_name='folder_delete_rehome')


def get_folders(uid: str, *, firestore_client: Any = None) -> list[FolderEntity]:
    return FirestoreFolders(uid, firestore_client=firestore_client).list().items


def get_folder(uid: str, folder_id: str, *, firestore_client: Any = None) -> FolderEntity | None:
    return FirestoreFolders(uid, firestore_client=firestore_client).get(folder_id)


def create_folder(
    uid: str,
    name: str,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    *,
    firestore_client: Any = None,
) -> FolderEntity:
    return FirestoreFolders(uid, firestore_client=firestore_client).create(
        FolderCreate(name=name, description=description, color=color, icon=icon)
    )


def update_folder(
    uid: str, folder_id: str, update_data: FolderUpdate, *, firestore_client: Any = None
) -> FolderEntity | None:
    return FirestoreFolders(uid, firestore_client=firestore_client).update(folder_id, update_data)


def delete_folder(
    uid: str, folder_id: str, move_to_folder_id: str | None = None, *, firestore_client: Any = None
) -> bool:
    return FirestoreFolders(uid, firestore_client=firestore_client).delete(
        folder_id, move_to_folder_id=move_to_folder_id
    )


def reorder_folders(uid: str, folder_ids: list[str], *, firestore_client: Any = None) -> bool:
    return FirestoreFolders(uid, firestore_client=firestore_client).reorder(folder_ids)


def initialize_system_folders(uid: str, *, firestore_client: Any = None) -> list[FolderEntity]:
    return FirestoreFolders(uid, firestore_client=firestore_client).initialize_system()


def get_conversations_in_folder(
    uid: str,
    folder_id: str,
    limit: int = 100,
    offset: int = 0,
    include_discarded: bool = False,
    *,
    firestore_client: Any = None,
) -> list[dict]:
    return FirestoreFolders(uid, firestore_client=firestore_client).conversations_in_folder(
        folder_id, limit=limit, offset=offset, include_discarded=include_discarded
    )


def move_conversation_to_folder(
    uid: str, conversation_id: str, folder_id: str | None, *, firestore_client: Any = None
) -> bool:
    return FirestoreFolders(uid, firestore_client=firestore_client).move_conversation(conversation_id, folder_id)


def bulk_move_conversations_to_folder(
    uid: str, conversation_ids: list[str], folder_id: str, *, firestore_client: Any = None
) -> int:
    return FirestoreFolders(uid, firestore_client=firestore_client).bulk_move_conversations(conversation_ids, folder_id)


def update_folder_conversation_count(uid: str, folder_id: str, *, firestore_client: Any = None) -> int:
    return FirestoreFolders(uid, firestore_client=firestore_client).refresh_conversation_count(folder_id)


def get_folder_by_category_mapping(
    uid: str, category_mapping: str, *, firestore_client: Any = None
) -> FolderEntity | None:
    return FirestoreFolders(uid, firestore_client=firestore_client).get_by_category_mapping(category_mapping)
