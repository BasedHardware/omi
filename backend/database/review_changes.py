"""Atomic reversible edits and journal, with durable agent suppression.

The writer applies the edit and journal in the same ledger transaction. Callers
must never edit first and record later. Undo/redo compare only owned fields,
so unrelated edits survive and conflicting later edits return 409. No deletes
of memories or person records. Entity merges retain a redirect node.
"""

import copy
import hashlib
import re
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
from database.people_generation import bump_people_generation
from database.action_items_cache import bump_action_items_list_version
from database import review_exact_undo
from database.review_field_states import read_field_state, write_field_state
from utils.dream_metrics import record_undo
from utils.review_projection import sync_conversations
from config.dream_agent import dream_journal_key, eligible
from database.read_boundary import parse_payload_strict
from models.review import ReviewChange, ReviewChangeDiff, ReviewChangesResponse

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
            if (data is None or data.get('deleted')) and edit.collection in {
                'conversations',
                'memory_items',
                'memories',
            }:
                raise store.ReviewStale('Edit target deleted')
            if data is None or data.get('deleted') or data.get('is_dismissed') or data.get('discarded'):
                raise store.ReviewConflict('Edit target unavailable')
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
                if edit.collection == 'people':
                    bump_people_generation(transaction, target)
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
        rows = []
        nodes = {}
        bootstrapped = set()
        fences = dict(expected_records or {})
        for entity_id in (left, right):
            ref = store.user(uid).collection('knowledge_nodes').document(entity_id)
            node = ref.get(transaction=tx).to_dict()
            path = 'knowledge_nodes/' + entity_id
            if entity_id.startswith('person:') and (node is None or (path in fences and fences[path] is None)):
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
                bootstrap = {
                    'id': entity_id,
                    'label': name,
                    'label_lower': name.lower(),
                    'node_type': 'person',
                    'aliases': [],
                    'aliases_lower': [],
                    'memory_ids': [],
                }
                if node is None:
                    rows.append((ref, bootstrap))
                elif node == bootstrap:
                    # A gate retry may see exactly the canonical node the first
                    # attempt minted. All other fields and witnesses stay fenced.
                    fences[path] = bootstrap
                    bootstrapped.add(entity_id)
            nodes[entity_id] = node
        store.validate_records(uid, tx, fences)
        for ref, node in rows:
            tx.set(ref, node)
            nodes[ref.id] = node
            bootstrapped.add(ref.id)
        return nodes, bootstrapped

    nodes, created = ensure_nodes(store.client().transaction())
    a, b = nodes.get(left), nodes.get(right)
    fences = dict(expected_records or {})
    for entity_id in created:
        path = 'knowledge_nodes/' + entity_id
        # Only an exact canonical bootstrap may replace its missing witness.
        fences[path] = nodes[entity_id]
    if left == right:
        raise store.ReviewStale('Two current distinct entity nodes are required')
    if not a or not b or a.get('redirect_entity_id') or b.get('redirect_entity_id'):
        raise store.ReviewConflict('Entity changed while preparing merge')
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
            rows.append(
                (
                    edit['collection'],
                    target,
                    {key: write_field_state(value) for key, value in edit[destination].items()},
                    current,
                )
            )
        change = dict(data['change'], undone=undone)
        result['change'] = change
        merge = data.get('entity_merge')
        mutations = [memory_ledger.mutation('undo_agent_edit' if undone else 'redo_agent_edit', change_id=change_id)]
        if merge:
            if undone:
                restored = []
                for _, target, patch, current in rows:
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
            for collection, target, patch, _ in rows:
                if collection == 'people':
                    bump_people_generation(transaction, target)
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


_DIFF_CONTEXT = 120
_DIFF_SPAN = 240
_DIFF_TEXT = 500
_DIFF_LABEL = 180
_TEXT_FIELDS = ('structured.title', 'user_title', 'description', 'name', 'summary', 'language', 'content')


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
    user = store.user(uid).get().to_dict() or {}
    show_dream = eligible(uid, user)
    changes = []
    for row in rows[:30]:
        if row.get('phase', 'applied') != 'applied':
            continue
        if not show_dream and dream_journal_key(row.get('edit_key')):
            continue
        change = _wire(row)
        diff = extract_change_diff(row)
        if diff is not None:
            change = change.model_copy(update={'diff': diff})
        changes.append(change)
    return ReviewChangesResponse(
        changes=changes,
        next_cursor=rows[29]['change']['change_id'] if len(rows) > 30 else None,
    )


