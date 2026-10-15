"""Atomic reversible edits and journal, with durable agent suppression.

The writer applies the edit and journal in the same ledger transaction. Callers
must never edit first and record later. Undo/redo compare only owned fields,
so unrelated edits survive and conflicting later edits return 409. No deletes
of memories or person records. Entity merges retain a redirect node.
"""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, ConfigDict, Field

from database import (
    entities,
    memory_ledger,
    review_memory_hygiene,
    review_queries,
    review_store as store,
)
from database.action_items_cache import bump_action_items_list_version
from database import review_exact_undo
from database.review_field_states import read_field_state, write_field_state
from utils.dream_metrics import record_undo
from utils.review_projection import sync_conversations
from database.read_boundary import parse_payload_strict
from models.review import ReviewChange, ReviewChangesResponse

WINDOW = timedelta(days=30)


class _Unchanged(Exception):
    pass


from utils.agent_capabilities.registry import journal_fields

ALLOWED_FIELDS = journal_fields()


class AgentEdit(BaseModel):
    """Internal writer input. Patch keys are constrained to supported reversible fields."""

    model_config = ConfigDict(extra='forbid')
    collection: Literal[
        'knowledge_nodes', 'people', 'conversations', 'action_items', 'entity_pages', 'dream_vocabulary'
    ]
    document_id: str = Field(min_length=1, max_length=128, pattern=r'^[^/]+$')
    patch: dict


def _wire(data: dict) -> ReviewChange:
    return parse_payload_strict(
        ReviewChange,
        data['change'],
        document_path='review_changes/' + store.safe_id(data['change'].get('change_id', 'unknown')),
    )


def agent_change_allowed(uid: str, edit_key: str) -> bool:
    """Dream MUST check this key before planning an edit; record also enforces it."""
    keys = [edit_key]
    if edit_key.startswith('agent:'):
        keys.append('dream:' + edit_key.removeprefix('agent:'))
    return not any(
        store.user(uid).collection('review_do_not_redo').document(store.safe_id(key)).get().exists for key in keys
    )


def suppress_agent_change(uid: str, edit_key: str) -> None:
    """A dismissed Review operation uses the same durable fence as an undo."""
    store.require_enabled(uid)
    store.user(uid).collection('review_do_not_redo').document(store.safe_id(edit_key)).set(
        {'edit_key': edit_key, 'created_at': datetime.now(timezone.utc)}
    )


