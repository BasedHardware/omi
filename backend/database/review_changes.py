"""Atomic reversible edits and journal, with durable agent suppression.

The writer applies the edit and journal in the same ledger transaction. Callers
must never edit first and record later. Undo/redo compare only owned fields,
so unrelated edits survive and conflicting later edits return 409. No deletes
of memories or person records. Entity merges retain a redirect node.
"""

import copy
from datetime import datetime, timedelta, timezone
from typing import Literal

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, ConfigDict, Field

from database import entities, memory_ledger, review_queries, review_store as store
from database.read_boundary import parse_payload_strict
from models.review import ReviewChange, ReviewChangesResponse

WINDOW = timedelta(days=30)


class _Unchanged(Exception):
    pass


ALLOWED_FIELDS = {
    'knowledge_nodes': {'label', 'label_lower', 'aliases', 'aliases_lower', 'merged_entity_ids', 'redirect_entity_id'},
    'people': {'name', 'aliases', 'organization', 'subtitle'},
    'conversations': {
        'user_title',
        'structured.title',
        'structured.overview',
        'structured.sections',
        'structured.note_claims',
        'transcript_segments',
        'manual_speaker_assignments',
    },
    'action_items': {'status', 'completed', 'completed_at'},
}


class AgentEdit(BaseModel):
    """Internal writer input. Patch keys are constrained to supported reversible fields."""

    model_config = ConfigDict(extra='forbid')
    collection: Literal['knowledge_nodes', 'people', 'conversations', 'action_items']
    document_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    patch: dict


def _get(data: dict, path: str) -> dict:
    value = data
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return {'present': False}
        value = value[key]
    return {'present': True, 'value': copy.deepcopy(value)}


def _patch_value(value: dict):
    return value['value'] if value['present'] else firestore.DELETE_FIELD


def _wire(data: dict) -> ReviewChange:
    return parse_payload_strict(
        ReviewChange,
        data['change'],
        document_path='review_changes/' + store.safe_id(data['change'].get('change_id', 'unknown')),
    )


def agent_change_allowed(uid: str, edit_key: str) -> bool:
    """Dream MUST check this key before planning an edit; record also enforces it."""
    return not store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key)).get().exists


def record_agent_change(
    uid: str,
    change: ReviewChange,
    edits: list[AgentEdit] | None = None,
    *,
    edit_key: str,
    memory_edit=None,
    expected_documents: dict | None = None,
    entity_merge: tuple[str, str] | None = None
) -> ReviewChange:
    """Apply and journal a supported edit exactly once, keyed by change_id.

    edit_key is a stable semantic operation key, independent of a run/change id.
    Agent retries and new runs cannot bypass an undo with a new change_id.
    Speaker transcript/assignment patches must be produced by the authorized
    speaker teaching path, including its generation fence; wire clients cannot
    supply AgentEdit. Transcript payloads must already be storage-encoded.
    """
    store.require_enabled()
    if memory_edit is not None:
        if getattr(memory_edit, 'duplicate_memory_id', None):
            from database.review_memory_merges import record_merge

            return record_merge(uid, change, memory_edit, edit_key)
        from database.review_memory_changes import record_memory_change

        return record_memory_change(uid, change, memory_edit, edit_key)
    if not edit_key.strip() or not edits or len(edits) > 100 or change.undone:
        raise ValueError('An edit key and 1..100 edits are required')
    keys = {(e.collection, e.document_id) for e in edits}
    if len(keys) != len(edits):
        raise ValueError('Each document may be patched only once')
    if change.kind == 'merge_memories':
        raise ValueError('Memory edits require memory_edit')
    for edit in edits:
        if edit.collection == 'action_items' and ('status' in edit.patch or 'completed' in edit.patch):
            if edit.patch.get('completed') != (edit.patch.get('status') == 'completed'):
                raise ValueError('Task status and completed must agree')
        if not edit.patch or not set(edit.patch) <= ALLOWED_FIELDS[edit.collection]:
            raise ValueError('Unsupported journal edit fields')
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change.change_id))
    marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key))
    result = {}

    def build(tx):
        existing = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        blocked = marker.get(transaction=tx).exists
        snapshots = [(e, store.user(uid).collection(e.collection).document(e.document_id)) for e in edits]
        rows = [(e, r, r.get(transaction=tx).to_dict()) for e, r in snapshots]
        if existing:
            if existing['edit_key'] != edit_key:
                raise store.ReviewConflict('Change identity conflict')
            result.update(existing)
            raise _Unchanged
        if blocked:
            raise store.ReviewConflict('Agent edit was undone by the user')
        records = []
        for edit, _, data in rows:
            if expected_documents is not None and data != expected_documents.get(edit.document_id):
                raise store.ReviewConflict('Entity changed while preparing merge')
            if not data or data.get('deleted') or data.get('is_dismissed') or data.get('discarded'):
                raise store.ReviewNotFound('Edit target not found')
            records.append(
                {
                    'collection': edit.collection,
                    'document_id': edit.document_id,
                    'before': {k: _get(data, k) for k in edit.patch},
                    'after': {k: {'present': True, 'value': v} for k, v in edit.patch.items()},
                }
            )
        journal = {
            'change': change.model_dump(mode='python'),
            'created_at': change.created_at,
            'edit_key': edit_key,
            'edits': records,
            'entity_merge': list(entity_merge) if entity_merge else None,
        }
        mutations = (
            [memory_ledger.merge_entities(*entity_merge, evidence={'review_change_id': change.change_id})]
            if entity_merge
            else [memory_ledger.mutation('agent_edit', change_id=change.change_id, edit_key=edit_key)]
        )
        result.update(journal)

        def write(transaction):
            for edit, target, _ in rows:
                transaction.update(target, edit.patch)
            transaction.set(ref, store.encode_doc(uid, journal))

        return {'mutations': mutations, 'projection_writer': write}

    try:
        memory_ledger.append_commit_with_builder(
            uid, None, build, use_current_head=True, firestore_client=store.client()
        )
    except _Unchanged:
        pass
    return _wire(result)