def extract_change_diff(row: object) -> ReviewChangeDiff | None:
    """Read-time excerpt from an already decrypted, owner-scoped journal row.

    Old rows that do not store the before/after text return no diff. This does
    not read another document and never returns a whole transcript.
    """
    try:
        return _extract_change_diff(row)
    except Exception:
        return None


def _extract_change_diff(row: object) -> ReviewChangeDiff | None:
    if not isinstance(row, dict):
        return None
    change = row.get('change')
    if not isinstance(change, dict):
        return None
    if _is_merge(row, change):
        found = _merge_diff(row, change)
        if found is not None:
            return found
    found = _spelling_or_transcript(row, change)
    if found is not None:
        return found
    found = _memory_diff(row, change)
    if found is not None:
        return found
    return _edit_diff(row, change)


def _is_merge(row: dict, change: dict) -> bool:
    kind = change.get('edit_kind') or change.get('kind') or ''
    if isinstance(kind, str) and kind.startswith('merge'):
        return True
    return bool(row.get('memory_merge') or row.get('entity_merge'))


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _spelling_or_transcript(row: dict, change: dict) -> ReviewChangeDiff | None:
    overlay = _as_dict(row.get('transcript_overlay'))
    corrections = _as_list(overlay.get('corrections'))
    active = [item for item in corrections if isinstance(item, dict) and not item.get('undone')]
    transcript_rows = [
        item
        for item in active
        if item.get('kind') == 'transcript'
        and isinstance(item.get('before'), str)
        and isinstance(item.get('after'), str)
    ]
    if transcript_rows:
        return _transcript_diff(transcript_rows, change)
    terms = _spelling_terms(change, active)
    if terms is None:
        return None
    before, after = terms
    texts = _context_texts(change)
    if not any(_count_term(text, before) for text in texts):
        return None
    main = _main_text(change, texts, before) or next(text for text in texts if _count_term(text, before))
    located = _locate(main, before)
    if located is None:
        return None
    _span, context_before, context_after = _window(main, *located)
    visible = sum(_count_term(text, before) for text in texts)
    segment_hits = len([item for item in active if item.get('kind') == 'spelling'])
    return _finish(
        change,
        field='transcript',
        before=before,
        after=after,
        context_before=context_before,
        context_after=context_after,
        occurrences=max(visible, segment_hits, 1),
    )


def _transcript_diff(rows: list[dict], change: dict) -> ReviewChangeDiff | None:
    spans = []
    for item in rows:
        spans.extend(_changed_spans(item['before'], item['after']))
    if not spans:
        return None
    source, dest, start, end, after_start, after_end = spans[0]
    span, context_before, context_after = _window(source, start, end)
    return _finish(
        change,
        field='transcript',
        before=span,
        after=dest[after_start:after_end],
        context_before=context_before,
        context_after=context_after,
        occurrences=len(spans),
    )


def _spelling_terms(change: dict, corrections: list[dict]):
    edit_kind = change.get('edit_kind')
    spelling_rows = [item for item in corrections if item.get('kind') == 'spelling']
    if edit_kind != 'spelling' and not spelling_rows:
        return None
    before = change.get('before') if isinstance(change.get('before'), str) else ''
    after = change.get('after') if isinstance(change.get('after'), str) else ''
    if spelling_rows:
        sample = spelling_rows[0]
        if isinstance(sample.get('before'), str) and not before:
            before = sample['before']
        if isinstance(sample.get('after'), str) and not after:
            after = sample['after']
    if not before or not after or before == after or len(before) > 50 or len(after) > 50:
        return None
    return before, after


def _memory_diff(row: dict, change: dict) -> ReviewChangeDiff | None:
    edit_kind = change.get('edit_kind')
    has_memory = isinstance(row.get('memory_edit'), dict) or isinstance(row.get('memory_hygiene'), dict)
    if not has_memory and edit_kind not in {'memory', 'retire_memory', 'supersede_memory'}:
        return None
    before_text = _memory_text(row.get('before'))
    after_text = None
    edit = row.get('memory_edit')
    if isinstance(edit, dict) and isinstance(edit.get('content'), str):
        after_text = edit['content']
    hygiene = row.get('memory_hygiene')
    if isinstance(hygiene, dict):
        if before_text is None:
            before_text = _memory_text(hygiene.get('before'))
        if after_text is None:
            after_text = _memory_text(hygiene.get('after'), prefer_new=True)
    if before_text is None and isinstance(change.get('before'), str):
        before_text = change['before']
    if after_text is None and isinstance(change.get('after'), str):
        after_text = change['after']
    if before_text is None or after_text is None or before_text == after_text:
        return None
    return _text_field_diff('content', before_text, after_text, change)


