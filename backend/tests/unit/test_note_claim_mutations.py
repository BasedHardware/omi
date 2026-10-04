"""Provenance follows visible-field replacement and source correction."""

from copy import deepcopy

from utils.conversations.note_claim_mutations import (
    apply_user_title,
    invalidate_note_claims,
    prepare_generated_note,
    summary_source_reference_invalidations,
)
from database.conversation_mutations import _apply_operation
from utils.conversations.render import redact_conversation_for_list, redact_conversation_for_integration


def claims():
    return [
        {'target': target, 'text': 'Original', 'evidence_ids': ['speech:s1'], 'provenance': 'said', 'private': False}
        for target in ('/title', '/overview', '/sections/0/body_markdown', '/action_items/0/description')
    ]


def test_user_title_override_preserves_unrelated_claims_and_is_copy_safe():
    data = {'structured': {'title': 'Generated', 'note_claims': claims()}}
    apply_user_title(data, 'Manual')
    assert data['structured']['title'] == 'Manual'
    assert data['structured']['note_claims'] == claims()[1:]


def test_generated_replacement_clears_old_annotations_when_flag_off():
    sentinel = object()
    previous = {'structured': {'note_claims': claims()}, 'user_title': 'Manual'}
    incoming = {'structured': {'title': 'Generated', 'overview': 'Fresh'}}
    prepare_generated_note(incoming, previous, sentinel)
    assert incoming['structured']['title'] == 'Manual'
    assert incoming['structured']['note_claims'] is sentinel
    incoming = {'structured': {'title': 'Generated', 'note_claims': claims()}}
    prepare_generated_note(incoming, previous, sentinel)
    assert incoming['structured']['note_claims'] == claims()[1:]


def test_offline_sync_title_operation_invalidates_claims_atomically():
    old = {'structured': {'title': 'Old', 'note_claims': claims()}}
    state, patch = _apply_operation(old, {'type': 'set_title', 'title': 'New'})
    assert patch['structured.title'] == state['structured']['title'] == 'New'
    assert patch['structured.note_claims'] == state['structured']['note_claims'] == claims()[1:]
    assert old['structured']['note_claims'] == claims()


def test_transcript_edit_invalidates_only_claims_using_edited_speech():
    old = claims()
    other = deepcopy(old[0])
    other['evidence_ids'] = ['speech:s2']
    result = summary_source_reference_invalidations({'note_claims': old + [other]}, 's1')
    assert result == {'structured.note_claims': [other]}
    assert old == claims()


def test_locked_projection_does_not_keep_removed_prose_claims():
    data = {'is_locked': True, 'structured': {'note_claims': claims()}}
    listed = redact_conversation_for_list(deepcopy(data))
    assert listed['structured']['note_claims'] == claims()[:3]
    integrated = redact_conversation_for_integration(deepcopy(data))
    assert integrated['structured']['note_claims'] == []


def test_legacy_structures_stay_metadata_free():
    old = {'title': 'Old'}
    assert not invalidate_note_claims(old, ('/title',))
    assert old == {'title': 'Old'}
