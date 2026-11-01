"""Review-round contracts: synthetic owner data only, real capability boundaries."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import conversations, review_changes, review_store, review_transcript_changes
from database.legal_holds import DestructiveOperationInProgress
from models.agent_tools import VerificationBatch
from models.review import AgentProposalItem
from tests.unit.test_dream_cleanup_edits import store, records, edit, UID
from tests.unit.test_agent_transcript_overlay import setup, correction
from tests.unit.test_dream_session import session, call, turn
from utils.agent_capabilities import transcripts, tools
from utils.agent_capabilities.cleanup_edits import validate_cleanup, require_duplicate_capture
from utils.agent_capabilities.registry import KINDS
from utils.agent_capabilities.session import rejection
from utils import dream_verify
from utils.llm.shaped_agent import Budget, Mount, Turn, run_loop


def test_bad_overlay_never_breaks_product_read_and_inline_avoids_extra_get(store, monkeypatch):
    seen, original = setup(store, monkeypatch)
    tools.apply_edit(UID, correction(), {'conversations/one': seen()}, authority='dream')
    monkeypatch.setattr(
        transcripts, 'load_entries', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Extra read'))
    )
    assert seen()['transcript_segments'][0]['text'].startswith('Qorbi')
    path = ('users', UID, 'conversations', 'one')
    store.rows[path]['transcript_correction_overlay'] = {'source': 'corrupt'}
    result = seen()
    assert result['transcript_segments'][0]['text'].startswith('Qorby')
    assert store.rows[path]['transcript_segments'] == original['transcript_segments']


def test_owner_full_segment_edit_protects_later_word_correction(store, monkeypatch):
    seen, _ = setup(store, monkeypatch)
    assert (
        review_transcript_changes.edit_user_segment(UID, 'one', 'segment-one', 'Qorby hosts a synthetic workshop.')
        == 'ok'
    )
    first = next(
        review_store.decode_doc(UID, row)['change']['change_id']
        for path, row in store.rows.items()
        if path[2:3] == ('review_changes',)
    )
    operation = correction(before='workshop', after='lab')
    tools.apply_edit(UID, operation, {'conversations/one': seen()}, authority='dream')
    with pytest.raises(review_store.ReviewConflict, match='dependent'):
        review_changes.set_undone(UID, first, True)


def test_user_edit_can_exceed_autonomous_entry_cap(store, monkeypatch):
    seen, _ = setup(store, monkeypatch)
    entry = dict(
        segment_id='segment-one',
        segment_index=0,
        start=0,
        before='Qorby',
        after='Qorbi',
        kind='spelling',
        source='dream',
        change_id='old',
        undone=True,
    )
    rows = [{**entry, 'change_id': 'synthetic-' + str(i)} for i in range(500)]
    encoded = review_store.encode_doc(UID, {'source': rows})
    store.rows[('users', UID, 'transcript_corrections', 'one')] = encoded
    store.rows[('users', UID, 'conversations', 'one')].update(
        has_transcript_corrections=True, transcript_correction_overlay=encoded
    )
    assert (
        review_transcript_changes.edit_user_segment(UID, 'one', 'segment-one', 'Owner requested synthetic replacement.')
        == 'ok'
    )
    assert seen()['transcript_segments'][0]['text'] == 'Owner requested synthetic replacement.'


def test_cleanup_undo_preserves_unrelated_background_writes(store):
    operation = edit('retire_task')
    tools.apply_edit(UID, operation, records(store), authority='dream')
    journal = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in store.rows.items()
        if path[2:3] == ('review_changes',)
    )
    task = store.rows[('users', UID, 'action_items', 'one')]
    task.update(indexed_at='synthetic-new-index', updated_at='synthetic-new-clock')
    review_changes.set_undone(UID, journal['change_id'], True)
    assert task is not store.rows[('users', UID, 'action_items', 'one')]
    restored = store.rows[('users', UID, 'action_items', 'one')]
    assert restored['status'] == 'active' and restored['indexed_at'] == 'synthetic-new-index'
    assert restored['updated_at'] == 'synthetic-new-clock'


def test_finish_first_does_not_drop_later_rejection_and_allows_repair(store, monkeypatch):
    active = session(store, monkeypatch)
    steps = []
    operation = dict(kind='dismiss_person', target='people/junk', reason='Synthetic junk')

    async def model(mount, messages):
        steps.append(deepcopy(messages))
        if len(steps) == 1:
            return turn([call('finish', {'summary': 'Done'}), call('propose_edit', {'edit': operation}, 2)])
        assert 'agent_schema' in messages[-2]['content'] or 'agent_schema' in messages[-1]['content']
        return turn(
            [
                call('finish', {'summary': 'Done'}),
                call('propose_edit', {'edit': {**operation, 'evidence': ['conversations/one']}}, 2),
            ]
        )

    result = asyncio.run(active.run(model, deadline_seconds=10))
    assert result.reason == 'finished' and len(steps) == 2 and len(active.staged) == 1


def test_only_two_boolean_opposite_votes_are_split_and_budget_keeps_parsed_value():
    for votes in [[], [True], [True, None], [None, None]]:
        assert dream_verify.disposition(votes) == 'unverified'
    assert dream_verify.disposition([True, False]) == 'split'

    async def model(mount, messages):
        return Turn(value=VerificationBatch(decisions=[]), tokens=20)

    result = asyncio.run(
        run_loop(
            Mount(instructions='Synthetic', schema=VerificationBatch, budget=Budget(turns=1, tokens=10)), [], model
        )
    )
    assert result.reason == 'token_budget' and result.value.decisions == []


def test_registry_exposes_every_shared_operation_and_user_protections_are_authority_aware(store):
    for spec in KINDS.values():
        assert all(
            callable(getattr(spec, name)) for name in ('schema', 'validate', 'key', 'apply', 'undo', 'change_view')
        )
    data = records(store)
    data['people/junk']['user_confirmed'] = True
    with pytest.raises(ValueError, match='agent_person_user_protected'):
        validate_cleanup(edit('dismiss_person'), data, authority='dream')
    validate_cleanup(edit('dismiss_person'), data, authority='user')
    data['action_items/one']['source'] = 'manual'
    with pytest.raises(ValueError, match='agent_task_user_protected'):
        validate_cleanup(edit('retire_task'), data, authority='dream')
    validate_cleanup(edit('retire_task'), data, authority='user')


def test_infrastructure_errors_are_structured_nonretryable_and_private_text_is_not_echoed():
    result = rejection(RuntimeError('Synthetic private provider detail'))
    assert result['code'] == 'agent_stale_or_unavailable' and result['retryable'] is False
    assert set(result) >= {'code', 'field', 'ref', 'expected', 'retryable'}
    assert 'private provider' not in json.dumps(result)


def test_huge_duplicate_similarity_is_bounded_and_does_not_ignore_different_tail(store):
    rows = records(store)
    one, two = rows['conversations/one'], rows['conversations/two']
    one['transcript_segments'][0]['text'] = 'synthetic repeated speech ' * 10000
    two['transcript_segments'][0]['text'] = one['transcript_segments'][0]['text'] + 'different obligation'
    with pytest.raises(ValueError, match='similarity_budget'):
        require_duplicate_capture(one, two)


def test_new_review_operation_keeps_the_released_edit_branch(store):
    operation = edit('dismiss_person')
    proposal = AgentProposalItem.model_validate({'edit': operation})
    wire = proposal.model_dump(mode='json')
    assert wire['edit']['kind'] == 'merge_people'
    assert wire['operation']['kind'] == 'dismiss_person'
    assert proposal.operation.kind == 'dismiss_person'


def test_explicit_user_can_repeat_an_undone_cleanup(store):
    data = records(store)
    store.rows[('users', UID, 'people', 'junk')]['user_confirmed'] = True
    data = records(store)
    operation = edit('dismiss_person')
    with review_store.user_request_authority(UID):
        assert tools.apply_edit(UID, operation, data, authority='user') == 'applied'
        change = next(
            review_store.decode_doc(UID, row)['change']
            for path, row in store.rows.items()
            if path[2:3] == ('review_changes',)
        )
        review_changes.set_undone(UID, change['change_id'], True)
        assert tools.apply_edit(UID, operation, records(store), authority='user') == 'applied'


def test_merge_moves_anchors_and_undo_receipt_to_the_new_capture(store, monkeypatch):
    from database.review_overlay_merge import transfer
    from google.cloud import firestore

    seen, _ = setup(store, monkeypatch)
    tools.apply_edit(UID, correction(), {'conversations/one': seen()}, authority='dream')
    journal = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in store.rows.items()
        if path[2:3] == ('review_changes',)
    )
    original = deepcopy(store.rows[('users', UID, 'conversations', 'one')])
    original.update(id='merged', has_transcript_corrections=False)
    original.pop('transcript_correction_overlay', None)
    store.rows[('users', UID, 'conversations', 'merged')] = original
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    transfer(UID, ['one'], 'merged', firestore_client=store)
    projected = conversations.prepare_conversation_for_read(store.rows[('users', UID, 'conversations', 'merged')], UID)
    assert projected['transcript_segments'][0]['text'].startswith('Qorbi')
    review_changes.set_undone(UID, journal['change_id'], True)
    projected = conversations.prepare_conversation_for_read(store.rows[('users', UID, 'conversations', 'merged')], UID)
    assert projected['transcript_segments'][0]['text'].startswith('Qorby')


def test_dynamic_kill_short_cache_and_outage_preserve_an_observed_stop(monkeypatch):
    from config import dream_control

    clock = [0.0]
    state = [False]
    calls = []

    class Flag:
        def get(self, **kwargs):
            calls.append(True)
            if state[0] is None:
                raise RuntimeError('Synthetic unavailable flag store')
            return SimpleNamespace(to_dict=lambda: {'enabled': state[0]})

    class DB:
        def collection(self, name):
            assert name == 'dream_control'
            return self

        def document(self, name):
            assert name == 'global'
            return Flag()

    monkeypatch.setattr(
        dream_control,
        'load_flag',
        lambda: DB().collection('dream_control').document('global').get().to_dict()['enabled'],
    )
    monkeypatch.setattr(dream_control.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(dream_control, '_until', 0)
    monkeypatch.setattr(dream_control, '_allowed', True)
    assert dream_control.allowed() is False
    state[0] = True
    assert dream_control.allowed() is False and len(calls) == 1
    clock[0] = 11
    state[0] = None
    assert dream_control.allowed() is False
    clock[0] = 22
    state[0] = True
    assert dream_control.allowed() is True


def test_apply_and_undo_rebuild_chunk_vectors_from_the_current_projection(store, monkeypatch):
    from database import vector_db

    seen, _ = setup(store, monkeypatch)
    indexed, deleted = [], []
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(vector_db, 'delete_transcript_chunk_vectors', lambda uid, key: deleted.append(key))
    monkeypatch.setattr(vector_db, 'upsert_transcript_chunk_vectors', lambda uid, key, chunks: indexed.append(chunks))
    tools.apply_edit(UID, correction(), {'conversations/one': seen()}, authority='dream')
    change = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in store.rows.items()
        if path[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, change['change_id'], True)
    assert 'Qorbi plans' in indexed[0][0]['text']
    assert 'Qorby plans' in indexed[1][0]['text']
    assert deleted == ['one', 'one']


def test_held_gate_blocks_transcript_vector_delete_before_provider_io(store, monkeypatch):
    from database import vector_db
    from utils.review_projection import sync_transcript_chunks

    setup(store, monkeypatch)
    provider = Mock()
    monkeypatch.setattr(vector_db, 'index', provider)
    monkeypatch.setattr(vector_db, 'default_db_client', store)
    store.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': 'legal_hold_deletion_gate.v1',
        'uid': UID,
        'kind': 'explicit_memory_deletion',
        'token': 'synthetic-gate',
        'state': 'running',
        'started_at': datetime.now(timezone.utc),
    }
    with pytest.raises(DestructiveOperationInProgress):
        sync_transcript_chunks(UID, 'one', firestore_client=store)
    assert provider.mock_calls == []


def test_committed_transcript_gate_retry_finishes_vector_projection(store, monkeypatch):
    from database import vector_db

    seen, _ = setup(store, monkeypatch)
    source = {'conversations/one': seen()}
    fences = tools.proposal_fences(UID, {'records': source})
    started_at = datetime.now(timezone.utc)
    operation = correction()
    provider = Mock()
    provider.list.return_value = [['synthetic-old-chunk']]
    monkeypatch.setattr(vector_db, 'index', provider)
    monkeypatch.setattr(vector_db, 'default_db_client', store)
    embed = Mock(return_value=[[0.1]])
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_documents=embed))
    upsert = vector_db.upsert_transcript_chunk_vectors
    attempts = []

    def contend_once(*args, **kwargs):
        attempts.append(None)
        if len(attempts) == 1:
            raise DestructiveOperationInProgress('external data write blocked by destructive operation')
        return upsert(*args, **kwargs)

    monkeypatch.setattr(vector_db, 'upsert_transcript_chunk_vectors', contend_once)
    with pytest.raises(DestructiveOperationInProgress):
        tools.apply_verified_edit(UID, operation, source, expected_records=fences, authority='dream')
    assert provider.delete.call_count == 1 and provider.upsert.call_count == 0
    assert seen()['transcript_segments'][0]['text'].startswith('Qorbi')
    assert (
        tools.apply_verified_edit(
            UID,
            operation,
            source,
            expected_records=fences,
            authority='dream',
            gate_retry=True,
            run_started_at=started_at,
        )
        == 'applied'
    )
    assert provider.delete.call_count == 2 and provider.upsert.call_count == 1
    assert 'Qorbi plans' in embed.call_args.args[0][0]
    assert len([key for key in store.rows if key[2:3] == ('review_changes',)]) == 1


def test_committed_transcript_gate_retry_keeps_applied_when_repair_fails(store, monkeypatch):
    from database import vector_db

    seen, _ = setup(store, monkeypatch)
    source = {'conversations/one': seen()}
    fences = tools.proposal_fences(UID, {'records': source})
    started_at = datetime.now(timezone.utc)
    operation = correction()
    provider = Mock()
    provider.list.return_value = [['synthetic-old-chunk']]
    monkeypatch.setattr(vector_db, 'index', provider)
    monkeypatch.setattr(vector_db, 'default_db_client', store)
    attempts = []

    def contend_then_fail(*args, **kwargs):
        attempts.append(None)
        if len(attempts) == 1:
            raise DestructiveOperationInProgress('external data write blocked by destructive operation')
        raise TimeoutError('synthetic embedding timeout')

    monkeypatch.setattr(vector_db, 'upsert_transcript_chunk_vectors', contend_then_fail)
    with pytest.raises(DestructiveOperationInProgress):
        tools.apply_verified_edit(UID, operation, source, expected_records=fences, authority='dream')
    assert (
        tools.apply_verified_edit(
            UID,
            operation,
            source,
            expected_records=fences,
            authority='dream',
            gate_retry=True,
            run_started_at=started_at,
        )
        == 'applied'
    )
    assert len(attempts) == 2


def test_shared_session_uses_one_memory_ref_spelling_for_legacy_seed_aliases():
    from utils.agent_capabilities.session import Session
    from utils.agent_capabilities.limits import SessionLimits

    session = Session(
        'synthetic-owner',
        None,
        SessionLimits(),
        {'targets': ['memories/one']},
        authority='user',
        records={'memories/one': {'content': 'Invented fact'}},
    )
    assert set(session.records) == {'memory_items/one'}
    assert session.known == {'memory_items/one'}
    assert session.seed['targets'] == ['memory_items/one']


def test_merge_without_overlay_still_seals_source_against_late_corrections(store, monkeypatch):
    from database.review_overlay_merge import transfer
    from google.cloud import firestore

    seen, original = setup(store, monkeypatch)
    store.rows[('users', UID, 'conversations', 'merged')] = {**deepcopy(original), 'id': 'merged'}
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    assert transfer(UID, ['one'], 'merged', firestore_client=store)
    assert review_transcript_changes.edit_user_segment(UID, 'one', 'segment-one', 'A stale source write.') == 'conflict'