def _memory_text(value, prefer_new: bool = False):
    if isinstance(value, dict) and isinstance(value.get('content'), str):
        return value['content']
    if isinstance(value, dict):
        contents = []
        for key, row in value.items():
            if isinstance(row, dict) and isinstance(row.get('content'), str):
                contents.append((str(key), row['content']))
        if not contents:
            return None
        if prefer_new:
            return contents[-1][1]
        return contents[0][1]
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict) and isinstance(row.get('content'), str):
                return row['content']
    return None


def _edit_diff(row: dict, change: dict) -> ReviewChangeDiff | None:
    edits = row.get('edits')
    if not isinstance(edits, list):
        return _change_text_diff(change)
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        before_map = _as_dict(edit.get('before'))
        after_map = _as_dict(edit.get('after'))
        for name in _TEXT_FIELDS:
            before = _state_text(before_map.get(name))
            after = _state_text(after_map.get(name))
            if before is None and after is None:
                continue
            if before == after:
                continue
            field = 'title' if name in {'structured.title', 'user_title'} else name
            return _text_field_diff(field, before or '', after or '', change)
        before_status = _state_text(before_map.get('status'))
        after_status = _state_text(after_map.get('status'))
        if before_status and after_status and before_status != after_status:
            return _text_field_diff('status', before_status, after_status, change)
    return _change_text_diff(change)


def _change_text_diff(change: dict) -> ReviewChangeDiff | None:
    edit_kind = change.get('edit_kind')
    if not isinstance(edit_kind, str) or edit_kind not in {
        'title',
        'overview',
        'close_task',
        'memory',
        'retire_task',
        'set_language',
    }:
        return None
    raw_before = change.get('before')
    raw_after = change.get('after')
    before = raw_before if isinstance(raw_before, str) else ''
    after = raw_after if isinstance(raw_after, str) else ''
    if (not before and not after) or before == after:
        return None
    field = {'title': 'title', 'set_language': 'language', 'close_task': 'status'}.get(edit_kind, edit_kind)
    return _text_field_diff(field, before, after, change)


def _merge_diff(row: dict, change: dict) -> ReviewChangeDiff | None:
    labels = _ref_labels(change)
    if len(labels) < 2:
        labels = _content_labels(row.get('before'))
    if len(labels) < 2 and isinstance(change.get('before'), str) and ' + ' in change['before']:
        labels = [part.strip() for part in change['before'].split(' + ') if part.strip()]
    if len(labels) < 2:
        return None
    after = change.get('after') if isinstance(change.get('after'), str) else ''
    edit = row.get('memory_edit')
    if not after and isinstance(edit, dict) and isinstance(edit.get('content'), str):
        after = edit['content']
    if not after:
        after = labels[0]
    return _finish(
        change,
        field='merge',
        before=' + '.join(_flat(label, _DIFF_LABEL) for label in labels[:8]),
        after=after,
        occurrences=len(labels),
        target_label=labels[0],
    )


def _text_field_diff(field: str, before: str, after: str, change: dict) -> ReviewChangeDiff | None:
    if len(before) <= _DIFF_TEXT and len(after) <= _DIFF_TEXT:
        return _finish(change, field=field, before=before, after=after, occurrences=1)
    spans = _changed_spans(before, after)
    if not spans:
        return None
    source, dest, start, end, after_start, after_end = spans[0]
    span, context_before, context_after = _window(source, start, end)
    return _finish(
        change,
        field=field,
        before=span,
        after=dest[after_start:after_end],
        context_before=context_before,
        context_after=context_after,
        occurrences=len(spans),
    )