def merge_review_entities(uid: str, change: ReviewChange, left: str, right: str, *, edit_key: str) -> ReviewChange:
    """Use the existing merge mutation, keeping the secondary as a redirect for facts/edges.

    People ids remain stable; the derived page folds facts/edges of both nodes.
    Undo restores each node's owned fields through a ledger split mutation.
    """
    store.require_enabled()

    # Older people records need no graph backfill to participate. Materialize
    # only their canonical identity, preserving stable person ids on undo.
    @firestore.transactional
    def ensure_nodes(tx):
        rows = []
        for entity_id in (left, right):
            ref = store.user(uid).collection('knowledge_nodes').document(entity_id)
            node = ref.get(transaction=tx).to_dict()
            if node is None and entity_id.startswith('person:'):
                person = (
                    store.user(uid)
                    .collection('people')
                    .document(entity_id.removeprefix('person:'))
                    .get(transaction=tx)
                    .to_dict()
                )
                if not person or person.get('is_dismissed'):
                    raise store.ReviewNotFound('Person not found')
                name = person.get('name') or entity_id
                rows.append(
                    (
                        ref,
                        {
                            'id': entity_id,
                            'label': name,
                            'label_lower': name.lower(),
                            'node_type': 'person',
                            'aliases': [],
                            'aliases_lower': [],
                            'memory_ids': [],
                        },
                    )
                )
        for ref, node in rows:
            tx.set(ref, node)

    ensure_nodes(store.client().transaction())
    a = store.user(uid).collection('knowledge_nodes').document(left).get().to_dict()
    b = store.user(uid).collection('knowledge_nodes').document(right).get().to_dict()
    if left == right or not a or not b or a.get('redirect_entity_id') or b.get('redirect_entity_id'):
        raise store.ReviewConflict('Two current distinct entity nodes are required')
    merged = entities.apply_entity_mutations({left: a, right: b}, [memory_ledger.merge_entities(left, right)])[left]
    aliases = merged.get('aliases', [])
    return record_agent_change(
        uid,
        change,
        [
            AgentEdit(
                collection='knowledge_nodes',
                document_id=left,
                patch={
                    'aliases': aliases,
                    'aliases_lower': [s.lower() for s in aliases],
                    'merged_entity_ids': merged['merged_entity_ids'],
                },
            ),
            AgentEdit(collection='knowledge_nodes', document_id=right, patch={'redirect_entity_id': left}),
        ],
        edit_key=edit_key,
        entity_merge=(left, right),
        expected_documents={left: a, right: b},
    )


