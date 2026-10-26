"""Historical required submissions enter Dream as hidden admission candidates.

Normal owner reads stay unchanged. The ordinary Dream planner and independent
verifiers compare candidates with fully read semantic neighbors. Only a
verified resolution may normalize a unique item or retain a duplicate's source
as a superseded audit row. No old submission is made visible to seek duplicates.
"""

from datetime import datetime, timezone
import json
from functools import partial
import time
from typing import Any, Literal, cast
from google.cloud import firestore

from config import required_memory_intake as policy
from database import review_store
from database.memory_apply_store import apply_long_term_patch_firestore
from database.memory_collections import MemoryCollections
from database.dream_effect_fence import assert_active
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.required_intake_fence import source_scope, RequiredIntakeSourceChanged
from models.agent_refs import base_ref
from models.agent_tools import Search
from models.memory_apply import ApplyStatus, MemoryControlState, build_patch_mutation_identity
from models.memory_contracts import deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from utils.executors import db_executor, run_blocking
from utils.memory import canonical_required_processing as required
from utils.memory.canonical_memory_adapter import read_canonical_memory_item, memory_item_to_memorydb
from utils.memory.required_intake import bounded_normalize, result_guard
from utils.memory.required_source_admission import source_revisions

MARKER = 'required_intake_candidate'


def read_control(uid, client):
    raw = client.document(MemoryCollections(uid=uid).memory_apply_control_state).get().to_dict()
    return MemoryControlState.model_validate(raw) if raw else None


def save_cursor(uid, before, visited):
    client = review_store.client()
    ref = client.document(f'{MemoryCollections(uid=uid).memory_runs}/dream_required_intake_cursor')

    @firestore.transactional
    def commit(tx):
        assert_active(uid, tx)
        current = ref.get(transaction=tx).to_dict() or None
        if current == before:
            tx.set(ref, visited)

    run_with_transaction_contention_retry(client.transaction, commit, operation_name='dream_required_intake_cursor')


def read_candidate(uid, memory_id, context):
    if not policy.backlog_enabled(uid):
        return None
    item = read_canonical_memory_item(uid, memory_id, db_client=review_store.client())
    if item is None or not item.content or item.uid != uid or item.captured_at >= policy.BACKLOG_CUTOFF:
        return None
    if not required.is_pending_required_processing(item) or item.source_state.value != 'active':
        return None
    revisions = source_revisions(uid, item, db_client=review_store.client())
    if revisions is None:
        return None
    row = memory_item_to_memorydb(item).model_dump(mode='python')
    if row.get('is_locked') or row.get('visibility') != 'private' or row.get('user_review') is False:
        return None
    return {
        **row,
        MARKER: {
            **context,
            'item_revision': item.item_revision,
            'content_hash': item.content_hash,
            'source_subject_id': item.subject_entity_id,
            'source_scope': item.subject_scope.value,
            'source_revisions': revisions,
        },
    }


