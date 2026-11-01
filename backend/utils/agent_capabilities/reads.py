"""Owner-scoped decrypted reads; no writes or fixed planner retrieval."""

from datetime import datetime, timezone
import copy
import zlib

from fastapi import HTTPException
from database import conversations, action_items, users, candidates
from utils.entity_pages import _facts, resolve_entity  # pyright: ignore[reportPrivateUsage]
from utils.memory.canonical_memory_adapter import read_canonical_memory_item, memory_item_to_memorydb
from utils.memory.memory_service import MemoryService
from models.product_memory import MemoryAccessPolicy, MemoryTier, MemoryItemStatus
from models.memory_evidence import SourceState
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from utils import dream_required_intake
from database.task_intelligence_control import get_task_workflow_control
from utils.agent_capabilities.errors import AgentRecordUnavailable


def read_required_intake_candidate(uid, ref, context):
    return dream_required_intake.read_candidate(uid, ref.split('/', 1)[1], context)


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

# Snippet and visibility fields only. Transcript bytes stay out of search hydration
# unless a speaker filter needs person ids or the capture has no title to show.
_CONVERSATION_PREVIEW_FIELDS = (
    'id',
    'created_at',
    'status',
    'discarded',
    'deleted',
    'dream_duplicate_of',
    'is_locked',
    'structured.title',
    'structured.overview',
    'user_title',
    'starred',
    'folder_user_set',
    'has_photos',
    'sync_relevance_user_kept',
    'relevance_decision',
)


class AgentTranscriptReadError(RuntimeError):
    """A stored speech blob cannot be verified; never mistake it for empty speech."""


def unavailable_is_transient(error=None):
    if error is None:
        return False
    if isinstance(error, HTTPException) and error.status_code in {402, 404}:
        return False
    if type(error) is ValueError and str(error) == 'Invalid dream read reference':
        return False
    return True


def search_hydration_unavailable(error):
    """A missing, hidden, or locked row is skipped during search hydration.

    HTTP 423 is the locked-conversation response from `read_record`. A direct
    read records that lock as transient so settlement can retry it.
    """
    if isinstance(error, HTTPException) and error.status_code == 423:
        return True
    return not unavailable_is_transient(error)


def read_record(uid, ref, *, control_cache=None, diagnostics=None, require_available=False):
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
            if require_available and conversations.is_visible_conversation(raw, include_discarded=True):
                raise AgentRecordUnavailable('Dream conversation temporarily hidden')
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
                raise ValueError('agent_transcript_shape')
        except (TypeError, ValueError, zlib.error) as exc:
            if diagnostics is not None:
                counts = diagnostics.setdefault('input_content_counts', {})
                counts['transcript_decode_failed'] = counts.get('transcript_decode_failed', 0) + 1
            raise AgentTranscriptReadError('Dream transcript unavailable') from exc
        row.setdefault('id', key)
        return row
    if collection in {'memories', 'memory_items'}:
        return _read_memory_record(uid, key, require_available=require_available)
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


def _read_memory_record(uid, key, *, require_available=False):
    """Owner-visible memory, with explicit temporary unavailability for Review.

    Review releases by default. Only the explicit terminal exclusions return None;
    ordinary retrieval continues to omit all unavailable rows.
    Store faults stay exceptions for every caller.
    """
    try:
        canonical = (
            read_canonical_memory_item(uid, key, include_inactive=True)
            if require_available
            else read_canonical_memory_item(uid, key)
        )
        if canonical:
            # This is the complete terminal allowlist for canonical memory evidence.
            if require_available and (
                canonical.status in {MemoryItemStatus.hidden, MemoryItemStatus.tombstoned}
                or canonical.source_state in {SourceState.tombstoned, SourceState.purged}
                or canonical.tier == MemoryTier.archive
                or (canonical.promotion or {}).get('user_review') is False
            ):
                return None
            policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
            now = datetime.now(timezone.utc)
            if not filter_canonical_default_visible_items([canonical], policy=policy, now=now):
                if require_available:
                    raise AgentRecordUnavailable('Dream memory temporarily unavailable')
                return None
        row = memory_item_to_memorydb(canonical) if canonical else MemoryService().fetch(uid, key)
    except HTTPException as exc:
        if require_available and exc.status_code == 402:
            raise AgentRecordUnavailable('Dream memory locked') from exc
        if not unavailable_is_transient(exc):
            return None
        raise
    if row.user_review is False:
        return None
    if row.visibility != 'private' or row.invalid_at is not None:
        if require_available:
            raise AgentRecordUnavailable('Dream memory temporarily unavailable')
        return None
    if row.is_locked:
        if require_available:
            raise AgentRecordUnavailable('Dream memory locked')
        return None
    return row.model_dump(mode='python')


def preview_record(uid, ref, *, need_speakers=False):
    """Bounded search hydration. Full records stay on `read_record`."""
    collection, separator, key = ref.partition('/')
    if not need_speakers and separator and key and '/' not in key and collection == 'conversations':
        raw = conversations.get_conversation_raw_snapshot(uid, key, field_paths=list(_CONVERSATION_PREVIEW_FIELDS))
        if not raw or not conversations.is_visible_conversation(raw) or raw.get('is_locked'):
            return None
        stored = raw.get('structured')
        structured = stored if isinstance(stored, dict) else {}
        title = structured.get('title') or ''
        overview = structured.get('overview') or ''
        user_title = raw.get('user_title') or ''
        if title or overview or user_title:
            return {
                'id': key,
                'created_at': raw.get('created_at'),
                'user_title': user_title or None,
                'structured': {'title': title, 'overview': overview},
            }
    return read_record(uid, ref)


def read_entity_record(uid, entity_id):
    node = resolve_entity(uid, entity_id)
    facts, decisions, _ = _facts(uid, [node['entity_id']], {})
    return {
        **node,
        'facts': [f.model_dump(mode='python') for f in facts],
        'decisions': [f.model_dump(mode='python') for f in decisions],
    }
