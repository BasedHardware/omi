"""Write-time admission, leased retries and hidden historical dedupe, offline."""

from datetime import datetime, timedelta, timezone
import asyncio
import json
import logging
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import required_memory_intake as policy
from database import memory_apply_store, review_store, dream_scheduler
from models.agent_edit import DreamHarnessEdit as HarnessEdit
from models.agent_edit import HarnessEdit as ReleasedHarnessEdit
from models.agent_tools import tool_model, tool_schemas
from utils.agent_capabilities.session import Session
from database import review_changes
from models.memory_apply import ApplyStatus, MemoryControlState, memory_content_hash
from models.memory_evidence import MemoryEvidence
from models.product_memory import MemoryItem
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_required_intake as backlog, dream_review_policy
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.limits import SessionLimits
from utils.memory import canonical_required_processing as processing, required_intake as intake
from utils.memory.promotion_flex import PromotionFlexDeferred
from utils.memory import required_source_admission as admission
from utils.memory import canonical_memory_adapter as adapter
from utils.memory import canonical_consolidation as consolidation
from utils.memory.required_promotion import required_processing_payload
from database.document_ids import document_id_from_seed
from database import required_intake_cursors
from database.required_intake_fence import RequiredIntakeSourceChanged
from utils import executors
from utils.memory.memory_system import CanonicalApplyStateUnavailable
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from concurrent.futures import ThreadPoolExecutor

UID = 'synthetic-required-intake-owner'
NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_inline_wait_releases_the_database_worker(db, monkeypatch):
    started = asyncio.Event()
    release = Event()
    loop = asyncio.get_running_loop()

    def slow_normalize(row):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(15)
        return normalized(row)

    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(executors, 'db_executor', pool)
        monkeypatch.setattr(intake, 'db_executor', pool)
        monkeypatch.setattr(processing, 'db_executor', pool)
        monkeypatch.setattr(intake, 'normalize', slow_normalize)
        capture = asyncio.create_task(executors.run_blocking(pool, intake.after_capture, UID, stored(db), db_client=db))
        try:
            await asyncio.wait_for(started.wait(), 10)
            assert await asyncio.wait_for(executors.run_blocking(pool, lambda: 'responsive'), 2) == 'responsive'
        finally:
            release.set()
            await capture
    assert stored(db).processing_state.value == 'processed'


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True])
async def test_async_create_response_and_prompt_cache_observe_normalized_content(db, monkeypatch, batch):
    service = MemoryService(db_client=db)
    monkeypatch.setattr(service, 'ensure_canonical_mutation_ready', lambda *a: None)
    monkeypatch.setattr(service, '_write_historical_overrides', lambda *a: None)
    cache_states = []
    monkeypatch.setattr(service, '_invalidate_prompt_cache', lambda uid: cache_states.append(stored(db).content))
    monkeypatch.setattr(
        intake,
        'normalize',
        lambda row: processing.ProcessedRequiredMemory(content='The owner prefers tea.', predicate='prefers'),
    )

    def committed_write(uid, payload):
        intake.after_capture(uid, stored(db), db_client=db)
        return 'new'

    monkeypatch.setattr(
        service,
        '_canonical',
        SimpleNamespace(
            write=committed_write, write_batch=lambda uid, rows: [committed_write(uid, row) for row in rows]
        ),
    )
    memory = adapter.memory_item_to_memorydb(stored(db))
    if batch:
        result = await executors.run_blocking(
            executors.db_executor,
            service.create_external_memory_batch,
            UID,
            [memory],
            memory_system=MemorySystem.CANONICAL,
            consumer='mcp',
            operation='synthetic',
        )
        result = result[0]
    else:
        result = await executors.run_blocking(
            executors.db_executor,
            service.create_external_memory,
            UID,
            memory,
            memory_system=MemorySystem.CANONICAL,
            consumer='mcp',
            operation='synthetic',
        )
    assert result.content == stored(db).content == 'The owner prefers tea.'
    assert cache_states[-1] == 'The owner prefers tea.'


def test_account_deletion_blocks_explicit_text_before_provider(db, monkeypatch):
    calls = []
    monkeypatch.setattr(intake, 'normalize', lambda row: calls.append(row.memory_id) or normalized(row))
    db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    assert intake.after_capture(UID, stored(db), db_client=db) is None
    with pytest.raises(CanonicalApplyStateUnavailable, match='account deletion'):
        processing.process_required_memory_item(UID, 'new', db_client=db, processor=intake.normalize)
    assert not calls and stored(db).processing_state.value == 'pending'


def test_deletion_after_control_read_is_fenced_before_provider_claim(db, monkeypatch):
    actual = processing._read_control_state
    calls = []

    def start_deleting(uid, **kwargs):
        control = actual(uid, **kwargs)
        db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
        return control

    monkeypatch.setattr(processing, '_read_control_state', start_deleting)
    monkeypatch.setattr(intake, 'normalize', lambda row: calls.append(row.memory_id) or normalized(row))
    result = intake.after_capture(UID, stored(db), db_client=db)
    assert result is not None and not result.attempted
    assert not calls and stored(db).processing_state.value == 'pending'


