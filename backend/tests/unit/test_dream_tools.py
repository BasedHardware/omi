"""Exercise the apply boundary and storage encoding with synthetic records."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import review_changes, review_store
from models.dream_agent import Edit
from utils import dream_tools


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


def test_transcript_fix_uses_encoded_reversible_patch_and_snapshot_fence(monkeypatch):
    uid = 'synthetic'
    row = {
        'id': 'c1',
        'data_protection_level': 'enhanced',
        'structured': {
            'title': 'Alise meeting',
            'overview': 'Alise discussed Widgets',
            'sections': [{'text': 'Alise met us', 'source_segment_ids': ['s1']}],
            'note_claims': [],
        },
        'transcript_segments': [{'id': 's1', 'text': 'Alise said hi', 'start': 0, 'end': 1}],
        'client_processing': {'old': 'projection'},
    }
    stored = dream_tools.conversations.encode_conversation_for_write(uid, row, 'enhanced')
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: deepcopy(stored)))
    monkeypatch.setattr(
        review_store,
        'user',
        lambda uid: SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: ref)),
    )
    monkeypatch.setattr(review_changes, 'agent_change_allowed', lambda *a: True)
    captured = []
    monkeypatch.setattr(review_changes, 'record_agent_change', lambda *a, **k: captured.append((a, k)))
    result = dream_tools.apply_edit(uid, spelling(), {'conversations/c1': deepcopy(row)})
    assert result == 'applied'
    args, kwargs = captured[0]
    patch = args[2][0].patch
    assert isinstance(patch['transcript_segments'], str)
    decoded = dream_tools.conversations.prepare_conversation_for_read(dict(stored, **patch), uid)
    assert decoded['transcript_segments'][0]['text'] == 'Alice said hi'
    assert decoded['structured']['title'] == 'Alice meeting'
    assert decoded['structured']['overview'] == 'Alice discussed Widgets'
    assert decoded['structured']['sections'][0]['source_segment_ids'] == []
    assert patch['client_processing'] is None
    assert kwargs['expected_documents'] == {'c1': stored}
    assert set(patch) <= review_changes.ALLOWED_FIELDS['conversations']


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