def set_undone(uid: str, change_id: str, undone: bool, *, now: datetime | None = None) -> ReviewChange:
    now = now or datetime.now(timezone.utc)
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change_id))
    data = store.decode_doc(uid, ref.get().to_dict())
    if data and data.get('memory_edit'):
        if data['created_at'] < now - WINDOW:
            raise store.ReviewNotFound('Change is outside the 30-day undo window')
        if data.get('memory_merge'):
            from database.review_memory_merges import set_undone as set_memory_merge_undone

            return set_memory_merge_undone(uid, change_id, undone, data)
        from database.review_memory_changes import set_memory_undone

        return set_memory_undone(uid, change_id, undone, data)
    result = {}

    def build(tx):
        data = store.decode_doc(uid, ref.get(transaction=tx).to_dict())
        if not data or data['created_at'] < now - WINDOW:
            raise store.ReviewNotFound('Change is outside the 30-day undo window')
        result.update(data)
        if data.get('memory_edit'):
            raise store.ReviewConflict('Canonical memory edit requires its own apply path')
        if data['change']['undone'] == undone:
            raise _Unchanged
        expected, destination = ('after', 'before') if undone else ('before', 'after')
        rows = []
        for edit in data['edits']:
            target = store.user(uid).collection(edit['collection']).document(edit['document_id'])
            current = target.get(transaction=tx).to_dict()
            if not current or current.get('deleted') or current.get('is_dismissed') or current.get('discarded'):
                raise store.ReviewConflict('Edit target no longer available')
            if any(_get(current, key) != value for key, value in edit[expected].items()):
                raise store.ReviewConflict('Target has a newer edit')
            rows.append((target, {key: _patch_value(value) for key, value in edit[destination].items()}, current))
        change = dict(data['change'], undone=undone)
        result['change'] = change
        merge = data.get('entity_merge')
        mutations = [memory_ledger.mutation('undo_agent_edit' if undone else 'redo_agent_edit', change_id=change_id)]
        if merge:
            if undone:
                restored = []
                for target, patch, current in rows:
                    restored_doc = copy.deepcopy(current)
                    for key, value in patch.items():
                        if value is firestore.DELETE_FIELD:
                            restored_doc.pop(key, None)
                        else:
                            restored_doc[key] = value
                    restored.append(restored_doc | {'id': target.id})
                mutations = [memory_ledger.split_entity(merge[0], restored, reason='Review undo')]
            else:
                mutations = [memory_ledger.merge_entities(*merge, evidence={'review_change_id': change_id})]

        def write(transaction):
            for target, patch, _ in rows:
                transaction.update(target, patch)
            transaction.update(ref, store.encode_doc(uid, {'change': change}))
            if undone:
                marker = store.user(uid).collection('review_do_not_redo').document(store.safe_id(data['edit_key']))
                transaction.set(marker, {'edit_key': data['edit_key'], 'change_id': change_id, 'created_at': now})

        return {'mutations': mutations, 'projection_writer': write}

    try:
        memory_ledger.append_commit_with_builder(
            uid, None, build, use_current_head=True, firestore_client=store.client()
        )
    except _Unchanged:
        pass
    return _wire(result)


def list_changes(uid: str, cursor: str | None = None, *, now: datetime | None = None) -> ReviewChangesResponse:
    now = now or datetime.now(timezone.utc)
    query = review_queries.CHANGES.build(
        store.user(uid).collection('review_changes'), {'since': now - WINDOW}, field_filter_factory=FieldFilter
    )
    query = query.order_by('created_at', direction='DESCENDING').order_by('__name__', direction='DESCENDING')
    if cursor:
        snap = store.user(uid).collection('review_changes').document(store.safe_id(cursor)).get()
        if not snap.exists or snap.to_dict()['created_at'] < now - WINDOW:
            raise store.ReviewConflict('Invalid change cursor')
        query = query.start_after(snap)
    rows = [store.require_doc(uid, s.to_dict()) for s in query.limit(31).stream()]
    return ReviewChangesResponse(
        changes=[_wire(row) for row in rows[:30] if row.get('phase', 'applied') == 'applied'],
        next_cursor=rows[29]['change']['change_id'] if len(rows) > 30 else None,
    )