def start_deletion(database, kind):
    if kind == 'account':
        database.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    else:
        database.rows[('users', UID, 'memory_items', 'new')].update(
            status='tombstoned', source_state='tombstoned', processing_state='blocked', item_revision=2
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['account', 'memory'])
@pytest.mark.parametrize('phase', ['queued', 'in_flight'])
async def test_deletion_during_model_wait_wins(db, monkeypatch, kind, phase):
    loop = asyncio.get_running_loop()
    queued, started = asyncio.Event(), asyncio.Event()
    release = Event()
    calls = []

    class QueuedPool(ThreadPoolExecutor):
        submissions = 0

        def submit(self, fn, /, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            self.submissions += 1
            if self.submissions == (2 if phase == 'queued' else 1):
                loop.call_soon_threadsafe(queued.set)
            return future

    def normalize(row):
        calls.append(row.memory_id)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(20)
        return normalized(row)

    with QueuedPool(max_workers=1) as pool:
        blocker = pool.submit(release.wait, 20) if phase == 'queued' else None
        monkeypatch.setattr(processing, 'llm_executor', pool)
        monkeypatch.setattr(intake, 'normalize', normalize)
        task = asyncio.create_task(
            intake.after_capture_async(UID, stored(db), db_client=db, deadline=intake.time.monotonic() + 15)
        )
        try:
            await asyncio.wait_for((queued if phase == 'queued' else started).wait(), 10)
            start_deletion(db, kind)
        finally:
            release.set()
            result = await task
            if blocker is not None:
                blocker.result(timeout=2)
    assert calls == ([] if phase == 'queued' else ['new'])
    assert result is None or not result.processed
    assert stored(db).processing_state.value == ('pending' if kind == 'account' else 'blocked')
    assert not stored(db).promotion.get('admission_receipt')


@pytest.mark.parametrize('kind', ['account', 'memory'])
def test_deletion_is_rechecked_in_required_result_transaction(db, monkeypatch, kind):
    actual = processing.apply_long_term_patch_firestore

    def delete_before_transaction(**kwargs):
        start_deletion(db, kind)
        return actual(**kwargs)

    monkeypatch.setattr(intake, 'normalize', normalized)
    monkeypatch.setattr(processing, 'apply_long_term_patch_firestore', delete_before_transaction)
    result = intake.after_capture(UID, stored(db), db_client=db)
    assert result is None or not result.processed
    assert stored(db).processing_state.value == ('pending' if kind == 'account' else 'blocked')
    assert not stored(db).promotion.get('admission_receipt')


def test_dispatch_metadata_failure_defers_without_quality_retry(db, monkeypatch):
    calls = []
    actual = intake.source_revisions

    def unavailable_in_model_worker(*args, **kwargs):
        calls.append('admit')
        if len(calls) == 2:
            raise ConnectionError('synthetic metadata outage')
        return actual(*args, **kwargs)

    monkeypatch.setattr(intake, 'source_revisions', unavailable_in_model_worker)
    monkeypatch.setattr(intake, 'normalize', lambda *a, **k: pytest.fail('metadata unavailable'))
    result = intake.after_capture(UID, stored(db), db_client=db)
    assert result.retryable and not result.processed
    receipts = [value for path, value in db.rows.items() if 'required_processing_retry_' in path[-1]]
    assert len(receipts) == 1 and receipts[0]['attempt_count'] == 0 and receipts[0]['lease_owner'] is None


def test_dispatch_metadata_wait_cannot_start_provider_after_deadline(db, monkeypatch):
    clock = {'now': 0, 'reads': 0}
    actual = intake.assert_account_active

    def slow_final_read(*args):
        actual(*args)
        clock['reads'] += 1
        if clock['reads'] == 2:
            clock['now'] = 11

    monkeypatch.setattr(intake, 'time', SimpleNamespace(monotonic=lambda: clock['now']))
    monkeypatch.setattr(intake, 'assert_account_active', slow_final_read)
    monkeypatch.setattr(intake, 'normalize', lambda *a, **k: pytest.fail('deadline passed'))
    with pytest.raises(processing.RequiredProcessingDeferred, match='deadline'):
        intake.normalize_at_dispatch(stored(db), db_client=db, deadline=10)


@pytest.mark.parametrize('dependency', ['utils.llm.clients', 'utils.llm.usage_tracker'])
def test_model_dependency_import_failure_defers_without_quality_retry(db, monkeypatch, dependency):
    import builtins

    actual = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == dependency:
            raise ImportError('synthetic unavailable model dependency')
        return actual(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', unavailable)
    result = intake.after_capture(UID, stored(db), db_client=db)
    assert result.retryable and not result.processed
    assert stored(db).processing_state.value == 'pending'
    receipts = [value for path, value in db.rows.items() if 'required_processing_retry_' in path[-1]]
    assert len(receipts) == 1 and receipts[0]['attempt_count'] == 0 and receipts[0]['lease_owner'] is None


@pytest.mark.asyncio
async def test_account_deletion_blocks_backlog_before_embedding(db):
    historical_candidate(db)
    db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    source = SimpleNamespace(search=AsyncMock())
    with pytest.raises(RequiredIntakeSourceChanged, match='account_deleting'):
        await backlog.prepare(UID, {'targets': []}, EvidenceRecords(), SessionLimits(), source)
    source.search.assert_not_awaited()


@pytest.mark.parametrize('flag,value', [('user_review', False), ('is_locked', True), ('is_dismissed', True)])
def test_completion_respects_owner_disposition_after_normalization(db, monkeypatch, flag, value):
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert intake.after_capture(UID, stored(db), db_client=db).processed
    db.rows[('users', UID, 'memory_items', 'new')]['promotion'][flag] = value
    monkeypatch.setattr(consolidation, 'list_receipted_required_processing_items', lambda *a, **kw: [stored(db)])
    result = consolidation.complete_receipted_required_intake(db_client=db, uid=UID, now=NOW, run_id='owner-choice')
    assert not result.promoted_memory_ids
    assert stored(db).tier.value == 'short_term'


def test_unmanaged_db_submission_defers_instead_of_waiting_on_provider(db, monkeypatch):
    monkeypatch.setattr(intake, 'normalize', lambda *a: pytest.fail('DB worker must not wait on a provider'))
    with executors.MonitoredThreadPoolExecutor(name='synthetic-db', max_workers=1) as pool:
        monkeypatch.setattr(executors, 'db_executor', pool)
        monkeypatch.setattr(intake, 'db_executor', pool)
        assert pool.submit(intake.after_capture, UID, stored(db), db_client=db).result(timeout=2) is None
    assert stored(db).processing_state.value == 'pending'


def test_completion_rechecks_owner_disposition_inside_transaction(db, monkeypatch):
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert intake.after_capture(UID, stored(db), db_client=db).processed
    actual = consolidation.apply_long_term_patch_firestore

    def reject_before_commit(**kwargs):
        db.rows[('users', UID, 'memory_items', 'new')]['promotion']['user_review'] = False
        return actual(**kwargs)

    monkeypatch.setattr(consolidation, 'apply_long_term_patch_firestore', reject_before_commit)
    with pytest.raises(RequiredIntakeSourceChanged, match='completion_owner_changed'):
        consolidation.complete_required_memory_item(UID, stored(db), db_client=db, now=NOW, run_id='owner-race')
    assert stored(db).tier.value == 'short_term'


@pytest.mark.asyncio
async def test_retry_rotates_past_a_full_withheld_page(db, monkeypatch):
    rows = []
    for index in range(101):
        row = item(f'page-{index:03d}', captured_at=NOW - timedelta(minutes=20) + timedelta(microseconds=index))
        db.rows[('users', UID, 'memory_items', row.memory_id)] = row.model_dump(mode='python')
        db.rows[('users', UID, 'memory_evidence', row.evidence[0].evidence_id)] = row.evidence[0].model_dump(
            mode='python'
        )
        rows.append(row)
    positions = []

    def page(uid, **kwargs):
        positions.append(kwargs.get('cursor'))
        return rows[:100] if kwargs.get('cursor') is None else rows[100:]

    monkeypatch.setattr(processing, 'list_pending_required_processing_items', page)
    monkeypatch.setattr(intake, 'source_revisions', lambda uid, row, **kw: {} if row.memory_id == 'page-100' else None)
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert await intake.retry_owner(UID, db_client=db, now=NOW) == 0
    assert await intake.retry_owner(UID, db_client=db, now=NOW) == 1
    assert stored(db, 'page-100').processing_state.value == 'processed'
    assert stored(db, 'page-000').processing_state.value == 'pending'
    assert positions == [None, {'captured_at': rows[99].captured_at, 'memory_id': rows[99].memory_id}]


@pytest.mark.asyncio
async def test_corrupt_source_does_not_pin_a_valid_retry(db, monkeypatch):
    monkeypatch.setattr(
        processing, 'list_pending_required_processing_items', lambda *a, **kw: [item('corrupt'), stored(db)]
    )

    def source(uid, row, **kw):
        if row.memory_id == 'corrupt':
            raise ValueError('synthetic invalid source shape')
        return {}

    monkeypatch.setattr(intake, 'source_revisions', source)
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert await intake.retry_owner(UID, db_client=db, now=NOW + timedelta(minutes=20)) == 1


def test_completion_failure_does_not_pin_a_valid_receipt(db, monkeypatch):
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert intake.after_capture(UID, stored(db), db_client=db).processed
    monkeypatch.setattr(
        consolidation,
        'list_receipted_required_processing_items',
        lambda *a, **kw: [item('corrupt', processed=True), stored(db)],
    )
    actual = consolidation.complete_required_memory_item

    def complete(uid, row, **kw):
        if row.memory_id == 'corrupt':
            raise ValueError('synthetic invalid source shape')
        return actual(uid, row, **kw)

    monkeypatch.setattr(consolidation, 'complete_required_memory_item', complete)
    result = consolidation.complete_receipted_required_intake(UID, db_client=db, now=NOW, run_id='corrupt-source')
    assert result.failed_memory_ids == ['corrupt'] and result.promoted_memory_ids == ['new']


def test_backlog_kill_switch_is_rechecked_at_canonical_apply(db, monkeypatch):
    row = historical_candidate(db)

    def disable_during_normalize(item, **kw):
        monkeypatch.setenv('DREAM_REQUIRED_INTAKE_BACKLOG_ENABLED', 'false')
        return normalized(item)

    monkeypatch.setattr(backlog, 'bounded_normalize', disable_during_normalize)
    with pytest.raises((review_store.ReviewConflict, ValueError)):
        backlog.apply(UID, resolution(row, other=''), {'memory_items/new': row}, None, 'switch-race', row)
    assert stored(db).processing_state.value == 'pending'


def test_completion_rotates_past_a_full_uncompletable_page(db, monkeypatch):
    rows = []
    for index in range(101):
        row = item(
            f'page-{index:03d}',
            captured_at=NOW - timedelta(minutes=20) + timedelta(microseconds=index),
            processed=index < 100,
        )
        db.rows[('users', UID, 'memory_items', row.memory_id)] = row.model_dump(mode='python')
        db.rows[('users', UID, 'memory_evidence', row.evidence[0].evidence_id)] = row.evidence[0].model_dump(
            mode='python'
        )
        rows.append(row)
    assert processing.process_required_memory_item(UID, 'page-100', db_client=db, processor=normalized).processed

    def page(uid, **kwargs):
        return rows[:100] if kwargs.get('cursor') is None else [stored(db, 'page-100')]

    monkeypatch.setattr(consolidation, 'list_receipted_required_processing_items', page)
    first = consolidation.complete_receipted_required_intake(UID, db_client=db, now=NOW, run_id='scan-one')
    second = consolidation.complete_receipted_required_intake(UID, db_client=db, now=NOW, run_id='scan-two')
    assert not first.promoted_memory_ids and second.promoted_memory_ids == ['page-100']
    assert stored(db, 'page-100').tier.value == 'long_term'


def test_cursor_advance_fences_generation_and_account_deletion(db):
    before, cursor, generation = required_intake_cursors.load(UID, 'retry', db_client=db)
    assert cursor is None
    db.rows[('users', UID, 'memory_state', 'apply_control')]['account_generation'] += 1
    required_intake_cursors.finish(
        UID, 'retry', before, {'captured_at': NOW, 'memory_id': 'new'}, generation, db_client=db
    )
    assert not any(path[-1] == 'required_intake_retry_scan' for path in db.rows)
    db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    with pytest.raises(RequiredIntakeSourceChanged, match='account_deleting'):
        required_intake_cursors.finish(UID, 'retry', before, cursor, generation, db_client=db)


def test_partial_neighbor_search_cannot_establish_uniqueness(db):
    row = historical_candidate(db)
    row[backlog.MARKER]['dedupe_complete'] = False
    with pytest.raises(ValueError, match='dedupe_incomplete'):
        backlog.validate(resolution(row, other=''), {'memory_items/new': row})


def test_existing_inventory_has_explicit_coverage_cap_and_skips_pending(db):
    rows, complete = backlog.read_existing_inventory(UID, 1, db_client=db)
    assert complete and not rows
    for index in range(101):
        row = item(f'cap-{index:03d}')
        db.rows[('users', UID, 'memory_items', row.memory_id)] = row.model_dump(mode='python')
    assert backlog.read_existing_inventory(UID, 1, db_client=db) == ({}, False)


@pytest.mark.asyncio
async def test_paginated_neighbors_are_not_unique_coverage(db, monkeypatch):
    historical_candidate(db)
    monkeypatch.setattr(processing, 'list_pending_required_processing_items', lambda *a, **kw: [stored(db)])
    monkeypatch.setattr(backlog, 'read_existing_inventory', lambda *a, **kw: ({}, False))
    survivor = {
        'id': 'survivor',
        'content': 'Synthetic existing fact.',
        'visibility': 'private',
        'subject_entity_id': 'user',
        'memory_tier': 'long_term',
    }
    source = SimpleNamespace(
        search=AsyncMock(
            return_value={
                'complete': True,
                'results': [{'ref': 'memory_items/survivor'}],
                'cursors': {'memory_items': 'next-page'},
            }
        ),
        read=AsyncMock(return_value=survivor),
    )
    seed, records = await backlog.prepare(UID, {'targets': []}, EvidenceRecords(), SessionLimits(), source)
    assert seed['required_intake_candidates'] == ['memory_items/new']
    assert records['memory_items/new'][backlog.MARKER]['dedupe_complete'] is False
    with pytest.raises(ValueError, match='dedupe_incomplete'):
        backlog.validate(resolution(records['memory_items/new'], other=''), records)


def test_only_backlog_kind_may_cite_a_bounded_full_inventory(db):
    row = historical_candidate(db)
    raw = resolution(row).model_dump()
    raw['evidence'] = ['memory_items/new', *[f'memory_items/e{i}' for i in range(20)]]
    assert len(HarnessEdit.model_validate(raw).evidence) == 21
    raw['kind'] = 'title'
    with pytest.raises(ValueError, match='Only bounded required-intake'):
        HarnessEdit.model_validate(raw)
    with pytest.raises(ValueError, match='candidate_required'):
        backlog.validate(resolution(row), {'memory_items/new': row}, authority='user')


def test_private_dream_contract_does_not_widen_released_review(db):
    public = ReleasedHarnessEdit.model_json_schema()['properties']
    private = HarnessEdit.model_json_schema()['properties']
    assert 'resolve_required_memory' not in public['kind']['enum']
    assert public['evidence']['maxItems'] == 10
    assert 'resolve_required_memory' in private['kind']['enum']
    assert private['evidence']['maxItems'] == 101
    raw = resolution(historical_candidate(db)).model_dump()
    with pytest.raises(ValueError, match='Dream-private'):
        tool_model('propose_edit', 'user').model_validate({'edit': raw})
    parsed = tool_model('propose_edit', 'dream').model_validate({'edit': raw})
    assert parsed.edit.kind == 'resolve_required_memory'
    assert 'resolve_required_memory' not in str(tool_schemas(authority='user'))
    assert 'resolve_required_memory' in str(tool_schemas(authority='dream'))


def test_private_intake_cannot_be_serialized_into_review_offer(db):
    with pytest.raises(ValueError, match='cannot be offered in Review'):
        dream_review_policy.suggest_edit(UID, resolution(historical_candidate(db)), {})


@pytest.mark.asyncio
async def test_private_dream_tool_call_stages_through_the_real_session(db, monkeypatch):
    row = historical_candidate(db)
    row[backlog.MARKER]['dedupe_refs'] = []
    edit = resolution(row, other='').model_copy(update={'evidence': ['memory_items/new']})
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(review_store, 'safe_id', lambda *a: 'synthetic-intake-proposal')
    session = Session(
        UID,
        SimpleNamespace(),
        SessionLimits(),
        {'targets': ['memory_items/new']},
        authority='dream',
        records=EvidenceRecords({'memory_items/new': row}),
    )
    result = await session.execute(
        [
            {
                'id': 'private-tool',
                'function': {'name': 'propose_edit', 'arguments': json.dumps({'edit': edit.model_dump(mode='json')})},
            }
        ]
    )
    response = json.loads(result[0]['content'].split('\n', 1)[1])
    assert response['status'] == 'staged', response
    assert isinstance(next(iter(session.staged.values())).operation, HarnessEdit)


def item(key='new', *, captured_at=NOW, processed=False):
    content = 'Synthetic owner prefers tea.'
    evidence = MemoryEvidence(
        evidence_id='ev_' + key,
        source_type='manual',
        source_id=key,
        source_version='1',
        artifact_preservation='not_applicable',
    )
    promotion = required_processing_payload(
        {'id': key, 'content': content, 'manually_added': True}, source_surface='mcp'
    )['promotion']
    if processed:
        promotion['processing_status'] = 'processed'
    return MemoryItem(
        uid=UID,
        memory_id=key,
        version=1,
        item_revision=1,
        tier='short_term',
        status='active',
        processing_state='processed' if processed else 'pending',
        content=content,
        content_hash=memory_content_hash(content=content, evidence_ids=[evidence.evidence_id]),
        evidence=[evidence],
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        subject_entity_id='user',
        subject_scope='primary_user',
        captured_at=captured_at,
        updated_at=NOW,
        account_generation=1,
        expires_at=captured_at + timedelta(days=7),
        promotion=promotion,
    )


@pytest.fixture
def db(monkeypatch):
    database = DreamFirestore()
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.setenv('MEMORY_REQUIRED_INTAKE_ENABLED', 'true')
    monkeypatch.setenv('DREAM_REQUIRED_INTAKE_BACKLOG_ENABLED', 'true')
    monkeypatch.setenv('DREAM_REQUIRED_INTAKE_BACKLOG_COHORT', 'uid:' + UID)
    monkeypatch.setattr(review_store, 'client', lambda: database)
    monkeypatch.setattr(memory_apply_store, '_firestore_transactional', lambda fn: fn)
    monkeypatch.setattr(backlog.firestore, 'transactional', lambda fn: fn)
    # Exercise real transaction bodies against the strict read-before-write fake.
    for name in (
        '_claim_retry_state_transaction',
        '_release_deferred_retry_state_transaction',
        '_transition_retry_state_transaction',
        '_delete_retry_state_transaction',
    ):
        decorated = getattr(processing, name)
        monkeypatch.setattr(processing, name, decorated.to_wrap)
    database.rows[('users', UID, 'memory_state', 'apply_control')] = MemoryControlState(
        uid=UID,
        head_commit_id='head0',
        account_generation=1,
        source_generation=1,
    ).model_dump(mode='python')
    database.rows[('users', UID, 'memory_items', 'new')] = item().model_dump(mode='python')
    database.rows[('users', UID, 'memory_evidence', 'ev_new')] = item().evidence[0].model_dump(mode='python')
    database.apply_results = []
    actual_apply = memory_apply_store.apply_long_term_patch_firestore

    def apply(**kwargs):
        result = actual_apply(**kwargs)
        database.apply_results.append((result.status, result.reason))
        if kwargs['patch_payload'].get('result_status') == 'superseded':
            assert result.status == ApplyStatus.committed, result.reason
        return result

    monkeypatch.setattr(processing, 'apply_long_term_patch_firestore', apply)
    monkeypatch.setattr(backlog, 'apply_long_term_patch_firestore', apply)
    return database


def normalized(row, **kwargs):
    return processing.ProcessedRequiredMemory(content=row.content, predicate='prefers', arguments={'drink': 'tea'})


def stored(database, key='new'):
    return MemoryItem.model_validate(database.rows[('users', UID, 'memory_items', key)])


def test_inline_receipts_success_and_repeated_capture_is_idempotent(db, monkeypatch):
    calls = []

    def normalize(row, **kwargs):
        calls.append(row.memory_id)
        return normalized(row)

    monkeypatch.setattr(intake, 'normalize', normalize)
    assert intake.after_capture(UID, item(), db_client=db).processed, db.apply_results
    assert stored(db).processing_state.value == 'processed'
    assert stored(db).promotion['processing_receipt']['output_item_revision'] == stored(db).item_revision
    intake.after_capture(UID, item(), db_client=db)
    assert calls == ['new']


def test_inline_reason_token_is_a_closed_set():
    matrix = [
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', processed=True, attempted=True),
            'processed',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='newer_revision_pending'),
            'newer_revision_pending',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='memory_not_found'),
            'memory_not_found',
        ),
        (
            processing.RequiredMemoryProcessingResult(
                memory_id='new', skipped_reason='not_pending_required_processing'
            ),
            'not_pending_required_processing',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='account_generation_changed'),
            'account_generation_changed',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='writer_mode_owned'),
            'writer_mode_owned',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='retry_backoff'),
            'retry_backoff',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='attempt_leased'),
            'attempt_leased',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='retry_exhausted'),
            'retry_exhausted',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='processor_not_configured'),
            'processor_not_configured',
        ),
        (
            processing.RequiredMemoryProcessingResult(
                memory_id='new', attempted=True, retryable=True, error_code='flex_deferred'
            ),
            'flex_deferred',
        ),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', attempted=True, error_code='APITimeoutError'),
            'failed',
        ),
        (processing.RequiredMemoryProcessingResult(memory_id='new', attempted=True), 'unclassified'),
        (
            processing.RequiredMemoryProcessingResult(memory_id='new', skipped_reason='synthetic_future_reason'),
            'unclassified',
        ),
    ]
    for result, expected in matrix:
        token = intake.inline_reason(result)
        assert token == expected
        assert token in intake.INLINE_REASON_TOKENS


