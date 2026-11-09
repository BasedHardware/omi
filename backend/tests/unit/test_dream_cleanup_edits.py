"""Real journal apply/Undo/Redo for synthetic people, tasks and duplicate captures."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from database import memory_ledger, review_changes, review_store, task_intelligence_control
from database.legal_holds import DestructiveOperationInProgress
from models.agent_tools import HarnessEdit, Search, tool_schemas
from tests.support.dream_firestore import DreamFirestore
from utils.agent_capabilities import tools as dream_tools
from utils.agent_capabilities import cleanup_edits as dream_cleanup_edits

UID = 'synthetic-harness-cleanup-owner'
NOW = datetime.now(timezone.utc)
SPEECH = 'Today the invented project team discussed the workshop plan and agreed to draft a complete outline for the next synthetic meeting with sample materials.'


def conversation(key):
    return {
        'id': key,
        'status': 'completed',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW + timedelta(minutes=2),
        'language': 'xx',
        'structured': {'title': 'Synthetic workshop'},
        'transcript_segments': [{'id': 'segment-one', 'text': SPEECH, 'start': 0, 'end': 120, 'is_user': True}],
    }


def task(key):
    return {
        'id': key,
        'description': 'Draft the invented workshop outline.',
        'status': 'active',
        'completed': False,
        'created_at': NOW,
        'updated_at': NOW,
        'source': 'conversation',
        'conversation_id': 'one',
        'owner': 'user',
        'account_generation': 0,
    }


@pytest.fixture
def store(monkeypatch):
    db = DreamFirestore()
    from database import vector_db

    monkeypatch.setattr(vector_db, 'index', None)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(task_intelligence_control, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(memory_ledger, 'transactional', lambda fn: fn)
    db.rows[('users', UID)] = {}
    db.rows[('users', UID, 'task_intelligence_control', 'state')] = {'account_generation': 0}
    for key in ('one', 'two'):
        db.rows[('users', UID, 'conversations', key)] = conversation(key)
        db.rows[('users', UID, 'action_items', key)] = task(key)
    db.rows[('users', UID, 'people', 'junk')] = {'id': 'junk', 'name': 'Canadian', 'created_at': NOW, 'updated_at': NOW}
    return db


def records(db):
    return {
        '/'.join(path[2:]): deepcopy(row)
        for path, row in db.rows.items()
        if path[:2] == ('users', UID) and len(path) == 4 and path[2] in {'conversations', 'people', 'action_items'}
    }


def edit(kind, **kwargs):
    targets = {
        'dismiss_person': 'people/junk',
        'merge_tasks': 'action_items/one',
        'retire_task': 'action_items/one',
        'merge_conversations': 'conversations/one',
        'set_language': 'conversations/one',
    }
    return HarnessEdit(
        kind=kind, target=targets[kind], reason='Synthetic evidenced cleanup', evidence=['conversations/one'], **kwargs
    )


@pytest.mark.parametrize(
    'operation',
    [
        edit('dismiss_person'),
        edit('retire_task'),
        edit('merge_tasks', other='action_items/two'),
        edit('merge_conversations', other='conversations/two'),
        edit('set_language', before='xx', after='en'),
    ],
)
def test_each_cleanup_applies_and_exactly_restores_missing_fields_on_undo_and_redo(store, operation):
    generation = ('users', UID, 'people_meta', 'generation')
    is_people = operation.target.startswith('people/')
    original = deepcopy(store.rows[('users', UID, *operation.target.split('/'))])
    seen = records(store)
    fences = dream_tools.proposal_fences(UID, {'records': seen})
    assert dream_tools.apply_edit(UID, operation, seen, expected_records=fences) == 'applied'
    assert store.rows.get(generation) == ({'generation': 1} if is_people else None)
    path = ('users', UID, *operation.target.split('/'))
    after = deepcopy(store.rows[path])
    journal = next(
        review_store.decode_doc(UID, row) for key, row in store.rows.items() if key[2:3] == ('review_changes',)
    )
    change = journal['change']
    assert change['edit_kind'] == operation.kind and change['before']
    assert change['context']['segments'][0]['text'] == SPEECH
    review_changes.set_undone(UID, change['change_id'], True)
    assert store.rows.get(generation) == ({'generation': 2} if is_people else None)
    assert store.rows[path] == original
    assert not review_changes.agent_change_allowed(UID, dream_tools.edit_key(operation, seen))
    review_changes.set_undone(UID, change['change_id'], False)
    assert store.rows.get(generation) == ({'generation': 3} if is_people else None)
    assert store.rows[path] == after


@pytest.mark.parametrize('changed', ['row', 'generation', 'account_delete'])
def test_later_user_edit_generation_or_deletion_prevents_cleanup_reversal(store, changed):
    operation = edit('merge_tasks', other='action_items/two')
    seen = records(store)
    dream_tools.apply_edit(UID, operation, seen, expected_records=dream_tools.proposal_fences(UID, {'records': seen}))
    change = next(
        review_store.decode_doc(UID, row)['change']
        for key, row in store.rows.items()
        if key[2:3] == ('review_changes',)
    )
    if changed == 'row':
        store.rows[('users', UID, 'action_items', 'one')]['superseded_by'] = 'a-later-survivor'
    elif changed == 'generation':
        store.rows[('users', UID, 'task_intelligence_control', 'state')]['account_generation'] = 1
    else:
        store.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    before = deepcopy(store.rows[('users', UID, 'action_items', 'one')])
    with pytest.raises((review_store.ReviewConflict, memory_ledger.LegacyCommitPrivacyFence)):
        review_changes.set_undone(UID, change['change_id'], True)
    assert store.rows[('users', UID, 'action_items', 'one')] == before


@pytest.mark.parametrize(
    'field,value',
    [
        ('source', 'manual'),
        ('updated_at', NOW + timedelta(seconds=1)),
        ('apple_reminder_id', 'synthetic-link'),
        ('recurrence_rule', 'FREQ=DAILY'),
    ],
)
def test_user_created_edited_linked_or_recurring_tasks_are_protected(store, field, value):
    seen = records(store)
    seen['action_items/one'][field] = value
    with pytest.raises(ValueError, match='agent_task_user_protected'):
        dream_tools.validate_edit(edit('retire_task'), seen)


@pytest.mark.parametrize(
    'field,value,reason',
    [
        ('started_at', NOW + timedelta(hours=1), 'capture_time_unavailable'),
        ('user_title', 'User kept this recording', 'conversation_user_protected'),
        ('transcript_segments', [{'text': 'Different speech ' * 30}], 'capture_speech_mismatch'),
    ],
)
def test_conversation_merge_requires_unprotected_overlapping_matching_speech(store, field, value, reason):
    seen = records(store)
    seen['conversations/two'][field] = value
    with pytest.raises(ValueError, match=reason):
        dream_tools.validate_edit(edit('merge_conversations', other='conversations/two'), seen)


def test_cleanup_retains_audio_and_survivor_and_never_hard_deletes(store):
    path = ('users', UID, 'conversations', 'one')
    store.rows[path]['audio_files'] = [{'id': 'synthetic-audio'}]
    seen = records(store)
    survivor = deepcopy(store.rows[('users', UID, 'conversations', 'two')])
    dream_tools.apply_edit(UID, edit('merge_conversations', other='conversations/two'), seen)
    assert store.rows[path]['audio_files'] == [{'id': 'synthetic-audio'}]
    assert store.rows[path]['dream_duplicate_of'] == 'two'
    assert 'discarded' not in store.rows[path] and store.rows[path]['status'] == 'completed'
    assert not dream_tools.conversations.is_visible_conversation(store.rows[path])
    assert dream_tools.conversations.is_visible_conversation(store.rows[path], include_discarded=True)
    assert store.rows[('users', UID, 'conversations', 'two')] == survivor


def person_merge_records(store):
    for key, name in [('left', 'Qorbi'), ('right', 'Qorby')]:
        store.rows[('users', UID, 'people', key)] = {
            'id': key,
            'name': name,
            'entity_id': 'person:' + key,
            'type': 'person',
        }
    return records(store)


def person_merge():
    return HarnessEdit(
        kind='merge_people',
        target='people/left',
        other='people/right',
        reason='Synthetic split identity',
        evidence=['conversations/one'],
    )


def test_person_bootstrap_merge_undo_redo_and_visible_survivor(store):
    seen = person_merge_records(store)
    operation = person_merge()
    fences = dream_tools.proposal_fences(UID, {'records': seen})
    assert fences['knowledge_nodes/person:left'] is None
    assert dream_tools.apply_edit(UID, operation, seen, expected_records=fences) == 'applied'
    left = ('users', UID, 'knowledge_nodes', 'person:left')
    right = ('users', UID, 'knowledge_nodes', 'person:right')
    assert store.rows[right]['redirect_entity_id'] == 'person:left'
    journal = next(
        review_store.decode_doc(UID, row) for key, row in store.rows.items() if key[2:3] == ('review_changes',)
    )
    change = journal['change']
    assert change['before'] == 'Qorbi + Qorby' and change['after'] == 'Qorbi'
    assert [ref['id'] for ref in change['refs']] == ['left', 'right']
    after = deepcopy((store.rows[left], store.rows[right]))
    review_changes.set_undone(UID, change['change_id'], True)
    assert 'redirect_entity_id' not in store.rows[right]
    assert 'merged_entity_ids' not in store.rows[left]
    review_changes.set_undone(UID, change['change_id'], False)
    assert (store.rows[left], store.rows[right]) == after


@pytest.mark.parametrize(
    'changed',
    [
        None,
        'id',
        'label',
        'label_lower',
        'node_type',
        'aliases',
        'aliases_lower',
        'memory_ids',
        'redirect_entity_id',
        'merged_entity_ids',
        'extra',
        'person',
        'missing_witness',
    ],
)
def test_person_bootstrap_gate_retry_accepts_only_exact_canonical_nodes(store, monkeypatch, changed):
    seen = person_merge_records(store)
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: records(store).get(ref))
    fences = dream_tools.proposal_fences(UID, {'records': seen})
    fences['people/missing-witness'] = None
    record = review_changes.record_agent_change

    def contend(*args, **kwargs):
        raise DestructiveOperationInProgress('canonical mutation blocked by destructive operation')

    monkeypatch.setattr(review_changes, 'record_agent_change', contend)
    with pytest.raises(DestructiveOperationInProgress):
        dream_tools.apply_verified_edit(UID, person_merge(), seen, expected_records=fences, authority='dream')
    node = store.rows[('users', UID, 'knowledge_nodes', 'person:left')]
    assert node['label'] == 'Qorbi'
    assert not any(key[2:3] == ('review_changes',) for key in store.rows)
    monkeypatch.setattr(review_changes, 'record_agent_change', record)
    if changed == 'person':
        store.rows[('users', UID, 'people', 'left')]['name'] = 'Later synthetic name'
    elif changed == 'missing_witness':
        store.rows[('users', UID, 'people', 'missing-witness')] = {'name': 'New identity'}
    elif changed:
        node[changed] = ['later'] if isinstance(node.get(changed), list) else 'later'

    def retry():
        return dream_tools.apply_verified_edit(
            UID, person_merge(), seen, expected_records=fences, authority='dream', gate_retry=True
        )

    if changed:
        with pytest.raises(review_store.ReviewConflict):
            retry()
        assert not any(key[2:3] == ('review_changes',) for key in store.rows)
    else:
        assert retry() == 'applied'
        assert store.rows[('users', UID, 'knowledge_nodes', 'person:right')]['redirect_entity_id'] == 'person:left'
    assert fences['knowledge_nodes/person:left'] is None


def test_already_merged_person_is_rejected_during_propose_with_actionable_feedback(store):
    import asyncio
    from utils.agent_capabilities.staging import stage

    seen = person_merge_records(store)
    operation = person_merge()
    dream_tools.apply_edit(UID, operation, seen, expected_records=dream_tools.proposal_fences(UID, {'records': seen}))
    with pytest.raises(ValueError, match='agent_person_already_merged'):
        asyncio.run(stage(UID, operation, seen, authority='dream'))


@pytest.mark.parametrize('race', ['node', 'missing_witness'])
def test_person_bootstrap_cannot_bless_post_bootstrap_changes(store, monkeypatch, race):
    seen = person_merge_records(store)
    fences = dream_tools.proposal_fences(UID, {'records': seen})
    fences['people/missing-witness'] = None
    original = review_changes.record_agent_change

    def racing(*args, **kwargs):
        if race == 'node':
            store.rows[('users', UID, 'knowledge_nodes', 'person:left')]['label'] = 'A later edit'
        else:
            store.rows[('users', UID, 'people', 'missing-witness')] = {'name': 'New identity'}
        return original(*args, **kwargs)

    monkeypatch.setattr(review_changes, 'record_agent_change', racing)
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.apply_edit(UID, person_merge(), seen, expected_records=fences)
    assert not any(key[2:3] == ('review_changes',) for key in store.rows)


@pytest.mark.parametrize(
    'field', ['speech_samples', 'speaker_embedding', 'user_confirmed', 'is_user_created', 'pinned', 'label_evidence']
)
def test_autonomous_person_merge_preserves_user_identity(store, field):
    seen = person_merge_records(store)
    seen['people/right'][field] = True
    with pytest.raises(ValueError, match='agent_person_user_protected'):
        dream_tools.validate_edit(person_merge(), seen, authority='dream')
    dream_tools.validate_edit(person_merge(), seen, authority='user')


def test_new_schemas_report_precise_validation_and_keep_bounded_tool_outputs():
    with pytest.raises(ValidationError):
        HarnessEdit(kind='retire_memory', target='memory_items/one', reason=' ', evidence=['conversations/one'])
    with pytest.raises(ValidationError):
        Search(limit=100)
    assert {tool['function']['name'] for tool in tool_schemas()} == {
        'search',
        'read',
        'propose_edit',
        'ask',
        'learn_term',
        'finish',
    }


def test_cleanup_fences_cannot_be_replaced_with_a_newer_target_snapshot(store):
    operation = edit('retire_task')
    seen = records(store)
    fences = dream_tools.proposal_fences(UID, {'records': seen})
    store.rows[('users', UID, 'action_items', 'one')]['description'] = 'Concurrent user change'
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.apply_edit(UID, operation, seen, expected_records=fences)
    assert not store.rows[('users', UID, 'action_items', 'one')].get('deleted')


def test_undo_suppression_keys_ignore_merge_direction_and_optional_before_text(store):
    seen = records(store)
    operation = edit('merge_tasks', other='action_items/two')
    reversed_operation = operation.model_copy(update={'target': operation.other, 'other': operation.target})
    assert dream_tools.edit_key(operation, seen) == dream_tools.edit_key(reversed_operation, seen)
    retirement = edit('retire_task')
    quoted = retirement.model_copy(update={'before': seen[retirement.target]['description']})
    assert dream_tools.edit_key(retirement, seen) == dream_tools.edit_key(quoted, seen)


def test_redo_rejects_a_changed_or_deleted_merge_survivor(store):
    """After Undo, Redo must not restore links to a moved/removed survivor."""
    operation = edit('merge_tasks', other='action_items/two')
    seen = records(store)
    dream_tools.apply_edit(UID, operation, seen, expected_records=dream_tools.proposal_fences(UID, {'records': seen}))
    change = next(
        decoded['change']
        for decoded in (
            review_store.decode_doc(UID, row) for key, row in store.rows.items() if key[2:3] == ('review_changes',)
        )
        if decoded
    )
    review_changes.set_undone(UID, change['change_id'], True)
    store.rows[('users', UID, 'action_items', 'two')]['description'] = 'Edited while undone'
    before = deepcopy(store.rows[('users', UID, 'action_items', 'one')])
    with pytest.raises(review_store.ReviewConflict, match='survivor'):
        review_changes.set_undone(UID, change['change_id'], False)
    assert store.rows[('users', UID, 'action_items', 'one')] == before
    # Restoring the survivor lets Redo proceed.
    store.rows[('users', UID, 'action_items', 'two')]['description'] = seen['action_items/two']['description']
    review_changes.set_undone(UID, change['change_id'], False)
    assert store.rows[('users', UID, 'action_items', 'one')]['superseded_by'] == 'two'


def test_redo_rejects_a_deleted_merge_survivor(store):
    operation = edit('merge_conversations', other='conversations/two')
    seen = records(store)
    dream_tools.apply_edit(UID, operation, seen)
    change = next(
        decoded['change']
        for decoded in (
            review_store.decode_doc(UID, row) for key, row in store.rows.items() if key[2:3] == ('review_changes',)
        )
        if decoded
    )
    review_changes.set_undone(UID, change['change_id'], True)
    del store.rows[('users', UID, 'conversations', 'two')]
    with pytest.raises(review_store.ReviewConflict, match='survivor'):
        review_changes.set_undone(UID, change['change_id'], False)


def test_task_cleanup_and_reversal_bump_the_action_items_list_cache(store, monkeypatch):
    calls = []
    monkeypatch.setattr(review_changes, 'bump_action_items_list_version', lambda uid: calls.append(uid))
    operation = edit('merge_tasks', other='action_items/two')
    seen = records(store)
    dream_tools.apply_edit(UID, operation, seen, expected_records=dream_tools.proposal_fences(UID, {'records': seen}))
    change = next(
        decoded['change']
        for decoded in (
            review_store.decode_doc(UID, row) for key, row in store.rows.items() if key[2:3] == ('review_changes',)
        )
        if decoded
    )
    review_changes.set_undone(UID, change['change_id'], True)
    review_changes.set_undone(UID, change['change_id'], False)
    assert calls == [UID, UID, UID]
