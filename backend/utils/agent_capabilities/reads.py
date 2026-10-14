"""Owner-scoped decrypted reads; no writes or fixed planner retrieval."""

from datetime import datetime, timezone
import copy
import zlib

from fastapi import HTTPException
from database import conversations, action_items, users, candidates
from utils.dream_diagnostics import initialize
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


class DreamTranscriptReadError(RuntimeError):
    """A stored speech blob cannot be verified; never mistake it for empty speech."""


def unavailable_is_transient(error=None):
    if error is None:
        return False
    if isinstance(error, HTTPException) and error.status_code in {402, 404}:
        return False
    if type(error) is ValueError and str(error) == 'Invalid dream read reference':
        return False
    return True


def read_record(uid, ref, *, control_cache=None, diagnostics=None):
    control_cache = {} if control_cache is None else control_cache
    collection, separator, key = ref.partition('/')
    if not separator or '/' in key or not key or collection not in READ_COLLECTIONS:
        raise ValueError('Invalid dream read reference')
    if collection == 'conversations':
        # One full owner-scoped document read, no photo subcollection and no
        # metadata projection. Verify the blob before the tolerant product
        # decoder can silently replace corrupt/wrong-key speech with [].
        raw = conversations.get_conversation_raw_snapshot(uid, key)
        if not raw or not conversations.is_visible_conversation(raw):
            return None
        if raw.get('is_locked'):
            raise HTTPException(423, 'Dream record locked')
        try:
            conversations.decode_transcript_segments_verified(
                uid,
                copy.deepcopy(raw.get('transcript_segments') or []),
                bool(raw.get('transcript_segments_compressed')),
            )
            row = conversations.prepare_conversation_for_read(raw, uid)
            if row is None or not isinstance(row.get('transcript_segments', []), list):
                raise ValueError('dream_transcript_shape')
        except (TypeError, ValueError, zlib.error) as exc:
            if diagnostics is not None:
                initialize(diagnostics)['input_content_counts']['transcript_decode_failed'] += 1
            raise DreamTranscriptReadError('Dream transcript unavailable') from exc
        row.setdefault('id', key)
        return row
    if collection in {'memories', 'memory_items'}:
        canonical = read_canonical_memory_item(uid, key)
        if canonical and not filter_canonical_default_visible_items(
            [canonical],
            policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
            now=datetime.now(timezone.utc),
        ):
            return None
        row = memory_item_to_memorydb(canonical) if canonical else MemoryService().fetch(uid, key)
        if row.user_review is False or row.visibility != 'private' or row.invalid_at is not None:
            return None
        if row.is_locked:
            raise HTTPException(423, 'Dream record locked')
        return row.model_dump(mode='python')
    if collection in {'action_items', 'candidates'}:
        if 'generation' not in control_cache:
            control_cache['generation'] = get_task_workflow_control(uid).account_generation
    if collection == 'action_items':
        row = action_items.get_action_item(uid, key)
        generation = control_cache['generation']
        return row if row and row.get('account_generation', 0) == generation and not row.get('deleted') else None
    if collection == 'candidates':
        row = candidates.get_candidate(uid, key)
        if row and row.account_generation == control_cache['generation'] and row.status.value == 'pending':
            return row.model_dump(mode='python')
        return None
    if collection == 'people':
        row = users.get_person(uid, key)
        return {**row, 'entity_id': 'person:' + key, 'type': 'person'} if row else None
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