def test_inline_log_line_carries_the_reason_token(db, monkeypatch, caplog):
    result = processing.RequiredMemoryProcessingResult(
        memory_id='new', attempted=True, skipped_reason='newer_revision_pending'
    )
    monkeypatch.setattr(processing, 'process_required_memory_item', lambda *a, **k: result)
    with caplog.at_level(logging.INFO, logger='utils.memory.required_intake'):
        intake.after_capture(UID, item(), db_client=db)
    assert 'required_intake_inline processed=False attempted=True reason=newer_revision_pending' in caplog.text


@pytest.mark.asyncio
async def test_inline_failure_stays_pending_then_dream_retries_same_revision(db, monkeypatch):
    old_enough = max(policy.BACKLOG_CUTOFF, NOW - timedelta(minutes=20))
    row = item(captured_at=old_enough)
    db.rows[('users', UID, 'memory_items', 'new')] = row.model_dump(mode='python')

    def fail(*args, **kwargs):
        raise PromotionFlexDeferred('synthetic_capacity')

    monkeypatch.setattr(intake, 'normalize', fail)
    result = intake.after_capture(UID, row, db_client=db)
    assert result.retryable and not result.processed
    assert stored(db).processing_state.value == 'pending'
    receipts = [value for path, value in db.rows.items() if 'required_processing_retry_' in path[-1]]
    assert len(receipts) == 1 and receipts[0]['attempt_count'] == 0 and receipts[0]['lease_owner'] is None
    monkeypatch.setattr(intake, 'normalize', normalized)
    captured = {}

    def pending(uid, **kwargs):
        captured.update(kwargs)
        return [stored(db)]

    monkeypatch.setattr(processing, 'list_pending_required_processing_items', pending)
    assert await intake.retry_owner(UID, db_client=db, now=NOW) == 1
    assert captured['captured_after'] == policy.BACKLOG_CUTOFF
    assert captured['captured_before'] == NOW - timedelta(minutes=10)
    assert captured['limit'] == 100
    assert stored(db).processing_state.value == 'processed'


