"""Write-time admission, leased retries and hidden historical dedupe, offline."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import required_memory_intake as policy
from database import memory_apply_store, review_store, dream_scheduler
from models.agent_edit import HarnessEdit
from models.memory_apply import ApplyStatus, MemoryControlState, memory_content_hash
from models.memory_evidence import MemoryEvidence
from models.product_memory import MemoryItem
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_required_intake as backlog
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.limits import SessionLimits
from utils.memory import canonical_required_processing as processing, required_intake as intake
from utils.memory.promotion_flex import PromotionFlexDeferred
from utils.memory import required_source_admission as admission
from utils.memory import canonical_memory_adapter as adapter
from utils.memory.required_promotion import required_processing_payload
from database.document_ids import document_id_from_seed

UID = 'synthetic-required-intake-owner'
NOW = datetime.now(timezone.utc)


def item(key='new', *, captured_at=NOW, processed=False):
    content = 'Synthetic owner prefers tea.'
    evidence = MemoryEvidence(
        evidence_id='ev_' + key,
        source_type='manual',
        source_id=key,
        source_version='1',
        artifact_preservation='not_applicable',
    )
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
        promotion={'required': True, 'processing_status': 'processed' if processed else 'pending_processing'},
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
    assert result.status.value == 'superseded' and result.processing_state.value == 'pending'
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
    retry.assert_awaited_once_with(limit=7)


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
    monkeypatch.setattr(admission.conversations, 'prepare_conversation_for_read', lambda *a, **k: source)
    monkeypatch.setattr(admission, 'exclude_from_derived', lambda *a, **k: False)
    monkeypatch.setattr(admission.owner_attribution, 'confident_owner_segments', lambda rows: [rows[0]], raising=False)
    counts = []
    monkeypatch.setattr(
        admission.relevance_media_metrics, 'observe_owner_memory_admission', lambda *a: counts.append(a), raising=False
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


@pytest.mark.parametrize('serving', [False, True])
def test_explicit_text_and_nonserving_audio_keep_their_existing_authority(monkeypatch, serving):
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
