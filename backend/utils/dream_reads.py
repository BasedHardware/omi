"""Owner-scoped, decrypted reads; references and visibility stay authoritative."""

from datetime import datetime, timezone

from fastapi import HTTPException
from database import review_store
from database import conversations, action_items, users, candidates, dream_store
from utils.dream_prompt import fits_triage
from utils.dream_context import EvidenceRecords, add_context, context_candidates
from utils.dream_context import fits_pass, REASONING_TARGET_LIMIT
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


def read_record(uid, ref, *, control_cache=None):
    control_cache = {} if control_cache is None else control_cache
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


def cached_reader():
    cache, control_cache = {}, {}

    def read(ref_uid, ref):
        if ref not in cache:
            cache[ref] = read_record(ref_uid, ref, control_cache=control_cache)
        return cache[ref]

    return read


def retrieve_context(uid, records, caps, vocabulary=None, *, read=None, diagnostics=None):
    read = cached_reader() if read is None else read
    return add_context(
        records,
        context_candidates(
            uid,
            records,
            vocabulary or [],
            read_record=read,
            read_entity_record=read_entity_record,
            diagnostics=diagnostics,
        ),
        caps,
        vocabulary,
        diagnostics=diagnostics,
    )


def read_changes(uid, lease, caps, vocabulary=None, *, diagnostics=None):
    diagnostics = initialize({} if diagnostics is None else diagnostics)
    counts = diagnostics['dirty_counts']
    read = cached_reader()

    dirty = dream_store.dirty_refs(uid, limit=dream_store.DIRTY_LIMIT)
    records = EvidenceRecords()
    consumed = []
    assessed = {}
    counts['fetched'] = len(dirty)

    def admit(snapshot):
        nonlocal records
        item = snapshot.to_dict()
        # An update after admission belongs to a later pass, even if observed now.
        if item['last_changed_at'] > lease['started_at']:
            counts['newer'] += 1
            return 'newer'
        ref = f"{item['collection']}/{item['id']}"
        if ref not in assessed:
            counts['attempted'] += 1
            try:
                assessed[ref] = read(uid, ref)
            except review_store.ReviewNotFound:
                assessed[ref] = None
            except HTTPException as exc:
                if exc.status_code not in {402, 404}:
                    counts['failed'] += 1
                    raise
                assessed[ref] = None
            except Exception:
                counts['failed'] += 1
                raise
            counts['found' if assessed[ref] else 'unavailable'] += 1
        row = assessed[ref]
        if not row:
            # A transient visibility/entitlement gap must not acknowledge a
            # product version that never entered the model's evidence.
            return 'unavailable'
        candidate = EvidenceRecords({**records, ref: row}, targets=records.targets | {ref})
        has_context = len(candidate) > len(candidate.targets)
        if not fits_triage(candidate, caps, vocabulary) or (has_context and not fits_pass(candidate, caps, vocabulary)):
            return 'budget'
        records = candidate
        consumed.append(item)
        counts['admitted'] += 1
        return 'admitted'

    # Four is an initial neighbourhood seed allocation, never a final target cap.
    position = 0
    while position < len(dirty) and len(records.targets) < 4:
        if admit(dirty[position]) == 'budget':
            break
        position += 1
    records = retrieve_context(uid, records, caps, vocabulary, read=read, diagnostics=diagnostics)
    # Return unspent neighbourhood capacity to dirty targets. Only admitted
    # versions are acknowledged; budget-deferred/unavailable refs stay queued.
    while position < len(dirty) and len(records.targets) < REASONING_TARGET_LIMIT:
        if admit(dirty[position]) == 'budget':
            counts['budget_deferred'] = len(dirty) - position
            break
        position += 1
    counts['budget_deferred'] = len(dirty) - position
    return records, consumed