def test_inline_off_and_historical_replay_do_not_call_processor(db, monkeypatch):
    monkeypatch.setattr(processing, 'process_required_memory_item', lambda *a, **k: pytest.fail('must stay pending'))
    intake.after_capture(UID, item(captured_at=policy.BACKLOG_CUTOFF - timedelta(days=1)), db_client=db)
    monkeypatch.setenv('MEMORY_REQUIRED_INTAKE_ENABLED', 'false')
    intake.after_capture(UID, item(), db_client=db)


def test_batch_shares_deadline_and_never_starts_another_attempt_after_budget(db, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(intake.time, 'monotonic', lambda: clock[0])
    calls = []

    def process(*args, **kwargs):
        calls.append(kwargs)
        clock[0] += 13
        return processing.RequiredMemoryProcessingResult(memory_id='new', attempted=True)

    monkeypatch.setattr(processing, 'process_required_memory_item', process)
    with intake.capture_budget():
        intake.after_capture(UID, item(), db_client=db)
        intake.after_capture(UID, item('second'), db_client=db)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_runs_before_reserved_capacity_wait(monkeypatch):
    order = []
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: [UID])

    async def retry(**kwargs):
        order.append('retry')

    async def capacity(**kwargs):
        assert order == ['retry']
        order.append('capacity')
        return None

    monkeypatch.setattr(dream_agent, 'retry_sweep', retry)
    monkeypatch.setattr(dream_agent.dream_capacity, 'available_model', capacity)
    monkeypatch.setattr(dream_agent, 'on_demand_enabled', lambda: False)
    monkeypatch.setattr(dream_agent, 'RESERVED_RECHECKS', 0)
    assert await dream_agent.drain() == [{'status': 'waiting', 'reason': 'reserved_capacity'}]