def _finish(change: dict, **payload) -> ReviewChangeDiff | None:
    before = _clip(
        payload.get('before') or '',
        _DIFF_SPAN if payload.get('context_before') or payload.get('context_after') else _DIFF_TEXT,
    )
    after = _clip(
        payload.get('after') or '',
        _DIFF_SPAN if payload.get('context_before') or payload.get('context_after') else _DIFF_TEXT,
    )
    if not before and not after:
        return None
    body: dict[str, Any] = {
        'field': _flat(str(payload.get('field') or 'change'), 64),
        'before': before,
        'after': after,
        'context_before': _clip(payload.get('context_before') or '', _DIFF_CONTEXT),
        'context_after': _clip(payload.get('context_after') or '', _DIFF_CONTEXT),
        'occurrences': max(1, min(int(payload.get('occurrences') or 1), 10000)),
        'target_label': _flat(payload.get('target_label') or _target_label(change), _DIFF_LABEL),
        'source_title': _flat(_source_title(change), 200),
        'group_key': _group_key(str(payload.get('field') or 'change'), before, after),
    }
    started = _source_started(change)
    if started is not None:
        body['source_started_at'] = started
    body = {key: value for key, value in body.items() if value not in (None, '')}
    return parse_payload_strict(ReviewChangeDiff, body, document_path='review_changes/diff')


def _changed_spans(before: str, after: str):
    """One linear edit span. Sequence matching is quadratic and splits tokens."""
    if before == after:
        return []
    prefix = 0
    limit = min(len(before), len(after))
    while prefix < limit and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < len(before) - prefix and suffix < len(after) - prefix and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1
    return [(before, after, prefix, len(before) - suffix, prefix, len(after) - suffix)]


def _window(text: str, start: int, end: int):
    end = min(len(text), max(start, end))
    start = max(0, min(start, end))
    if end - start > _DIFF_SPAN:
        end = start + _DIFF_SPAN
    return text[start:end], text[max(0, start - _DIFF_CONTEXT) : start], text[end : end + _DIFF_CONTEXT]


def _context_texts(change: dict) -> list[str]:
    context = change.get('context')
    if not isinstance(context, dict) or not isinstance(context.get('segments'), list):
        return []
    texts = []
    for segment in context['segments']:
        if isinstance(segment, dict) and isinstance(segment.get('text'), str):
            texts.append(segment['text'])
    return texts


def _main_text(change: dict, texts: list[str], term: str):
    context = _as_dict(change.get('context'))
    index = context.get('main_index')
    if isinstance(index, int) and 0 <= index < len(texts) and _count_term(texts[index], term):
        return texts[index]
    return None


def _term_pattern(term: str):
    return re.compile(r'(?<!\w)' + re.escape(term) + r'(?!\w)')


def _count_term(text: str, term: str) -> int:
    if not text or not term:
        return 0
    return len(_term_pattern(term).findall(text))


def _locate(text: str, term: str):
    match = _term_pattern(term).search(text)
    if match is None:
        return None
    return match.start(), match.end()


def _state_text(state):
    if not isinstance(state, dict) or state.get('present') is not True:
        return None
    value = state.get('value')
    return value if isinstance(value, str) else None


def _ref_labels(change: dict) -> list[str]:
    refs = change.get('refs')
    if not isinstance(refs, list):
        return []
    labels = []
    for ref in refs:
        if isinstance(ref, dict) and isinstance(ref.get('label'), str) and ref['label'].strip():
            labels.append(ref['label'].strip())
    return labels


def _content_labels(value) -> list[str]:
    rows = value if isinstance(value, list) else []
    if isinstance(value, dict):
        rows = [row for row in value.values() if isinstance(row, dict)]
    labels = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get('content'), str) and row['content'].strip():
            labels.append(row['content'].strip())
    return labels


def _target_label(change: dict) -> str:
    labels = _ref_labels(change)
    if labels:
        return labels[0]
    return _source_title(change)


def _source_title(change: dict) -> str:
    context = change.get('context')
    if isinstance(context, dict) and isinstance(context.get('conversation_title'), str):
        return context['conversation_title']
    return ''


def _source_started(change: dict):
    context = change.get('context')
    if not isinstance(context, dict):
        return None
    value = context.get('conversation_date')
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _group_key(field: str, before: str, after: str) -> str:
    token = '|'.join([_flat(field, 32), _flat(before, 80).casefold(), _flat(after, 80).casefold()])
    if len(token) <= 128:
        return token
    return _flat(field, 32) + '|' + hashlib.sha256(token.encode()).hexdigest()[:32]


def _clip(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    text = value.replace('\x00', '')
    return text if len(text) <= limit else text[:limit]


def _flat(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    return _clip(' '.join(value.split()), limit)