def record_agent_change(
    uid: str,
    change: ReviewChange,
    edits: list[AgentEdit] | None = None,
    *,
    edit_key: str,
    memory_edit=None,
    expected_documents: dict | None = None,
    expected_records: dict | None = None,
    entity_merge: tuple[str, str] | None = None,
    exact_undo: bool = False,
    witness_records: dict | None = None,
) -> ReviewChange:
    """Apply and journal a supported edit exactly once, keyed by change_id.

    edit_key is a stable semantic operation key, independent of a run/change id.
    Agent retries and new runs cannot bypass an undo with a new change_id.
    Speaker transcript/assignment patches must be produced by the authorized
    speaker teaching path, including its generation fence; wire clients cannot
    supply AgentEdit. Transcript payloads must already be storage-encoded.
    """
    store.require_enabled(uid)
    if memory_edit is not None:
        if getattr(memory_edit, 'duplicate_memory_id', None):
            from database.review_memory_merges import record_merge

            return record_merge(uid, change, memory_edit, edit_key, expected_records=expected_records)
        from database.review_memory_changes import record_memory_change

        return record_memory_change(uid, change, memory_edit, edit_key, expected_records=expected_records)
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
        if blocked and not store.is_user_request(uid):
            raise store.ReviewConflict('Agent edit was undone by the user')
        store.validate_records(uid, tx, expected_records)
        records = []
        for edit, _, data in rows:
            if expected_documents is not None and data != expected_documents.get(edit.document_id):
                raise store.ReviewConflict('Entity changed while preparing merge')
            if data is None and edit.collection in {'entity_pages', 'dream_vocabulary'}:
                data = {}
            if data is None or data.get('deleted') or data.get('is_dismissed') or data.get('discarded'):
                raise store.ReviewNotFound('Edit target not found')
            records.append(
                {
                    'collection': edit.collection,
                    'document_id': edit.document_id,
                    'before': {k: read_field_state(data, k) for k in edit.patch},
                    'after': {k: {'present': True, 'value': v} for k, v in edit.patch.items()},
                }
            )
        journal: dict[str, Any] = {
            'change': change.model_dump(mode='python'),
            'created_at': change.created_at,
            'edit_key': edit_key,
            'edits': records,
            'entity_merge': list(entity_merge) if entity_merge else None,
        }
        if exact_undo:
            journal.update(
                review_exact_undo.journal_fences(edits, rows, expected_records, witnesses=witness_records, uid=uid)
            )
        mutations = (
            [memory_ledger.merge_entities(*entity_merge, evidence={'review_change_id': change.change_id})]
            if entity_merge
            else [memory_ledger.mutation('agent_edit', change_id=change.change_id, edit_key=edit_key)]
        )
        result.update(journal)

        def write(transaction):
            for edit, target, original in rows:
                if original is None:
                    transaction.set(target, edit.patch)
                else:
                    transaction.update(target, edit.patch)
            transaction.set(ref, store.encode_doc(uid, journal))

        return {'mutations': mutations, 'projection_writer': write}

    try:
        memory_ledger.append_commit_with_builder(
            uid, None, build, use_current_head=True, firestore_client=store.client()
        )
    except _Unchanged:
        pass
    sync_conversations(uid, edits, firestore_client=store.client())
    if edits and any(edit.collection == 'action_items' for edit in edits):
        bump_action_items_list_version(uid)
    return _wire(result)


def merge_review_entities(
    uid: str, change: ReviewChange, left: str, right: str, *, edit_key: str, expected_records: dict | None = None
) -> ReviewChange:
    """Use the existing merge mutation, keeping the secondary as a redirect for facts/edges.

    People ids remain stable; the derived page folds facts/edges of both nodes.
    Undo restores each node's owned fields through a ledger split mutation.
    """
    store.require_enabled(uid)

    # Older people records need no graph backfill to participate. Materialize
    # only their canonical identity, preserving stable person ids on undo.
    @firestore.transactional
    def ensure_nodes(tx):
        store.validate_records(uid, tx, expected_records)
        rows = []
        nodes = {}
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
            nodes[entity_id] = node
        for ref, node in rows:
            tx.set(ref, node)
            nodes[ref.id] = node
        return nodes, {ref.id for ref, _ in rows}

    nodes, created = ensure_nodes(store.client().transaction())
    a, b = nodes.get(left), nodes.get(right)
    fences = dict(expected_records or {})
    for entity_id in created:
        path = 'knowledge_nodes/' + entity_id
        # Only the node this transaction minted may replace its missing
        # witness. Never bless a fresh reread or discard unrelated null fences.
        fences[path] = nodes[entity_id]
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
        expected_records=fences,
    )