def candidate_context(db):
    control = backlog.read_control(UID, db)
    return {
        'head_commit_id': control.head_commit_id,
        'account_generation': 1,
        'source_generation': 1,
        'dedupe_refs': ['memory_items/survivor'],
        'search_complete': True,
        'dedupe_complete': True,
    }


def historical_candidate(db):
    original = item(captured_at=policy.BACKLOG_CUTOFF - timedelta(days=1))
    db.rows[('users', UID, 'memory_items', 'new')] = original.model_dump(mode='python')
    return backlog.read_candidate(UID, 'new', candidate_context(db))


def resolution(row, *, other='memory_items/survivor'):
    return HarnessEdit(
        kind='resolve_required_memory',
        target='memory_items/new',
        other=other,
        before=row['content'],
        reason='Synthetic same-subject duplicate comparison',
        evidence=['memory_items/new', 'memory_items/survivor'],
    )


def test_backlog_dedupe_retains_source_and_does_not_normalize_or_change_survivor(db, monkeypatch):
    row = historical_candidate(db)
    survivor = {
        'id': 'survivor',
        'content': row['content'],
        'visibility': 'private',
        'subject_scope': row['subject_scope'],
        'subject_entity_id': row['subject_entity_id'],
        'memory_tier': 'long_term',
    }
    db.rows[('users', UID, 'memory_items', 'survivor')] = {
        **item('survivor', processed=True).model_dump(mode='python'),
        'tier': 'long_term',
        'expires_at': None,
        'ledger_commit_id': 'synthetic-survivor-commit',
        'ledger_sequence': 1,
    }
    monkeypatch.setattr(backlog, 'bounded_normalize', lambda *a, **k: pytest.fail('duplicate must not become visible'))
    outcome = backlog.apply(
        UID,
        resolution(row),
        {'memory_items/new': row, 'memory_items/survivor': survivor},
        None,
        'synthetic-dedupe',
        row,
    )
    assert outcome == 'applied'
    result = stored(db)
    assert result.status.value == 'superseded' and result.processing_state.value == 'blocked'
    assert result.content == row['content']
    assert result.promotion['required_intake_resolution']['survivor_id'] == 'survivor'


