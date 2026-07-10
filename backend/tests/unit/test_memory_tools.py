import pytest

from database import memory_ledger
from database.memory_ledger import HeadConflict
from models.memory_contracts import DurableMemoryPatch
from utils.memory.memory_tools import (
    MemoryToolContext,
    MemoryToolValidationError,
    apply_patch_with_memory_tools,
    evidence_ids_from_bundle,
    facts_from_bundle,
)


def _patch(decision='add', **overrides):
    payload = {
        'patch_id': f'patch_{decision}',
        'packet_id': 'pkt_1',
        'run_id': 'run_1',
        'observed_head_commit_id': 'head_0',
        'idempotency_key': f'idem_{decision}',
        'decision': decision,
        'result_status': 'active',
        'evidence_ids': ['ev_1'],
        'evidence_refs': [{'evidence_id': 'ev_1', 'quote': 'I use Warp every day.'}],
        'target_memory_id': 'mem_1' if decision in {'add_evidence', 'update', 'merge', 'skip_duplicate'} else None,
        'memory_text': 'User uses Warp every day.',
        'predicate': 'uses_tool',
        'arguments': {'object': 'Warp'},
        'rationale': 'direct evidence',
        'subject_entity_id': 'ent_user',
        'subject_label': 'the user',
        'aboutness': 'primary_user',
        'relationship_to_user': 'self',
    }
    payload.update(overrides)
    return DurableMemoryPatch(**payload)


def _context(state, commits, **overrides):
    def append_commit(uid, parent_commit_id, mutations, *, run_id=None, use_current_head=False, **kwargs):
        return memory_ledger.append_commit_to_history(
            state,
            commits,
            parent_commit_id,
            mutations,
            run_id=run_id,
            use_current_head=use_current_head,
        )

    payload = {
        'uid': 'u1',
        'allowed_evidence_ids': {'ev_1'},
        'append_commit': append_commit,
        'read_head': lambda uid: state.get('current_head_commit_id'),
        'route_persister': lambda uid, patch, **kwargs: {'uid': uid, 'decision': patch.decision.value},
    }
    payload.update(overrides)
    return MemoryToolContext(**payload)


def test_memory_tools_reject_empty_content_for_fact_write():
    state = {'current_head_commit_id': 'head_0'}
    context = _context(state, {})
    patch = _patch(memory_text='   ')

    with pytest.raises(MemoryToolValidationError, match='memory_text is required'):
        apply_patch_with_memory_tools(patch, context)


def test_memory_tools_reject_missing_subject_for_fact_write():
    state = {'current_head_commit_id': 'head_0'}
    context = _context(state, {})
    patch = _patch(subject_entity_id=None)

    with pytest.raises(MemoryToolValidationError, match='subject_entity_id is required'):
        apply_patch_with_memory_tools(patch, context)


def test_memory_tools_reject_malformed_predicate():
    state = {'current_head_commit_id': 'head_0'}
    context = _context(state, {})
    patch = _patch(predicate='Uses Tool')

    with pytest.raises(MemoryToolValidationError, match='predicate is malformed'):
        apply_patch_with_memory_tools(patch, context)


def test_memory_tools_reject_unresolved_evidence_ref():
    state = {'current_head_commit_id': 'head_0'}
    context = _context(state, {}, allowed_evidence_ids={'ev_1'})
    patch = _patch(evidence_ids=['ev_missing'], evidence_refs=[{'evidence_id': 'ev_missing'}])

    with pytest.raises(MemoryToolValidationError, match='unresolved evidence refs'):
        apply_patch_with_memory_tools(patch, context)


def test_memory_tools_reject_wrong_subject_attachment():
    state = {'current_head_commit_id': 'head_0'}
    context = _context(
        state,
        {},
        existing_facts={'mem_1': {'id': 'mem_1', 'subject_entity_id': 'ent_father'}},
    )
    patch = _patch('add_evidence', subject_entity_id='ent_user')

    with pytest.raises(MemoryToolValidationError, match='subject does not match'):
        apply_patch_with_memory_tools(patch, context)


