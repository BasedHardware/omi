"""Owner-scoped, decrypted reads; references and visibility stay authoritative."""

from datetime import datetime, timezone

from fastapi import HTTPException
from database import review_store
from database import conversations, action_items, users, candidates, dream_store
from utils.dream_prompt import fits_triage
from utils.dream_context import EvidenceRecords, add_context, context_candidates
from utils.entity_pages import _facts, resolve_entity  # pyright: ignore[reportPrivateUsage]
from utils.memory.canonical_memory_adapter import read_canonical_memory_item, memory_item_to_memorydb
from utils.memory.memory_service import MemoryService
from models.product_memory import MemoryAccessPolicy
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from database.task_intelligence_control import get_task_workflow_control

READ_COLLECTIONS = {
    'conversations',
    'memory_items',
    'memories',
    'action_items',
    'people',
    'knowledge_nodes',
    'workstreams',
    'candidates',
}


def read_record(uid, ref):
    collection, separator, key = ref.partition('/')
    if not separator or '/' in key or not key or collection not in READ_COLLECTIONS:
        raise ValueError('Invalid dream read reference')
    if collection == 'conversations':
        row = next(iter(conversations.get_conversations_by_id_without_photos(uid, [key])), None)
        return row if row and conversations.is_visible_conversation(row) and not row.get('is_locked') else None
    if collection in {'memories', 'memory_items'}:
        canonical = read_canonical_memory_item(uid, key)
        if canonical and not filter_canonical_default_visible_items(
            [canonical],
            policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
            now=datetime.now(timezone.utc),
        ):
            return None
        row = memory_item_to_memorydb(canonical) if canonical else MemoryService().fetch(uid, key)
        if row.is_locked or row.user_review is False or row.visibility != 'private':
            return None
        return row.model_dump(mode='python')
    if collection == 'action_items':
        row = action_items.get_action_item(uid, key)
        generation = get_task_workflow_control(uid).account_generation
        return row if row and row.get('account_generation', 0) == generation and not row.get('deleted') else None
    if collection == 'candidates':
        row = candidates.get_candidate(uid, key)
        if (
            row
            and row.account_generation == get_task_workflow_control(uid).account_generation
            and row.status.value == 'pending'
        ):
            return row.model_dump(mode='python')
        return None
    if collection == 'people':
        return users.get_person(uid, key)
    if collection in {'knowledge_nodes', 'workstreams'}:
        return resolve_entity(uid, key)
    return None


def read_entity_record(uid, entity_id):
    node = resolve_entity(uid, entity_id)
    facts, decisions, _ = _facts(uid, [node['entity_id']], {})
    return {
        **node,
        'facts': [f.model_dump(mode='python') for f in facts],
        'decisions': [f.model_dump(mode='python') for f in decisions],
    }


def read_changes(uid, lease, caps, vocabulary=None):
    dirty = dream_store.dirty_refs(uid, limit=dream_store.WRITE_CHUNK)
    records = EvidenceRecords()
    consumed = []
    for snapshot in dirty:
        if len(records.targets) >= 4:
            break
        item = snapshot.to_dict()
        # An update after admission belongs to a later pass, even if observed now.
        if item['last_changed_at'] > lease['started_at']:
            continue
        ref = f"{item['collection']}/{item['id']}"
        try:
            row = read_record(uid, ref)
        except review_store.ReviewNotFound:
            row = None
        except HTTPException as exc:
            if exc.status_code not in {402, 404}:
                raise
            row = None
        if row:
            candidate = {**records, ref: row}
            if not fits_triage(candidate, caps, vocabulary):
                break
            records[ref] = row
            records.targets.add(ref)
        consumed.append(item)
    records = add_context(
        records,
        context_candidates(
            uid, records, vocabulary or [], read_record=read_record, read_entity_record=read_entity_record
        ),
        caps,
        vocabulary,
    )
    return records, consumed