def test_backlog_new_fact_uses_same_processor_and_receipt(db, monkeypatch):
    row = historical_candidate(db)
    monkeypatch.setattr(backlog, 'bounded_normalize', normalized)
    assert (
        backlog.apply(UID, resolution(row, other=''), {'memory_items/new': row}, None, 'synthetic-unique', row)
        == 'applied'
    )
    assert stored(db).processing_state.value == 'processed'
    assert stored(db).promotion['processing_receipt']['decision'] == 'durable_required'


def test_backlog_changed_head_or_incomplete_neighbors_cannot_admit(db):
    row = historical_candidate(db)
    edit = resolution(row, other='')
    edit.evidence = ['memory_items/new']
    with pytest.raises(ValueError, match='cite_all_neighbors'):
        backlog.validate(edit, {'memory_items/new': row})
    edit.evidence.append('memory_items/survivor')
    db.rows[('users', UID, 'memory_state', 'apply_control')]['head_commit_id'] = 'concurrent-canonical-write'
    with pytest.raises(review_store.ReviewConflict, match='snapshot changed'):
        backlog.apply(UID, edit, {'memory_items/new': row}, None, 'synthetic', row)
    assert stored(db).processing_state.value == 'pending'


@pytest.mark.asyncio
async def test_incomplete_backlog_search_never_seeds_hidden_items(db, monkeypatch):
    historical_candidate(db)
    monkeypatch.setattr(backlog, 'read_existing_inventory', lambda *a, **k: ({}, False))
    monkeypatch.setattr(processing, 'list_pending_required_processing_items', lambda *a, **k: [stored(db)])
    source = SimpleNamespace(search=AsyncMock(return_value={'complete': False, 'results': []}))
    seed, rows = await backlog.prepare(UID, {'targets': []}, EvidenceRecords(), SessionLimits(), source)
    assert not seed['targets'] and not rows


