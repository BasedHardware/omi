"""Owner-scoped, decrypted reads; references and visibility stay authoritative."""

from datetime import datetime, timezone
import copy
import json
import zlib

from fastapi import HTTPException
from database import review_store
from database import conversations, action_items, users, candidates, dream_store
from utils.dream_prompt import (
    fits_triage,
    context_reserve,
    triage_budget,
    evidence_message,
    mount,
    TRIAGE_INSTRUCTIONS,
    text,
    conversation_summary,
)
from utils.dream_transport import input_ceiling
from models.dream_agent import Triage
from utils.dream_context import EvidenceRecords, add_context, context_candidates
from utils.dream_context import fits_pass, REASONING_TARGET_LIMIT, CONTEXT_TARGET_LIMIT, query_content
from utils.dream_diagnostics import initialize
from utils.dream_guards import timestamp
from utils.observability.fallback import record_fallback
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


def cached_reader(diagnostics=None):
    cache, control_cache = {}, {}

    def read(ref_uid, ref):
        if ref not in cache:
            cache[ref] = read_record(ref_uid, ref, control_cache=control_cache, diagnostics=diagnostics)
        return cache[ref]

    return read


def record_budget_counts(records, caps, vocabulary, diagnostics):
    counts = diagnostics['context_budget_counts']
    try:
        message = evidence_message(records, Triage, triage_budget(caps), vocabulary=vocabulary)
        payload = json.loads(message[0]['content'])
        counts['triage_input_bytes'] = input_ceiling(
            mount(Triage, triage_budget(caps), TRIAGE_INSTRUCTIONS).messages(message), Triage.model_json_schema()
        )
        counts['target_excerpt_bytes'] = sum(
            len(value.encode()) for ref, value in payload['records'].items() if ref in records.targets
        )
        counts['context_excerpt_bytes'] = sum(
            len(value.encode()) for ref, value in payload['records'].items() if ref not in records.targets
        )
    except ValueError:
        counts.update(triage_input_bytes=0, target_excerpt_bytes=0, context_excerpt_bytes=0)


def retrieve_context(uid, records, caps, vocabulary=None, *, read=None, diagnostics=None, pending_refs=()):
    diagnostics = initialize({} if diagnostics is None else diagnostics)
    original = records
    budget_counts = diagnostics['context_budget_counts']
    budget_counts.update(
        supplied_targets=len(original.targets),
        reserved_triage_bytes=context_reserve(caps),
        target_triage_limit_bytes=triage_budget(caps) - context_reserve(caps),
    )
    for ref, row in original.items():
        if not ref.startswith('conversations/'):
            continue
        shape = diagnostics['input_content_counts']
        structured = row.get('structured') or {}
        shape['conversations'] += 1
        shape['with_title'] += bool(text(row.get('user_title')) or text(structured.get('title')))
        shape['with_overview'] += bool(text(structured.get('overview')))
        shape['with_sections_text'] += bool(conversation_summary({**row, 'structured': {**structured, 'overview': ''}}))
        has_speech = any(text(segment.get('text')) for segment in row.get('transcript_segments') or [])
        shape['with_transcript_text'] += has_speech
        shape['empty_transcript' if 'transcript_segments' in row else 'missing_transcript'] += not has_speech
        shape['query_content_empty'] += not bool(query_content(row).strip())
    # Supplied dry-run records obey the same target reservation as queue reads.
    selected = EvidenceRecords({ref: row for ref, row in original.items() if ref not in original.targets}, targets=())
    for ref in original:
        if ref not in original.targets:
            continue
        candidate = EvidenceRecords({**selected, ref: original[ref]}, targets=selected.targets | {ref})
        targets_only = EvidenceRecords({key: value for key, value in candidate.items() if key in candidate.targets})
        if len(candidate.targets) > CONTEXT_TARGET_LIMIT or not fits_triage(
            targets_only, caps, vocabulary, reserve_context=True
        ):
            break
        selected = candidate
    if not selected.targets and original.targets:
        first = next(ref for ref in original if ref in original.targets)
        selected = EvidenceRecords({**selected, first: original[first]}, targets={first})
    records = selected
    seeds = set(records.targets)
    diagnostics['target_context_counts'].update(retrieval_seeded=len(seeds), contextless=len(records.targets - seeds))
    read = cached_reader(diagnostics) if read is None else read
    # Shared with the lazy candidate generator so earlier-tier admissions also
    # stop occupying later temporal output slots.
    excluded = set(original)
    records = add_context(
        records,
        context_candidates(
            uid,
            EvidenceRecords(records, targets=seeds),
            vocabulary or [],
            read_record=read,
            read_entity_record=read_entity_record,
            diagnostics=diagnostics,
            excluded_refs=excluded,
            pending_refs=pending_refs,
        ),
        caps,
        vocabulary,
        diagnostics=diagnostics,
        excluded_refs=excluded,
        reserve_context=True,
    )
    kept = bool(
        set(records) - records.targets
        or budget_counts['visible_found']
        or any(counts['budget_skipped'] for counts in diagnostics['retrieval_counts'].values())
    )
    budget_counts['reservation_kept'] = int(kept)
    if not kept:
        budget_counts['slice_reclaimed'] = 1
        # Only an empty/unavailable neighbourhood releases the target slice.
        for ref in original:
            if ref not in original.targets or ref in records.targets:
                continue
            candidate = EvidenceRecords({**records, ref: original[ref]}, targets=records.targets | {ref})
            if len(candidate.targets) > REASONING_TARGET_LIMIT or not fits_triage(candidate, caps, vocabulary):
                break
            records = candidate
    budget_counts['targets_deferred'] = len(original.targets - records.targets)
    diagnostics['target_context_counts']['contextless'] = len(records.targets - seeds)
    record_budget_counts(records, caps, vocabulary, diagnostics)
    return records