def set_undone(uid: str, change_id: str, undone: bool, *, now: datetime | None = None) -> ReviewChange:
    now = now or datetime.now(timezone.utc)
    ref = store.user(uid).collection('review_changes').document(store.safe_id(change_id))
    data = store.decode_doc(uid, ref.get().to_dict())

    def tracked(change):
        if undone and data and not data['change']['undone']:
            record_undo(change)
        return change

    if data and data.get('memory_hygiene'):
        if data['created_at'] < now - WINDOW:
            raise store.ReviewNotFound('Change is outside the 30-day undo window')
        return tracked(review_memory_hygiene.set_undone(uid, change_id, undone))
    if data and data.get('transcript_overlay'):
        if data['created_at'] < now - WINDOW:
            raise store.ReviewNotFound('Change is outside the 30-day undo window')
        from database.review_transcript_changes import set_undone as set_transcript_undone

        return tracked(set_transcript_undone(uid, change_id, undone))
    if data and data.get('memory_edit'):
        if data['created_at'] < now - WINDOW:
            raise store.ReviewNotFound('Change is outside the 30-day undo window')
        if data.get('memory_merge'):
            from database.review_memory_merges import set_undone as set_memory_merge_undone

            return tracked(set_memory_merge_undone(uid, change_id, undone, data))
        from database.review_memory_changes import set_memory_undone

        return tracked(set_memory_undone(uid, change_id, undone, data))
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
        review_exact_undo.validate_generation(uid, tx, data)
        if not undone:
            # Merge cleanups hide the target behind a surviving row; Redo must
            # not resurrect superseded_by/dream_duplicate_of links pointing at
            # a survivor that changed or disappeared after Undo.
            for survivor_path, expected_fence in (data.get('witness_fences') or {}).items():
                survivor_collection, survivor_id = survivor_path.split('/', 1)
                survivor = (
                    store.user(uid).collection(survivor_collection).document(survivor_id).get(transaction=tx).to_dict()
                )
                observed = (
                    review_exact_undo.witness_snapshot(uid, survivor_path, survivor)
                    if isinstance(expected_fence, dict) and survivor is not None
                    else store.fingerprint(survivor)
                )
                if survivor is None or observed != expected_fence:
                    raise store.ReviewConflict('Cleanup survivor has a newer edit')
        rows = []
        exact_restores = {}
        for edit in data['edits']:
            target = store.user(uid).collection(edit['collection']).document(edit['document_id'])
            current = target.get(transaction=tx).to_dict()
            exact = review_exact_undo.validate_row(data, edit['collection'], edit['document_id'], current, expected)
            if current is None or (
                not exact and (current.get('deleted') or current.get('is_dismissed') or current.get('discarded'))
            ):
                raise store.ReviewConflict('Edit target no longer available')
            if (
                edit['collection'] == 'conversations'
                and 'transcript_segments' in edit[expected]
                and current.get('has_transcript_corrections')
            ):
                overlay = (
                    store.user(uid)
                    .collection('transcript_corrections')
                    .document(edit['document_id'])
                    .get(transaction=tx)
                    .to_dict()
                )
                from database.conversations import decode_transcript_segments_verified

                def decode(state):
                    return decode_transcript_segments_verified(
                        uid, state.get('value') or [], bool(current.get('transcript_segments_compressed'))
                    )

                before_segments = decode(edit['before']['transcript_segments'])
                after_segments = decode(edit['after']['transcript_segments'])
                touched = {
                    index
                    for index in range(max(len(before_segments), len(after_segments)))
                    if index >= min(len(before_segments), len(after_segments))
                    or before_segments[index].get('text') != after_segments[index].get('text')
                }
                if any(
                    not row['undone'] and row['segment_index'] in touched
                    for row in store.require_doc(uid, overlay)['source']
                ):
                    raise store.ReviewConflict('Transcript has a dependent newer correction')
            if any(read_field_state(current, key) != value for key, value in edit[expected].items()):
                raise store.ReviewConflict('Target has a newer edit')
            if exact:
                # A full-row fence permits exact replacement without DELETE_FIELD
                # transforms. Missing fields stay missing, including after Redo.
                exact_restores[target.path] = review_exact_undo.restored_row(current, edit[destination])
            rows.append((target, {key: write_field_state(value) for key, value in edit[destination].items()}, current))
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
                identity = target.path
                if identity in exact_restores:
                    transaction.set(target, exact_restores[identity])
                else:
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
        return _wire(result)
    sync_conversations(uid, result['edits'], firestore_client=store.client())
    if any(edit.get('collection') == 'action_items' for edit in result.get('edits', [])):
        bump_action_items_list_version(uid)
    return tracked(_wire(result))


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