def test_backlog_switch_and_cohort_are_independent(monkeypatch):
    monkeypatch.setenv('MEMORY_REQUIRED_INTAKE_ENABLED', 'true')
    monkeypatch.delenv('DREAM_REQUIRED_INTAKE_BACKLOG_ENABLED', raising=False)
    monkeypatch.setenv('DREAM_REQUIRED_INTAKE_BACKLOG_COHORT', 'uid:' + UID)
    assert not policy.backlog_enabled(UID)
    monkeypatch.setenv('DREAM_REQUIRED_INTAKE_BACKLOG_ENABLED', 'true')
    assert policy.backlog_enabled(UID) and not policy.backlog_enabled('synthetic-other-owner')


@pytest.mark.asyncio
async def test_cleanup_off_still_runs_required_retry_phase(monkeypatch):
    retry = AsyncMock()
    monkeypatch.setattr(dream_agent, 'enabled', lambda: False)
    monkeypatch.setattr(dream_agent, 'retry_sweep', retry)
    assert await dream_agent.drain(limit=7) == []
    retry.assert_awaited_once_with(limit=7, complete_owner=consolidation.complete_receipted_required_intake)


@pytest.mark.asyncio
async def test_retry_inventory_cursor_only_advances_completed_prefix(monkeypatch):
    finish = []
    monkeypatch.setenv('MEMORY_REQUIRED_INTAKE_ENABLED', 'true')
    monkeypatch.setattr(dream_scheduler, 'required_retry_page', lambda **kw: (['a', 'b', 'c'], 'before'))
    monkeypatch.setattr(intake, 'retry_due_owners', AsyncMock(return_value=2))
    monkeypatch.setattr(dream_scheduler, 'finish_required_retry_page', lambda *args: finish.append(args))
    await intake.retry_sweep()
    assert finish == [('before', 'b')]


def test_source_quote_admission_requires_owner_anchor_and_revision(monkeypatch):
    monkeypatch.setattr(admission, 'assert_account_active', lambda *args: None)
    owner = {
        'id': 'owner',
        'text': 'I prefer tea',
        'start': 0,
        'end': 2,
        'speaker_id': 0,
        'is_user': True,
        'speaker_label_source': 'manual',
    }
    guest = {'id': 'guest', 'text': 'I prefer coffee', 'start': 3, 'end': 5, 'speaker_id': 1, 'is_user': False}
    source = {'transcript_segments': [owner, guest]}
    monkeypatch.setattr(admission, 'serving_for', lambda *a: True)
    from database import conversations
    from utils.conversations import relevance_content, relevance_media_metrics

    monkeypatch.setattr(conversations, 'prepare_conversation_for_read', lambda *a, **k: source)
    monkeypatch.setattr(relevance_content, 'exclude_from_derived', lambda *a, **k: False)
    counts = []
    monkeypatch.setattr(
        relevance_media_metrics, 'observe_owner_memory_admission', lambda *a: counts.append(a), raising=False
    )
    snapshot = SimpleNamespace(update_time=NOW, to_dict=lambda: source)
    client = SimpleNamespace(document=lambda path: SimpleNamespace(get=lambda: snapshot))
    evidence = (
        item()
        .evidence[0]
        .model_copy(
            update={
                'source_type': 'conversation',
                'source_id': 'conversation',
                'conversation_id': 'conversation',
                'quote_refs': [{'text': 'I prefer tea', 'segment_id': 'owner'}],
            }
        )
    )
    row = item().model_copy(update={'user_asserted': False, 'evidence': [evidence]})
    assert admission.source_revisions(UID, row, db_client=client) == {f'users/{UID}/conversations/conversation': NOW}
    evidence.quote_refs = [{'text': 'I prefer coffee', 'segment_id': 'guest'}]
    assert admission.source_revisions(UID, row, db_client=client) is None
    assert counts == [(2, 1), (2, 0)]
    evidence.quote_refs = [{'text': 'I prefer tea', 'segment_id': 'owner'}]
    snapshot.update_time = None
    assert admission.source_revisions(UID, row, db_client=client) is None
    snapshot.update_time = NOW
    owner['speaker_label_source'] = None
    assert admission.source_revisions(UID, row, db_client=client) is None


@pytest.mark.parametrize('serving', [False, True])
def test_explicit_text_and_nonserving_audio_keep_their_existing_authority(monkeypatch, serving):
    monkeypatch.setattr(admission, 'assert_account_active', lambda *args: None)
    monkeypatch.setattr(admission, 'serving_for', lambda *a: serving)
    client = SimpleNamespace(document=lambda path: pytest.fail('explicit text must not read audio'))
    assert admission.source_revisions(UID, item(), db_client=client) == {}
    if not serving:
        row = item().model_copy(
            update={
                'user_asserted': False,
                'evidence': [
                    item().evidence[0].model_copy(update={'source_type': 'conversation', 'conversation_id': 'source'})
                ],
            }
        )
        assert admission.source_revisions(UID, row, db_client=client) == {}


