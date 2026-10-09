"""Owner-scoped, decrypted reads; references and visibility stay authoritative."""

from datetime import datetime, timezone

from fastapi import HTTPException
from database import review_store
from database import conversations, action_items, users, candidates, screen_activity, dream_store
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
        row = conversations.get_conversation(uid, key)
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


def read_changes(uid, lease):
    events = dream_store.events(uid, lease)
    records = {}
    for event in events:
        for item in event['refs']:
            ref = f"{item['collection']}/{item['id']}"
            if ref in records:
                continue
            try:
                row = read_record(uid, ref)
            except review_store.ReviewNotFound:
                row = None
            except HTTPException as exc:
                if exc.status_code not in {402, 404}:
                    raise
                row = None
            if row:
                records[ref] = row
    # Only touched identities, never a full user history.
    identities = set()
    for ref, row in list(records.items()):
        if ref.startswith('conversations/'):
            for segment in row.get('transcript_segments') or []:
                if segment.get('person_id'):
                    identities.add('person:' + segment['person_id'])
        if row.get('subject_entity_id'):
            identities.add(row['subject_entity_id'])
        if row.get('workstream_id'):
            identities.add(row['workstream_id'])
    for entity_id in sorted(identities)[:20]:
        node = resolve_entity(uid, entity_id)
        facts, decisions, _ = _facts(uid, [node['entity_id']], {})
        records['entity/' + entity_id] = {
            **node,
            'facts': [f.model_dump(mode='python') for f in facts],
            'decisions': [f.model_dump(mode='python') for f in decisions],
        }
    if events:
        for row in screen_activity.get_screen_activity(
            uid, start_date=events[0]['at'], end_date=lease['started_at'], limit=30
        ):
            records['screen/' + row['id']] = row
    return records, (events[-1]['sequence'] if events else lease['watermark'])
