import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypedDict, cast

from config.memory_confidence import SOURCE_SIGNAL_CAPTURE_PRIORS
from database import memory_ledger
from database import short_term_memories as short_term_db
from database.store import Filter, get_document_store
from models.memories import confidence_fields_for_evidence, merge_evidence_sets
from utils import encryption
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read
import logging

logger = logging.getLogger(__name__)

memories_collection = 'memories'
users_collection = 'users'


class MemoryDoc(TypedDict, total=False):
    """Firestore `users/{uid}/memories/{memory_id}` document contract.

    All fields are optional at the document level (``total=False``) because legacy
    memories predate several columns and Firestore reads must tolerate their
    absence. Values typed ``Any`` are SDK-returned (datetime / nested dict / list)
    and are narrowed by callers via ``isinstance`` checks.
    """

    id: str
    uid: str
    content: Any  # str (plaintext) or encrypted str (enhanced protection)
    title: str
    headline: Optional[str]
    arguments: Dict[str, Any]
    structured: Dict[str, Any]
    category: str
    visibility: str
    created_at: Any  # firestore DATETIME
    updated_at: Any  # firestore DATETIME
    invalid_at: Any  # firestore DATETIME
    scoring: float
    user_review: Optional[bool]
    reviewed: bool
    edited: bool
    is_locked: bool
    kg_extracted: bool
    app_id: Optional[str]
    memory_id: Optional[str]  # origin conversation id (legacy memories: == id)
    topic: str
    subtopics: List[str]
    plugin_id: Optional[str]
    language: Optional[str]
    subject_attribution: str
    capture_confidence: Optional[float]
    data_protection_level: str
    superseded_by: Optional[str]
    redaction_status: str
    evidence: List[Dict[str, Any]]
    to_sha256: Optional[str]


# Signature expected by ``prepare_for_read`` for the post-read decrypt hook. The
# concrete helper accepts/returns Optional[Dict] for direct call sites that may
# pass ``None``; at decorator sites we cast to this narrower contract.
_DecryptFunc = Callable[[Dict[str, Any], str], Dict[str, Any]]


def _typed_doc(doc: Any) -> Dict[str, Any]:
    """Narrow a Firestore snapshot to a :class:`MemoryDoc`-shaped ``dict``.

    Firestore ships no type stubs; ``doc.to_dict()`` is untyped. We ``isinstance``
    the raw payload to a ``dict`` and cast it so every downstream ``.get(...)`` is
    statically keyed. Callers that want typed key access can ``cast(MemoryDoc, …)``
    on the result; the helper returns ``Dict[str, Any]`` so it flows freely into
    the module's ``Dict[str, Any]``-typed APIs (a ``TypedDict`` is invariant with
    ``Dict[str, Any]`` in pyright and cannot be assigned directly).
    """
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def _store():
    return get_document_store()


def _memories_path(uid: str) -> str:
    return f'{users_collection}/{uid}/{memories_collection}'


def _memory_path(uid: str, memory_id: str) -> str:
    return f'{users_collection}/{uid}/{memories_collection}/{memory_id}'


def _update_memory_if_exists(
    uid: str,
    memory_id: str,
    update_payload: Dict[str, Any],
    operation: str,
) -> bool:
    store = _store()
    path = _memory_path(uid, memory_id)
    if not store.exists(path):
        logger.warning('Skipping stale memory %s update: memory document no longer exists uid=%s', operation, uid)
        return False
    store.update(path, update_payload)
    return True


def get_memory_ids(uid: str) -> List[str]:
    """Return all memory document IDs for a user without decrypting any fields (IDs-only projection).

    Used for bulk operations like account deletion (e.g. to purge derived Pinecone vectors)."""
    return _store().list_ids(_memories_path(uid))


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************


def _encrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(memory_data)

    if 'content' in data and isinstance(data['content'], str):
        data['content'] = encryption.encrypt(data['content'], uid)
    if 'evidence' in data and isinstance(data['evidence'], list):
        data['evidence'] = encryption.encrypt(json.dumps(data['evidence'], default=str), uid)
    return data


