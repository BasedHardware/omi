"""Exercise the apply boundary and storage encoding with synthetic records."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import review_changes, review_store
from tests.unit.test_dream_cleanup_edits import store, UID
from models.dream_edit import Edit
from utils.agent_capabilities import tools as dream_tools, transcripts


def spelling(target='conversations/c1'):
    return Edit(
        kind='spelling',
        target=target,
        before='Alise',
        after='Alice',
        reason='Supported name correction',
        evidence=[target],
    )


def test_undo_marker_prevents_journal_and_mutation(monkeypatch):
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: False)

    def forbidden(*a, **k):
        pytest.fail('blocked edit reached mutation')

    monkeypatch.setattr(review_changes, 'record_agent_change', forbidden)
    assert dream_tools.apply_edit('synthetic', spelling(), {'conversations/c1': {}}) == 'suppressed'


def test_semantic_key_is_stable_and_merge_direction_independent():
    edit = spelling()
    assert dream_tools.edit_key(edit) == dream_tools.edit_key(edit.model_copy(update={'reason': 'Another explanation'}))
    merge = Edit(
        kind='merge_people',
        target='entity/person:a',
        other='entity/person:b',
        reason='Duplicate',
        evidence=['entity/person:a'],
    )
    assert dream_tools.edit_key(merge) == dream_tools.edit_key(
        merge.model_copy(update={'target': merge.other, 'other': merge.target})
    )


def test_transcript_fix_uses_immutable_overlay_and_snapshot_fence(store, monkeypatch):
    uid = UID
    row = {
        'id': 'c1',
        'data_protection_level': 'enhanced',
        'structured': {
            'title': 'Alise meeting',
            'overview': 'Alise discussed Widgets',
            'sections': [{'heading': 'Alise meeting', 'body_markdown': 'Alise met us', 'source_segment_ids': ['s1']}],
            'note_claims': [],
        },
        'transcript_segments': [{'id': 's1', 'text': 'Alise said hi', 'start': 0, 'end': 1}],
        'client_processing': {'old': 'projection'},
    }
    stored = dream_tools.conversations.encode_conversation_for_write(uid, row, 'enhanced')
    store.rows[('users', uid, 'conversations', 'c1')] = deepcopy(stored)
    monkeypatch.setattr(dream_tools.conversations, 'db', store)
    assert dream_tools.apply_edit(uid, spelling(), {'conversations/c1': deepcopy(row)}) == 'applied'
    persisted = store.rows[('users', uid, 'conversations', 'c1')]
    assert persisted['transcript_segments'] == stored['transcript_segments']
    decoded = dream_tools.conversations.prepare_conversation_for_read(persisted, uid)
    assert decoded['transcript_segments'][0]['text'] == 'Alice said hi'
    assert decoded['transcript_segments'][0]['original_text'] == 'Alise said hi'
    assert decoded['structured']['title'] == 'Alice meeting'
    assert decoded['structured']['overview'] == row['structured']['overview']
    assert decoded['structured']['sections'] == row['structured']['sections']
    assert 'client_processing' not in decoded
    journal = next(
        review_store.decode_doc(uid, value) for path, value in store.rows.items() if path[2:3] == ('review_changes',)
    )
    from utils.agent_capabilities.transcripts import original_fingerprint

    assert journal['transcript_overlay']['original_fingerprint'] == original_fingerprint(uid, stored)
    review_changes.set_undone(uid, journal['change']['change_id'], True)
    assert (
        transcripts.originals(
            dream_tools.conversations.prepare_conversation_for_read(persisted, uid)['transcript_segments']
        )
        == row['transcript_segments']
    )


def test_concurrent_transcript_correction_is_refused(monkeypatch):
    row = {'id': 'c1', 'transcript_segments': [{'id': 's1', 'text': 'Old'}], 'structured': {}}
    raw = dict(row, transcript_segments=[{'id': 's1', 'text': 'User corrected'}])
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: raw))
    monkeypatch.setattr(
        review_store,
        'user',
        lambda uid: SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: ref)),
    )
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    with pytest.raises(review_store.ReviewConflict):
        dream_tools.apply_edit('synthetic', spelling(), {'conversations/c1': row})


def test_memory_fix_goes_through_memory_edit(monkeypatch):
    captured = []
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **k: captured.append((a, k)))
    edit = spelling('memory_items/m1')
    dream_tools.apply_edit('synthetic', edit, {edit.target: {'content': 'Alise prefers Widgets'}})
    assert captured[0][1]['memory_edit'].content == 'Alice prefers Widgets'
    assert captured[0][0][2] == []


def test_name_substitution_preserves_ids_and_boundaries():
    value = {
        'title': 'Alise',
        'sections': [{'text': 'Alise uses Alise2', 'source_segment_ids': ['Alise']}],
        'id': 'Alise',
    }
    result = dream_tools._replace_tree(value, 'Alise', 'Alice')
    assert result['id'] == 'Alise'
    assert result['sections'][0]['text'] == 'Alice uses Alise2'
    assert result['sections'][0]['source_segment_ids'] == ['Alise']


def test_memory_merge_key_survives_new_tail_ids_after_undo():
    edit = Edit(
        kind='merge_memories',
        target='memory_items/one',
        other='memory_items/two',
        after='Merged',
        reason='Duplicate',
        evidence=['memory_items/one'],
    )
    records = {
        edit.target: {'content': 'Synthetic fact', 'subject_entity_id': 'person:p'},
        edit.other: {'content': 'Same synthetic fact', 'subject_entity_id': 'person:p'},
    }
    original_key = dream_tools.edit_key(edit, records)
    later = edit.model_copy(update={'target': 'memory_items/undo-tail-1', 'other': 'memory_items/undo-tail-2'})
    tails = {later.target: records[edit.target], later.other: records[edit.other]}
    assert dream_tools.edit_key(later, tails) == original_key


def test_memory_correction_key_survives_undo_tail_and_tool_kind_changes():
    edit = spelling('memory_items/original')
    row = {
        'content': 'Alise prefers Widgets',
        'subject_scope': 'primary_user',
        'subject_entity_id': None,
        'slot': 'preference',
        'visibility': 'private',
    }
    original = dream_tools.edit_key(edit, {edit.target: row})
    tail = edit.model_copy(update={'target': 'memory_items/undo-tail'})
    assert original == dream_tools.edit_key(tail, {tail.target: row})
    rewrite = tail.model_copy(update={'kind': 'memory', 'before': '', 'after': 'Alice prefers Widgets'})
    assert original == dream_tools.edit_key(rewrite, {rewrite.target: row})
    assert original.startswith('agent:memory:')
    changed = dict(row, content='Alise now prefers Robots')
    assert original != dream_tools.edit_key(tail, {tail.target: changed})


@pytest.mark.parametrize('fragment', ['s1', '12.5', '00:00:12.5'])
def test_fragment_spelling_only_changes_selected_segment_and_journals_scope(store, monkeypatch, fragment):
    uid = UID
    row = {
        'id': 'c1',
        'data_protection_level': 'enhanced',
        'user_title': 'Alise meeting',
        'structured': {'title': 'Alise meeting'},
        'transcript_segments': [
            {'id': 's1', 'start': 12.5, 'end': 15, 'text': 'Alise met Alise.'},
            {'id': 's2', 'start': 20, 'end': 22, 'text': 'Alise elsewhere.'},
        ],
    }
    stored = dream_tools.conversations.encode_conversation_for_write(uid, row, 'enhanced')
    store.rows[('users', uid, 'conversations', 'c1')] = deepcopy(stored)
    monkeypatch.setattr(dream_tools.conversations, 'db', store)
    edit = spelling('conversations/c1#' + fragment)
    records = {'conversations/c1': deepcopy(row)}
    assert dream_tools.apply_edit(uid, edit, records) == 'applied'
    raw = store.rows[('users', uid, 'conversations', 'c1')]
    assert raw['transcript_segments'] == stored['transcript_segments']
    decoded = dream_tools.conversations.prepare_conversation_for_read(raw, uid)
    assert decoded['transcript_segments'][0]['text'] == 'Alice met Alice.'
    assert decoded['transcript_segments'][1] == {
        **row['transcript_segments'][1],
        'original_text': row['transcript_segments'][1]['text'],
    }
    assert decoded['structured'] == row['structured'] and decoded['user_title'] == row['user_title']
    journal = next(
        review_store.decode_doc(uid, value) for path, value in store.rows.items() if path[2:3] == ('review_changes',)
    )
    assert journal['transcript_overlay']['before'] == {'client_processing': {'present': False}}
    assert journal['transcript_overlay']['after'] == {'client_processing': {'present': False}}
    assert len(journal['transcript_overlay']['corrections']) == 1
    assert journal['change']['refs'][0]['label'] == 'Conversation #' + fragment
    alias = edit.model_copy(update={'target': 'conversations/c1#s1'})
    assert dream_tools.edit_key(edit, records) == dream_tools.edit_key(alias, records)
    review_changes.set_undone(uid, journal['change']['change_id'], True)
    assert (
        transcripts.originals(dream_tools.conversations.prepare_conversation_for_read(raw, uid)['transcript_segments'])
        == row['transcript_segments']
    )


@pytest.mark.parametrize('fragment', ['unknown', '', '20'])
def test_invalid_or_wrong_segment_spelling_cannot_widen_target(fragment):
    records = {
        'conversations/c1': {
            'transcript_segments': [
                {'id': 's1', 'start': 12.5, 'text': 'Alise here.'},
                {'id': 's2', 'start': 20, 'text': 'Different name.'},
            ]
        }
    }
    with pytest.raises(ValueError, match='agent_target_(term_missing|quote_mismatch)'):
        dream_tools.validate_edit(spelling('conversations/c1#' + fragment), records)