def test_transactional_source_revision_change_blocks_canonical_settlement(db, monkeypatch):
    row = stored(db)
    path = f'users/{UID}/conversations/synthetic'
    calls = []
    monkeypatch.setattr(intake, 'normalize', lambda item, **kw: calls.append(item.memory_id) or normalized(item))
    # A source proven at admission is gone/changed by the time apply reads it.
    monkeypatch.setattr(intake, 'source_revisions', lambda *a, **k: {path: NOW})
    outcome = intake.after_capture(UID, row, db_client=db)
    assert outcome.retryable and not outcome.processed
    assert calls == ['new'] and stored(db).processing_state.value == 'pending'
    receipts = [value for key, value in db.rows.items() if 'required_processing_retry_' in key[-1]]
    assert receipts[0]['attempt_count'] == 0


def test_retry_cursor_cas_does_not_clobber_a_newer_sweep(db, monkeypatch):
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    path = ('dream_scheduler', 'required_intake')
    db.rows[path] = {'after': 'a'}
    dream_scheduler.finish_required_retry_page('a', 'b', firestore_client=db)
    assert db.rows[path] == {'after': 'b'}
    dream_scheduler.finish_required_retry_page('a', 'c', firestore_client=db)
    assert db.rows[path] == {'after': 'b'}


def test_create_retry_after_inline_rewrite_reuses_the_receipted_submission(db, monkeypatch):
    raw = 'remember that tea is my preferred drink'
    payload = required_processing_payload(
        {'id': document_id_from_seed(raw), 'content': raw, 'manually_added': True}, source_surface='mcp'
    )
    calls = []

    def rewrite(row, **kwargs):
        calls.append(row.memory_id)
        return processing.ProcessedRequiredMemory(content='The owner prefers tea.', predicate='prefers')

    monkeypatch.setattr(intake, 'normalize', rewrite)
    first = adapter.write_canonical_external_memory(UID, payload, db_client=db)
    second = adapter.write_canonical_external_memory(UID, payload, db_client=db)
    assert first == second and calls == [first]
    assert stored(db, first).content == 'The owner prefers tea.'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['restricted', 'locked', 'old_generation'])
async def test_backlog_ineligible_rows_never_reach_embedding_search(db, monkeypatch, kind):
    historical_candidate(db)
    row = stored(db)
    updates = (
        {'sensitivity_labels': ['credential']}
        if kind == 'restricted'
        else ({'promotion': {**row.promotion, 'is_locked': True}} if kind == 'locked' else {'account_generation': 0})
    )
    row = row.model_copy(update=updates)
    monkeypatch.setattr(processing, 'list_pending_required_processing_items', lambda *a, **k: [row])
    source = SimpleNamespace(search=AsyncMock(side_effect=AssertionError('must not embed withheld content')))
    seed, rows = await backlog.prepare(UID, {'targets': []}, EvidenceRecords(), SessionLimits(), source)
    assert not seed['targets'] and not rows
    source.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_timed_out_model_completion_has_no_late_write_authority(db):
    started, release, finished = Event(), Event(), Event()

    def slow(row):
        started.set()
        try:
            release.wait(timeout=2)
            return normalized(row)
        finally:
            finished.set()

    task = asyncio.create_task(
        processing.process_required_memory_item_async(UID, 'new', db_client=db, processor=slow, timeout_seconds=1)
    )
    try:
        assert await asyncio.to_thread(started.wait, 1)
        outcome = await task
        assert outcome.retryable and not outcome.processed
        assert stored(db).processing_state.value == 'pending'
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 2)
        await task
    assert stored(db).processing_state.value == 'pending'


def test_changed_account_generation_never_calls_normalizer(db, monkeypatch):
    row = item().model_copy(update={'account_generation': 0})
    db.rows[('users', UID, 'memory_items', 'new')] = row.model_dump(mode='python')
    monkeypatch.setattr(intake, 'normalize', lambda *a, **k: pytest.fail('stale account generation'))
    outcome = intake.after_capture(UID, row, db_client=db)
    assert outcome.skipped_reason == 'account_generation_changed' and not outcome.attempted


def test_receipted_required_completion_uses_the_existing_atomic_l2_route(db, monkeypatch):
    monkeypatch.setattr(intake, 'normalize', normalized)
    assert intake.after_capture(UID, item(), db_client=db).processed
    monkeypatch.setattr(consolidation, 'list_receipted_required_processing_items', lambda *a, **k: [stored(db)])
    result = consolidation.complete_receipted_required_intake(
        UID, db_client=db, now=NOW, run_id='synthetic-dream-completion', limit=5
    )
    assert result.promoted_memory_ids == ['new']
    assert stored(db).tier.value == 'long_term'
    assert stored(db).promotion['admission_receipt'] and stored(db).graph_ready


def test_short_term_neighbor_cannot_retire_authoritative_backlog(db):
    row = historical_candidate(db)
    survivor = {**row, 'id': 'survivor', 'memory_tier': 'short_term'}
    survivor.pop(backlog.MARKER)
    with pytest.raises(ValueError, match='not_durable'):
        backlog.validate(resolution(row), {'memory_items/new': row, 'memory_items/survivor': survivor})
    assert stored(db).status.value == 'active'


def test_noncompatibility_writer_withholds_unowned_required_work_before_paid_call(db, monkeypatch):
    db.rows[('users', UID, 'memory_state', 'apply_control')]['writer_mode'] = 'ledger'
    monkeypatch.setattr(intake, 'normalize', lambda *a, **k: pytest.fail('wrong writer must not spend'))
    outcome = intake.after_capture(UID, item(), db_client=db)
    assert outcome.skipped_reason == 'writer_mode_owned' and not outcome.attempted