def _decrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(memory_data)

    if 'content' in data and isinstance(data['content'], str):
        try:
            data['content'] = encryption.decrypt(data['content'], uid)
        except Exception:
            pass
    if 'evidence' in data and isinstance(data['evidence'], str):
        try:
            decrypted = encryption.decrypt(data['evidence'], uid)
            data['evidence'] = json.loads(decrypted)
        except Exception:
            pass
    return data


def _prepare_data_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    if level == 'enhanced':
        return _encrypt_memory_data(data, uid)
    return data


def _prepare_memory_for_read(memory_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    if not memory_data:
        return None

    level = memory_data.get('data_protection_level')
    if level == 'enhanced':
        return _decrypt_memory_data(memory_data, uid)

    return memory_data


# *****************************
# ********** CRUD *************
# *****************************


@prepare_for_read(decrypt_func=cast(_DecryptFunc, _prepare_memory_for_read))
def get_memories(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    categories: List[str] = [],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_invalidated: bool = False,
    sort: str = 'scoring_desc',
) -> List[Dict[str, Any]]:
    logger.info(f'get_memories db {uid} {limit} {offset} {categories} {start_date} {end_date} {sort}')
    filters: List[Filter] = []
    if categories:
        filters.append(('category', 'in', categories))
    if start_date:
        filters.append(('created_at', '>=', start_date))
    if end_date:
        filters.append(('created_at', '<=', end_date))

    # Keep the query on the existing indexed order (scoring desc, created_at desc). MCP-specific
    # sort modes are applied after batch collection to avoid requiring extra composite indexes for
    # category-filtered reads.
    # TODO: put user review to the query
    memories: List[Dict[str, Any]] = [
        _typed_doc(doc)
        for doc in _store().query(
            _memories_path(uid),
            filters=filters,
            order_by=[('scoring', 'desc'), ('created_at', 'desc')],
            limit=limit,
            offset=offset,
        )
    ]
    logger.info(f"get_memories {len(memories)}")
    # Exclude user-rejected memories, and (by default) superseded/retracted ones.
    # invalid_at is filtered in Python: old docs lack the field (-> None -> active),
    # which a Firestore `== None` filter would wrongly drop.
    result: List[Dict[str, Any]] = [
        memory
        for memory in memories
        if memory.get('user_review') is not False and (include_invalidated or memory.get('invalid_at') is None)
    ]
    return result


@prepare_for_read(decrypt_func=cast(_DecryptFunc, _prepare_memory_for_read))
def get_user_public_memories(uid: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    logger.info(f'get_public_memories {limit} {offset}')

    memories: List[Dict[str, Any]] = [
        _typed_doc(doc)
        for doc in _store().query(
            _memories_path(uid),
            order_by=[('scoring', 'desc'), ('created_at', 'desc')],
            limit=limit,
            offset=offset,
        )
    ]

    # Consider visibility as 'public' if it's missing
    public_memories: List[Dict[str, Any]] = [
        memory for memory in memories if memory.get('visibility', 'public') == 'public'
    ]

    return public_memories


@prepare_for_read(decrypt_func=cast(_DecryptFunc, _prepare_memory_for_read))
def get_non_filtered_memories(uid: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    logger.info(f'get_non_filtered_memories {uid} {limit} {offset}')
    return [
        _typed_doc(doc)
        for doc in _store().query(
            _memories_path(uid), order_by='created_at', direction='desc', limit=limit, offset=offset
        )
    ]


@set_data_protection_level(data_arg_name='data')
@prepare_for_write(data_arg_name='data', prepare_func=_prepare_data_for_write)
def create_memory(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    path = _memory_path(uid, data['id'])

    def build_commit(tx: Any) -> Dict[str, Any]:
        snapshot = tx.get(path)
        existing_data: Optional[Dict[str, Any]] = _typed_doc(snapshot) if snapshot.exists else None
        merged_data = _merge_memory_for_write(uid, existing_data, data)

        def write_projection(write_tx: Any) -> None:
            write_tx.set(path, merged_data)

        return {'mutations': [memory_ledger.add_fact(merged_data)], 'projection_writer': write_projection}

    return memory_ledger.append_commit_with_builder(uid, None, build_commit, use_current_head=True)


@set_data_protection_level(data_arg_name='data')
@prepare_for_write(data_arg_name='data', prepare_func=_prepare_data_for_write)
def save_memories(uid: str, data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not data:
        return

    coalesced_data = _coalesce_memory_writes(uid, data)
    paths_and_data: List[tuple[str, Dict[str, Any]]] = [
        (_memory_path(uid, memory['id']), memory) for memory in coalesced_data
    ]

    def build_commit(tx: Any) -> Dict[str, Any]:
        snapshots: List[Any] = [tx.get(path) for path, _ in paths_and_data]

        merged_data: List[tuple[str, Dict[str, Any]]] = []
        for (path, memory), snapshot in zip(paths_and_data, snapshots):
            existing_data: Optional[Dict[str, Any]] = _typed_doc(snapshot) if snapshot.exists else None
            merged_data.append((path, _merge_memory_for_write(uid, existing_data, memory)))

        def write_projection(write_tx: Any) -> None:
            for path, memory in merged_data:
                write_tx.set(path, memory)

        return {
            'mutations': [memory_ledger.add_fact(memory) for _, memory in merged_data],
            'projection_writer': write_projection,
        }

    return memory_ledger.append_commit_with_builder(uid, None, build_commit, use_current_head=True)


def _merge_memory_for_write(
    uid: str, existing_data: Optional[Dict[str, Any]], incoming_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge additive provenance when a deterministic memory id already exists."""
    if not existing_data:
        return incoming_data

    incoming_plain = _prepare_memory_for_read(incoming_data, uid) or incoming_data
    existing_plain = _prepare_memory_for_read(existing_data, uid) or existing_data
    existing_evidence: List[Any] = existing_plain.get('evidence') or []
    incoming_evidence: List[Any] = incoming_plain.get('evidence') or []
    if not incoming_evidence:
        return incoming_data

    merged_plain: Dict[str, Any] = {**existing_plain, **incoming_plain}
    merged_plain['created_at'] = existing_plain.get('created_at', incoming_plain.get('created_at'))
    merged_plain['evidence'] = merge_evidence_sets(existing_evidence, incoming_evidence)
    merged_plain.update(
        confidence_fields_for_evidence(
            merged_plain['evidence'],
            merged_plain.get('subject_attribution', 'unknown'),
            existing_capture_confidence=existing_plain.get('capture_confidence'),
        )
    )
    return _prepare_data_for_write(merged_plain, uid, merged_plain.get('data_protection_level', 'standard'))


def _coalesce_memory_writes(uid: str, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged_by_id: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for memory in memories:
        memory_id = memory['id']
        if memory_id not in merged_by_id:
            merged_by_id[memory_id] = memory
            order.append(memory_id)
            continue
        merged_by_id[memory_id] = _merge_memory_for_write(uid, merged_by_id[memory_id], memory)
    return [merged_by_id[memory_id] for memory_id in order]


def _merge_evidence(  # type: ignore[reportUnusedFunction]  # reserved: thin alias over merge_evidence_sets
    existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    return merge_evidence_sets(existing, incoming)


def delete_memories(uid: str) -> None:
    store = _store()
    # Chunk deletes to stay under the Firestore 500-writes-per-batch limit. A user with more than
    # 500 memories would otherwise make the single batch.commit() raise and delete nothing. Mirrors
    # the chunking in unlock_all_memories.
    batch = store.batch()
    count = 0
    for doc in store.query(_memories_path(uid)):
        batch.delete(doc.path)
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = store.batch()
            count = 0
    if count > 0:
        batch.commit()


@prepare_for_read(decrypt_func=cast(_DecryptFunc, _prepare_memory_for_read))
def get_memory(uid: str, memory_id: str) -> Optional[Dict[str, Any]]:
    snapshot = _store().get(_memory_path(uid, memory_id))
    raw: object = snapshot.to_dict()
    memory_data: Optional[Dict[str, Any]] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return memory_data


def get_memories_by_ids(uid: str, memory_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Batch fetch multiple memories by their IDs.
    Uses the port's multi-get for efficient batch retrieval.
    """
    if not memory_ids:
        return []

    memories: List[Dict[str, Any]] = []
    for doc in _store().get_many(_memories_path(uid), memory_ids):
        memory_data = _prepare_memory_for_read(_typed_doc(doc), uid)
        if memory_data:
            memories.append(memory_data)

    return memories


def review_memory(uid: str, memory_id: str, value: bool) -> None:
    _store().update(_memory_path(uid, memory_id), {'reviewed': True, 'user_review': value})


def set_memory_kg_extracted(uid: str, memory_id: str) -> None:
    _update_memory_if_exists(uid, memory_id, {'kg_extracted': True}, 'kg_extracted')


def change_memory_visibility(uid: str, memory_id: str, value: str) -> None:
    _store().update(_memory_path(uid, memory_id), {'visibility': value})


def update_memory_fields(uid: str, memory_id: str, data: Dict[str, Any]) -> None:
    """Updates specified fields for a memory and sets the updated_at timestamp."""
    if not data:
        return

    update_payload = data.copy()
    update_payload['updated_at'] = datetime.now(timezone.utc)
    _store().update(_memory_path(uid, memory_id), update_payload)


def add_evidence(uid: str, memory_id: str, evidence: Dict[str, Any]) -> None:
    """Append one provenance Evidence row to a memory if it is not already present."""
    path = _memory_path(uid, memory_id)
    doc_snapshot = _store().get(path)
    if not doc_snapshot.exists:
        return

    memory_data = _prepare_memory_for_read(_typed_doc(doc_snapshot), uid) or {}
    existing: List[Any] = memory_data.get('evidence') or []
    evidence_id = evidence.get('evidence_id')
    if evidence_id and any(
        cast(Dict[str, Any], item).get('evidence_id') == evidence_id for item in existing if isinstance(item, dict)
    ):
        return

    updated_evidence: List[Any] = existing + [evidence]
    update_payload: Dict[str, Any] = {'evidence': updated_evidence, 'updated_at': datetime.now(timezone.utc)}
    doc_level = memory_data.get('data_protection_level', 'standard')
    if doc_level == 'enhanced':
        update_payload = _encrypt_memory_data(update_payload, uid)
    _store().update(path, update_payload)


def recompute_evidence(uid: str, memory_id: str) -> List[Dict[str, Any]]:
    """Placeholder hook for later veracity/tombstone recomputation tickets."""
    memory = get_memory(uid, memory_id)
    return (memory or {}).get('evidence', [])


def edit_memory(uid: str, memory_id: str, value: str) -> Optional[Dict[str, Any]]:
    path = _memory_path(uid, memory_id)

    doc_snapshot = _store().get(path)
    if not doc_snapshot.exists:
        return

    doc_level = _typed_doc(doc_snapshot).get('data_protection_level', 'standard')
    content = value
    if doc_level == 'enhanced':
        content = encryption.encrypt(content, uid)

    update_time = datetime.now(timezone.utc)
    value_for_commit = content if doc_level == 'enhanced' else value
    content_change: Dict[str, Any] = {'to': value_for_commit}
    if doc_level == 'enhanced':
        content_change['to_sha256'] = hashlib.sha256(value.encode('utf-8')).hexdigest()

    def write_projection(tx: Any) -> None:
        snapshot = tx.get(path)
        if not snapshot.exists:
            return
        tx.update(path, {'content': content, 'edited': True, 'updated_at': update_time})

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.refine_fact(memory_id, {'content': content_change, 'edited': {'to': True}})],
        commit_time=update_time,
        projection_writer=write_projection,
        use_current_head=True,
    )


def refine_memory(uid: str, memory_id: str, arg_changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    path = _memory_path(uid, memory_id)
    update_time = datetime.now(timezone.utc)

    def write_projection(tx: Any) -> None:
        snapshot = tx.get(path)
        if not snapshot.exists:
            return
        update_payload = projection_update_for_refine(_typed_doc(snapshot) or {}, arg_changes, update_time)
        tx.update(path, update_payload)

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.refine_fact(memory_id, arg_changes)],
        commit_time=update_time,
        projection_writer=write_projection,
        use_current_head=True,
    )


@set_data_protection_level(data_arg_name='new_memory')
@prepare_for_write(data_arg_name='new_memory', prepare_func=_prepare_data_for_write)
def merge_contradict_memory(
    uid: str,
    new_memory: Dict[str, Any],
    superseded_ids: List[str],
    valid_interval: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    new_path = _memory_path(uid, new_memory['id'])
    superseded_paths = [_memory_path(uid, memory_id) for memory_id in superseded_ids]
    update_time = datetime.now(timezone.utc)
    valid_interval = valid_interval or {}
    invalid_at = valid_interval.get('valid_to') or update_time

    def build_commit(tx: Any) -> Dict[str, Any]:
        new_snapshot = tx.get(new_path)
        existing_new: Optional[Dict[str, Any]] = _typed_doc(new_snapshot) if new_snapshot.exists else None
        merged_new = _merge_memory_for_write(uid, existing_new, new_memory)

        def write_projection(write_tx: Any) -> None:
            write_tx.set(new_path, merged_new)
            for path in superseded_paths:
                write_tx.update(
                    path,
                    {
                        'invalid_at': invalid_at,
                        'superseded_by': merged_new['id'],
                        'updated_at': update_time,
                    },
                )

        return {
            'mutations': [memory_ledger.add_fact(merged_new)]
            + [
                memory_ledger.supersede_fact(
                    memory_id,
                    by=merged_new['id'],
                    kind='contradict',
                    valid_interval=valid_interval,
                )
                for memory_id in superseded_ids
            ],
            'projection_writer': write_projection,
        }

    return memory_ledger.append_commit_with_builder(uid, None, build_commit, use_current_head=True)


def projection_update_for_refine(
    memory_data: Dict[str, Any], arg_changes: Dict[str, Any], updated_at: datetime
) -> Dict[str, Any]:
    update_payload: Dict[str, Any] = {'updated_at': updated_at}
    arguments = copy.deepcopy(memory_data.get('arguments') or {})
    for key, change in arg_changes.items():
        value: Any = change
        if isinstance(change, dict) and 'to' in change:
            value = cast(Dict[str, Any], change).get('to')
        if key == 'content':
            update_payload['content'] = value
        elif key == 'edited':
            update_payload['edited'] = value
        else:
            arguments[key] = value
    update_payload['arguments'] = arguments
    return update_payload


def invalidate_memory(
    uid: str,
    memory_id: str,
    superseded_by: Optional[str] = None,
    invalid_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Soft-invalidate a memory that has been superseded or retracted.

    Unlike delete_memory this keeps the document (history) but stamps invalid_at so
    every retrieval path excludes it — the "constantly updated brain" stops surfacing
    a fact the moment it stops being true. Callers should also drop the Pinecone vector
    so the memory disappears from semantic search too.
    """
    if invalid_at is None:
        invalid_at = datetime.now(timezone.utc)
    path = _memory_path(uid, memory_id)
    update_payload: Dict[str, Any] = {'invalid_at': invalid_at, 'updated_at': datetime.now(timezone.utc)}
    if superseded_by is not None:
        update_payload['superseded_by'] = superseded_by

    if superseded_by is not None:
        ledger_mutation = memory_ledger.supersede_fact(
            memory_id,
            by=superseded_by,
            kind='contradict',
            valid_interval={'valid_to': invalid_at},
        )
    else:
        ledger_mutation = memory_ledger.retract_fact(memory_id, reason='invalidated')

    def write_projection(tx: Any) -> None:
        # Update-if-exists (ADR-0021): a missing legacy projection doc is already invalidated from
        # the caller's perspective. Guard with exists() rather than relying on an update-on-missing
        # raise, since that is adapter-defined; the ledger mutation still records the invalidation.
        if tx.get(path).exists:
            tx.update(path, update_payload)

    return memory_ledger.append_commit(
        uid,
        None,
        [ledger_mutation],
        commit_time=invalid_at,
        projection_writer=write_projection,
        use_current_head=True,
    )


def delete_memory(uid: str, memory_id: str) -> None:
    _store().delete(_memory_path(uid, memory_id))


def delete_memories_batch(uid: str, memory_ids: List[str]) -> None:
    """Delete multiple memories in a single batched write.

    The router caps a batch-delete request at MEMORIES_BATCH_MAX (100), well under
    Firestore's 500-writes-per-batch limit, but this helper mirrors the chunking in
    delete_all_memories so it stays correct if it is ever reused for larger sets.
    """
    if not memory_ids:
        return
    store = _store()
    batch = store.batch()
    count = 0
    for memory_id in memory_ids:
        batch.delete(_memory_path(uid, memory_id))
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = store.batch()
            count = 0
    if count > 0:
        batch.commit()


def delete_all_memories(uid: str) -> None:
    store = _store()
    # Chunk deletes to stay under the Firestore 500-writes-per-batch limit. Account deletion and
    # "delete all memories" hit this for any user with more than 500 memories: the single
    # batch.commit() would raise and remove nothing. Mirrors the chunking in unlock_all_memories.
    batch = store.batch()
    count = 0
    for doc in store.query(_memories_path(uid)):
        batch.delete(doc.path)
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = store.batch()
            count = 0
    if count > 0:
        batch.commit()


def ripple_source_deletion(uid: str, source_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    affected: List[Dict[str, Any]] = []

    for doc in _store().query(_memories_path(uid)):
        raw_memory = _typed_doc(doc)
        memory = _prepare_memory_for_read(raw_memory, uid) or raw_memory
        evidence = _evidence_for_source_ripple(memory, source_id, doc.id)
        if not _evidence_has_source(evidence, source_id):
            continue
        tombstoned_evidence = tombstone_evidence_for_source(evidence, source_id, now)
        active_evidence = active_evidence_items(tombstoned_evidence)
        affected.append(
            {
                'path': doc.path,
                'id': doc.id,
                'memory': memory,
                'evidence': tombstoned_evidence,
                'active_evidence': active_evidence,
            }
        )

    if not affected:
        short_term_ids = short_term_db.tombstone_source(uid, source_id)
        return {
            'updated_memory_ids': [],
            'retracted_memory_ids': [],
            'tombstoned_evidence_ids': [],
            'vector_delete_ids': [],
            'short_term_tombstoned_ids': short_term_ids,
            'commit': None,
        }

    retracted_ids = [item['id'] for item in affected if not item['active_evidence']]
    updated_ids = [item['id'] for item in affected if item['active_evidence']]
    tombstoned_evidence_ids: List[Any] = [
        cast(Dict[str, Any], evidence).get('evidence_id')
        for item in affected
        for evidence in item['evidence']
        if isinstance(evidence, dict)
        and cast(Dict[str, Any], evidence).get('source_id') == source_id
        and cast(Dict[str, Any], evidence).get('evidence_id')
    ]

    def write_projection(tx: Any) -> None:
        for item in affected:
            if item['active_evidence']:
                update_payload = _source_survival_update(item['memory'], item['evidence'], item['active_evidence'], now)
            else:
                update_payload = _payload_tombstone_update(item['evidence'], now)
            tx.update(
                item['path'],
                _prepare_data_for_write(update_payload, uid, item['memory'].get('data_protection_level', 'standard')),
            )

    mutations: List[Dict[str, Any]] = []
    for item in affected:
        for evidence in item['evidence']:
            if isinstance(evidence, dict):
                ev = cast(Dict[str, Any], evidence)
                if ev.get('source_id') == source_id and ev.get('evidence_id'):
                    mutations.append(memory_ledger.tombstone_evidence(item['id'], ev['evidence_id'], now))
        if not item['active_evidence']:
            mutations.append(memory_ledger.retract_fact(item['id'], reason='source_tombstoned'))

    commit_result = memory_ledger.append_commit(
        uid,
        None,
        mutations,
        commit_time=now,
        projection_writer=write_projection,
        use_current_head=True,
    )
    short_term_ids = short_term_db.tombstone_source(uid, source_id)
    return {
        'updated_memory_ids': updated_ids,
        'retracted_memory_ids': retracted_ids,
        'tombstoned_evidence_ids': tombstoned_evidence_ids,
        'vector_delete_ids': retracted_ids,
        'short_term_tombstoned_ids': short_term_ids,
        'commit': (commit_result or {}).get('commit'),
    }


def tombstone_evidence_for_source(
    evidence: List[Dict[str, Any]], source_id: str, tombstoned_at: datetime
) -> List[Dict[str, Any]]:
    tombstoned: List[Dict[str, Any]] = []
    for item in evidence or []:
        if not isinstance(item, dict):  # type: ignore[reportUnnecessaryIsInstance]  # defensive: legacy evidence rows may not be dicts
            tombstoned.append(item)
            continue
        next_item = copy.deepcopy(item)
        if next_item.get('source_id') == source_id:
            next_item['redaction_status'] = 'tombstoned'
            next_item['tombstoned_at'] = tombstoned_at
        tombstoned.append(next_item)
    return tombstoned


def active_evidence_items(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        item
        for item in evidence or []
        if isinstance(item, dict)  # type: ignore[reportUnnecessaryIsInstance]  # defensive: legacy evidence rows may not be dicts
        and item.get('redaction_status', 'active') != 'tombstoned'
    ]


def _source_survival_update(
    memory: Dict[str, Any],
    tombstoned_evidence: List[Dict[str, Any]],
    active_evidence: List[Dict[str, Any]],
    updated_at: datetime,
) -> Dict[str, Any]:
    update_payload: Dict[str, Any] = {
        'evidence': tombstoned_evidence,
        'updated_at': updated_at,
        'redaction_status': 'active',
    }
    update_payload.update(
        confidence_fields_for_evidence(
            active_evidence,
            memory.get('subject_attribution', 'unknown'),
            existing_capture_confidence=memory.get('capture_confidence'),
        )
    )
    return update_payload


def _payload_tombstone_update(tombstoned_evidence: List[Dict[str, Any]], updated_at: datetime) -> Dict[str, Any]:
    return {
        'content': None,
        'headline': None,
        'arguments': {},
        'evidence': tombstoned_evidence,
        'invalid_at': updated_at,
        'redaction_status': 'payload_tombstoned',
        'updated_at': updated_at,
    }


def _evidence_has_source(evidence: List[Dict[str, Any]], source_id: str) -> bool:
    return any(
        isinstance(item, dict)  # type: ignore[reportUnnecessaryIsInstance]  # defensive: legacy evidence rows may not be dicts
        and item.get('source_id') == source_id
        for item in evidence or []
    )


def _evidence_for_source_ripple(memory: Dict[str, Any], source_id: str, memory_id: str) -> List[Dict[str, Any]]:
    evidence: List[Any] = memory.get('evidence') or []
    if evidence or memory.get('memory_id') != source_id:
        return evidence
    return [
        {
            'evidence_id': f'legacy:{source_id}:{memory_id}',
            'source_id': source_id,
            'source_type': 'conversation',
            'source_signal': 'legacy',
            'independence_group': source_id,
            'capture_confidence': SOURCE_SIGNAL_CAPTURE_PRIORS['legacy'],
            'redaction_status': 'active',
        }
    ]


def get_memory_ids_for_conversation(uid: str, conversation_id: str) -> List[str]:
    """Get all memory IDs associated with a conversation."""
    return [
        doc.id
        for doc in _store().query(_memories_path(uid), filters=[('memory_id', '==', conversation_id)])
    ]


def delete_memories_for_conversation(uid: str, memory_id: str) -> Dict[str, Any]:
    result = ripple_source_deletion(uid, memory_id)
    logger.info(f"delete_memories_for_conversation {memory_id} {len(result['retracted_memory_ids'])}")
    return result


def unlock_all_memories(uid: str) -> None:
    """
    Finds all memories for a user with is_locked: True and updates them to is_locked = False.
    """
    store = _store()
    batch = store.batch()
    count = 0
    for doc in store.query(_memories_path(uid), filters=[('is_locked', '==', True)]):
        batch.update(doc.path, {'is_locked': False})
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = store.batch()
            count = 0
    if count > 0:
        batch.commit()
    logger.info(f"Unlocked all memories for user {uid}")


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************


def get_memories_to_migrate(uid: str, target_level: str) -> List[Dict[str, Any]]:
    """
    Finds all memories that are not at the target protection level by fetching all documents
    and filtering them in memory. This simplifies the code but may be less performant for
    users with a very large number of documents.
    """
    to_migrate: List[Dict[str, Any]] = []
    for doc in _store().query(_memories_path(uid), fields=['data_protection_level']):
        doc_data = _typed_doc(doc)
        current_level = doc_data.get('data_protection_level', 'standard')
        if target_level != current_level:
            to_migrate.append({'id': doc.id, 'type': 'memory'})

    return to_migrate


def migrate_memories_level_batch(uid: str, memory_ids: List[str], target_level: str) -> None:
    """
    Migrates a batch of memories to the target protection level.
    """
    store = _store()
    batch = store.batch()

    for doc_snapshot in store.get_many(_memories_path(uid), memory_ids):
        memory_data = _typed_doc(doc_snapshot)
        current_level = memory_data.get('data_protection_level', 'standard')

        if current_level == target_level:
            continue

        # Decrypt the data first (if needed) to get a clean slate.
        plain_data = _prepare_memory_for_read(memory_data, uid)

        plain_content = cast(Dict[str, Any], plain_data).get('content')
        migrated_content = plain_content
        if target_level == 'enhanced':
            if isinstance(plain_content, str):
                migrated_content = encryption.encrypt(plain_content, uid)

        # Update the document with the migrated data and the new protection level.
        update_data = {'data_protection_level': target_level, 'content': migrated_content}
        batch.update(doc_snapshot.path, update_data)

    batch.commit()


def migrate_memories(prev_uid: str, new_uid: str, app_id: Optional[str] = None) -> int:
    """
    Migrate memories from one user to another.
    If app_id is provided, only migrate memories related to that app.
    """
    logger.info(f'Migrating memories from {prev_uid} to {new_uid}')

    store = _store()
    filters: List[Filter] = [('app_id', '==', app_id)] if app_id else []

    # Get memories to migrate
    memories_to_migrate: List[Dict[str, Any]] = [
        _typed_doc(doc) for doc in store.query(_memories_path(prev_uid), filters=filters)
    ]

    if not memories_to_migrate:
        logger.info(f'No memories to migrate for user {prev_uid}')
        return 0

    # Create batch for destination user
    batch = store.batch()

    # Add memories to batch
    for memory in memories_to_migrate:
        # Enhanced memories are encrypted with a per-user key (the uid is the HKDF salt), so content
        # encrypted for prev_uid is unreadable to new_uid. Decrypt with the previous user's key and
        # re-encrypt with the new user's key before copying, so the new owner can read them.
        content = memory.get('content')
        if memory.get('data_protection_level') == 'enhanced' and isinstance(content, str) and content:
            plaintext = encryption.decrypt(content, prev_uid)
            if plaintext == content:
                # encryption.decrypt returns its input unchanged when it cannot decrypt (wrong key or
                # corrupted ciphertext) rather than raising, so an unchanged value means decryption
                # failed. Copy the memory as-is and log it, rather than re-encrypting the still-
                # encrypted content under new_uid (which the new owner could "decrypt" back to the old
                # ciphertext, masking the corruption).
                logger.warning(f"migrate_memories: could not decrypt memory {memory.get('id')}; copying as-is")
            else:
                memory = {**memory, 'content': encryption.encrypt(plaintext, new_uid)}
        batch.set(_memory_path(new_uid, memory['id']), memory)

    # Commit batch
    batch.commit()
    logger.info(f'Migrated {len(memories_to_migrate)} memories from {prev_uid} to {new_uid}')
    return len(memories_to_migrate)