async def prepare(uid, seed, records, limits, source):
    """Bounded, read-only candidates and neighbors in the existing pass budget."""
    if not policy.backlog_enabled(uid):
        return seed, records
    client = review_store.client()
    control = await run_blocking(db_executor, read_control, uid, client)
    if control is None or control.writer_mode.value != 'compatibility':
        return seed, records
    cursor_ref = client.document(f'{MemoryCollections(uid=uid).memory_runs}/dream_required_intake_cursor')
    cursor = cursor_ref.get().to_dict() or None
    if cursor and (
        set(cursor) != {'captured_at', 'memory_id'}
        or not isinstance(cursor['captured_at'], datetime)
        or not isinstance(cursor['memory_id'], str)
    ):
        raise ValueError('required_intake_cursor_invalid')
    items = await run_blocking(
        db_executor,
        required.list_pending_required_processing_items,
        uid,
        db_client=client,
        limit=required.MAX_REQUIRED_PROCESSING_QUERY_SCAN,
        captured_before=policy.BACKLOG_CUTOFF,
        cursor=cursor,
    )
    if not items and cursor:
        items = await run_blocking(
            db_executor,
            required.list_pending_required_processing_items,
            uid,
            db_client=client,
            limit=required.MAX_REQUIRED_PROCESSING_QUERY_SCAN,
            captured_before=policy.BACKLOG_CUTOFF,
        )
    # Keep imports acyclic: session owns serialized-size accounting.
    additions = {}
    candidates = []
    embedding_tokens = 0
    visited = None
    attempted = 0
    for item in items:
        if attempted >= policy.BACKLOG_ITEMS_PER_PASS:
            break
        visited = {'captured_at': item.captured_at, 'memory_id': item.memory_id}
        revisions = await run_blocking(db_executor, source_revisions, uid, item, db_client=client)
        if revisions is None:
            continue
        text = item.content or ''
        if not text or len(text) > 2000:
            continue
        attempted += 1
        neighbors = {}
        complete = True
        chunks = [text[offset : offset + 500] for offset in range(0, len(text), 500)]
        for mode, query in ((mode, chunk) for chunk in chunks for mode in ('semantic', 'lexical')):
            if mode == 'semantic':
                embedding_tokens += len(query.encode()) * 6
            page = await source.search(
                Search(
                    collections=['memory_items'], mode=cast(Literal['semantic', 'lexical'], mode), query=query, limit=8
                ),
                byte_budget=16000,
            )
            if not page.get('complete') or page.get('unavailable_refs'):
                complete = False
                break
            for hit in page['results']:
                if hit['ref'] == 'memory_items/' + item.memory_id:
                    continue
                row = await source.read(hit['ref'])
                if row is None:
                    complete = False
                    break
                neighbors[hit['ref']] = row
        if not complete or len(neighbors) > 8:
            continue
        context = {
            'head_commit_id': control.head_commit_id,
            'account_generation': control.account_generation,
            'source_generation': control.source_generation,
            'dedupe_refs': sorted(neighbors),
            'search_complete': True,
        }
        row = await run_blocking(db_executor, read_candidate, uid, item.memory_id, context)
        if row is None:
            continue
        ref = 'memory_items/' + item.memory_id
        proposed = {**additions, **neighbors, ref: row}
        if _bytes({**records, **proposed}) > min(24000, limits.read_bytes // 2):
            break
        additions = proposed
        candidates.append(ref)
    if visited is not None:
        await run_blocking(db_executor, save_cursor, uid, cursor, visited)
    latest = await run_blocking(db_executor, read_control, uid, client)
    if latest is None or latest.head_commit_id != control.head_commit_id:
        seed = {**seed, 'required_intake_embedding_tokens': embedding_tokens}
        return seed, records
    records.update(additions)
    seed = {
        **seed,
        'targets': [*candidates, *seed.get('targets', [])],
        'required_intake_candidates': candidates,
        'required_intake_embedding_tokens': embedding_tokens,
    }
    return seed, records


def _bytes(value):
    # Avoid importing Session (which uses the capability registry).
    return len(json.dumps(value, default=str, ensure_ascii=False).encode())


def validate(edit, records, *, authority='dream'):
    row = records[base_ref(edit.target)]
    candidate = row.get(MARKER) or {}
    if authority != 'dream' or not candidate.get('search_complete') or not edit.target.startswith('memory_items/'):
        raise ValueError('required_intake_candidate_required')
    if edit.after or edit.before != row.get('content'):
        raise ValueError('required_intake_preserves_submission')
    if not set(candidate.get('dedupe_refs', [])).issubset(edit.evidence):
        raise ValueError('required_intake_cite_all_neighbors')
    if edit.target not in edit.evidence:
        raise ValueError('required_intake_cite_submission')
    if edit.other:
        other = records.get(base_ref(edit.other))
        if edit.other not in candidate['dedupe_refs'] or not other or MARKER in other:
            raise ValueError('required_intake_survivor_required')
        subject = candidate.get('source_subject_id')
        same_subject = (
            other.get('subject_entity_id') == subject
            if subject
            else (candidate.get('source_scope') == 'primary_user' and other.get('subject_entity_id') == 'user')
        )
        if row.get('visibility') != other.get('visibility') or not same_subject:
            raise ValueError('required_intake_subject_mismatch')


def apply(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    try:
        with source_scope(uid, (row.get(MARKER) or {}).get('source_revisions', {})):
            return _apply(uid, edit, records, change, key, row, expected_records=expected_records, authority=authority)
    except RequiredIntakeSourceChanged as error:
        raise review_store.ReviewConflict('Required intake source changed') from error


def _apply(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    del change, expected_records
    validate(edit, records, authority=authority)
    if not policy.backlog_enabled(uid):
        raise ValueError('required_intake_backlog_disabled')
    client = review_store.client()
    context = row[MARKER]
    current = read_candidate(uid, edit.target.split('/', 1)[1], context)
    if current != row:
        raise review_store.ReviewConflict('Required intake candidate changed')
    item = read_canonical_memory_item(uid, row['id'], db_client=client)
    if item is None:
        raise review_store.ReviewConflict('Required intake unavailable')
    control = read_control(uid, client)
    if control is None or (control.head_commit_id, control.account_generation, control.source_generation) != (
        context['head_commit_id'],
        context['account_generation'],
        context['source_generation'],
    ):
        raise review_store.ReviewConflict('Required intake dedupe snapshot changed')
    if not edit.other:
        outcome = required.process_required_memory_item(
            uid,
            item.memory_id,
            db_client=client,
            processor=partial(bounded_normalize, deadline=time.monotonic() + policy.INLINE_TIMEOUT_SECONDS),
            result_guard=partial(result_guard, time.monotonic() + policy.INLINE_TIMEOUT_SECONDS),
            expected_head_commit_id=control.head_commit_id,
        )
        if not outcome.processed:
            raise review_store.ReviewConflict('Required intake deferred')
        return 'applied'
    audit = dict(item.promotion or {})
    audit['required_intake_resolution'] = {
        'kind': 'dream_verified_duplicate',
        'survivor_id': edit.other.split('/', 1)[1],
        'source_revision': item.item_revision,
        'edit_key': key,
        'resolved_at': datetime.now(timezone.utc).isoformat(),
    }
    # Retain the original content, evidence and all historical ledger versions.
    logical: dict[str, Any] = {
        'decision': 'update',
        'target_memory_id': item.memory_id,
        'result_status': 'superseded',
    }
    evidence_ids = [ev.evidence_id for ev in item.evidence]
    payload = {
        **logical,
        'evidence_ids': evidence_ids,
        'expected_item_revision': item.item_revision,
        'expected_content_hash': item.content_hash,
        'promotion_audit': audit,
    }
    payload['mutation_metadata'] = build_patch_mutation_identity(payload)
    logical['mutation_metadata'] = payload['mutation_metadata']
    identity = deterministic_contract_id('dream-required-intake-dedupe', {'key': key, 'revision': item.item_revision})
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.synthesis,
        source_packet_id='required_intake:' + identity,
        target_memory_id=item.memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        proposed_operation=operation,
        patch_payload={
            **payload,
            'patch_id': identity,
            'packet_id': identity,
            'run_id': identity,
            'idempotency_key': identity,
            'observed_head_commit_id': control.head_commit_id,
        },
        db_client=client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise review_store.ReviewConflict('Required intake duplicate changed')
    return 'applied'