def read_changes(uid, lease, caps, vocabulary=None, *, diagnostics=None, unavailable=None):
    unavailable = [] if unavailable is None else unavailable
    diagnostics = initialize({} if diagnostics is None else diagnostics)
    counts = diagnostics['dirty_counts']
    read = cached_reader(diagnostics)

    dirty = dream_store.dirty_refs(uid, limit=dream_store.DIRTY_INSPECTION_LIMIT, newest=False)[
        : dream_store.DIRTY_INSPECTION_LIMIT
    ]
    records = EvidenceRecords()
    consumed = []
    assessed = {}
    paused = set()
    counts['fetched'] = len(dirty)

    def admit(snapshot, *, reserve_context=False):
        nonlocal records
        item = snapshot.to_dict()
        deferred_until = timestamp(item.get('deferred_until'))
        if deferred_until and lease['started_at'] < deferred_until:
            paused.add(f"{item['collection']}/{item['id']}")
            return 'deferred'
        # An update after admission belongs to a later pass, even if observed now.
        if item['last_changed_at'] > lease['started_at']:
            counts['newer'] += 1
            return 'newer'
        ref = f"{item['collection']}/{item['id']}"
        if ref not in assessed:
            counts['attempted'] += 1
            transient = False
            try:
                assessed[ref] = read(uid, ref)
            except review_store.ReviewNotFound:
                assessed[ref] = None
            except DreamTranscriptReadError:
                counts['failed'] += 1
                assessed[ref] = None
                transient = True
                record_fallback(
                    component='other', from_mode='none', to_mode='none', reason='malformed_doc', outcome='degraded'
                )
            except HTTPException as exc:
                if exc.status_code not in {402, 404, 423}:
                    counts['failed'] += 1
                    raise
                assessed[ref] = None
                transient = exc.status_code in {402, 423}
            except Exception:
                counts['failed'] += 1
                raise
            counts['found' if assessed[ref] else 'unavailable'] += 1
            if not assessed[ref]:
                counts['transient' if transient else 'permanent'] += 1
                unavailable.append({**item, 'transient': transient})
        row = assessed[ref]
        if not row:
            # Settlement independently fences permanent misses and bounds
            # retries for 402/locked/unverifiable versions; none is model evidence.
            return 'unavailable'
        candidate = EvidenceRecords({**records, ref: row}, targets=records.targets | {ref})
        has_context = len(candidate) > len(candidate.targets)
        if not fits_triage(candidate, caps, vocabulary, reserve_context=reserve_context) or (
            has_context and not fits_pass(candidate, caps, vocabulary)
        ):
            return 'budget'
        records = candidate
        consumed.append(item)
        counts['admitted'] += 1
        return 'admitted'

    # Four is an initial neighbourhood seed allocation, never a final target cap.
    position = 0
    while position < len(dirty) and len(records.targets) < 4:
        if admit(dirty[position], reserve_context=True) == 'budget':
            break
        position += 1
    # Potential targets 5–8 have not been hydrated/admitted yet. Exclude the
    # bounded pending queue window from temporal selection before those reads;
    # exclusion itself neither consumes a version nor adds a product read.
    pending = {
        f"{item['collection']}/{item['id']}"
        for snapshot in dirty[position:]
        if (item := snapshot.to_dict())['last_changed_at'] <= lease['started_at']
    } | paused
    records = retrieve_context(uid, records, caps, vocabulary, read=read, diagnostics=diagnostics, pending_refs=pending)
    initial_consumed = len(consumed)
    consumed = [item for item in consumed if f"{item['collection']}/{item['id']}" in records.targets]
    dropped_initial = initial_consumed - len(consumed)
    counts['admitted'] = len(consumed)
    # Return unspent neighbourhood capacity to dirty targets. Only admitted
    # target versions are consumed; unavailable versions settle separately.
    while (
        not diagnostics['context_budget_counts']['reservation_kept']
        and position < len(dirty)
        and len(records.targets) < REASONING_TARGET_LIMIT
    ):
        if admit(dirty[position]) == 'budget':
            counts['budget_deferred'] = len(dirty) - position
            break
        position += 1
    counts['budget_deferred'] = len(dirty) - position + dropped_initial
    diagnostics['target_context_counts']['contextless'] = max(
        0, len(records.targets) - diagnostics['target_context_counts']['retrieval_seeded']
    )
    record_budget_counts(records, caps, vocabulary, diagnostics)
    return records, consumed