def test_memory_tools_apply_append_only_and_replay_prior_state():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    context = _context(state, commits)

    first = apply_patch_with_memory_tools(_patch('add', new_memory_id='mem_new'), context)
    second_patch = _patch('update', target_memory_id='mem_new', new_memory_id='mem_updated')
    second = apply_patch_with_memory_tools(
        second_patch.model_copy(update={'observed_head_commit_id': first.commit_id}), context
    )

    assert first.applied is True
    assert second.applied is True
    assert len(commits) == 2
    first_head = memory_ledger.fold_commits([commits[first.commit_id]])
    current_head = memory_ledger.fold_commits(list(commits.values()))
    assert first_head['mem_new'].get('invalid_at') is None
    assert current_head['mem_updated']['subject_entity_id'] == 'ent_user'
    assert any(
        mutation.get('type') == 'supersede_fact'
        and mutation.get('fact_id') == 'mem_new'
        and mutation.get('by') == 'mem_updated'
        for mutation in commits[second.commit_id]['mutations']
    )


def test_memory_tools_idempotent_repeat_commits_once():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    context = _context(state, commits)
    patch = _patch('add', new_memory_id='mem_new')

    first = apply_patch_with_memory_tools(patch, context)
    second = apply_patch_with_memory_tools(patch, context)

    assert first.applied is True
    assert second.applied is False
    assert len(commits) == 1


def test_memory_tools_head_conflict_regrounds_to_current_head_once():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    current = memory_ledger.append_commit_to_history(
        state,
        commits,
        'head_0',
        [memory_ledger.add_fact({'id': 'mem_existing', 'content': 'Existing fact.'})],
    )
    context = _context(state, commits)
    patch = _patch('add', observed_head_commit_id='head_0', new_memory_id='mem_new')

    result = apply_patch_with_memory_tools(patch, context)

    assert current['applied'] is True
    assert result.applied is True
    assert result.head_conflict_retry is True
    assert len(commits) == 2
    assert state['current_head_commit_id'] == result.commit_id


def test_memory_tools_can_disable_head_conflict_retry():
    state = {'current_head_commit_id': 'head_1'}
    context = _context(state, {}, retry_on_head_conflict=False)

    with pytest.raises(HeadConflict):
        apply_patch_with_memory_tools(_patch('add', observed_head_commit_id='head_0'), context)


def test_memory_tools_persist_non_active_route_without_ledger_write():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    captured = []
    context = _context(
        state,
        commits,
        route_persister=lambda uid, patch, **kwargs: captured.append((uid, patch.decision.value, kwargs))
        or {'ok': True},
    )
    patch = _patch('review', result_status='review')

    result = apply_patch_with_memory_tools(patch, context)

    assert result.applied is False
    assert result.commit_id is None
    assert result.non_active_route == {'ok': True}
    assert captured[0][1] == 'review'
    assert commits == {}


def test_memory_tools_extract_bundle_evidence_and_facts():
    bundle = {
        'l1_items': [{'evidence_ids': ['ev_1'], 'source_refs': [{'evidence_id': 'ev_2'}]}],
        'evidence_packets': [{'evidence_ids': ['ev_3'], 'observations': [{'evidence_ids': ['ev_4']}]}],
        'graph_snapshot': {'edges': [{'fact_id': 'mem_1', 'subject_entity_id': 'ent_user'}]},
        'vector_seed': [{'memory_id': 'mem_2', 'subject_entity_id': 'ent_user'}],
    }

    assert evidence_ids_from_bundle(bundle) == {'ev_1', 'ev_2', 'ev_3', 'ev_4'}
    assert set(facts_from_bundle(bundle)) == {'mem_1', 'mem_2'}
