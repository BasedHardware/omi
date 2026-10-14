"""Immutable raw speech, encrypted projections, authority and exact product Undo."""

from copy import deepcopy
import asyncio

import pytest

from database import conversations, review_changes, review_store
from models.agent_edit import HarnessEdit
from tests.unit.test_dream_cleanup_edits import store, UID
from utils.agent_capabilities import tools, transcripts
from utils.agent_capabilities.effects import apply_staged
from utils.agent_capabilities.staging import stage


def correction(target='conversations/one#segment-one', **changes):
    return HarnessEdit.model_validate(
        {
            'kind': 'spelling',
            'target': target,
            'before': 'Qorby',
            'after': 'Qorbi',
            'reason': 'Synthetic explicitly spelled name',
            'evidence': ['conversations/one'],
            'value': 4,
            **changes,
        }
    )


def setup(store, monkeypatch):
    row = store.rows[('users', UID, 'conversations', 'one')]
    row.update(
        id='one',
        data_protection_level='enhanced',
        transcript_segments=[
            {
                'id': 'segment-one',
                'text': 'Qorby plans an invented workshop. Qorbi is the spelling.',
                'is_user': True,
                'start': 0,
                'end': 5,
            }
        ],
        structured={'title': 'Qorby workshop', 'overview': 'Qorby plans an invented workshop.'},
    )
    raw = conversations.encode_conversation_for_write(UID, row, 'enhanced')
    store.rows[('users', UID, 'conversations', 'one')] = raw
    monkeypatch.setattr(conversations, 'db', store)

    def seen():
        return conversations.prepare_conversation_for_read(store.rows[('users', UID, 'conversations', 'one')], UID)

    monkeypatch.setattr(tools, 'proposal_record', lambda uid, ref, snapshot: seen())
    return seen, deepcopy(raw)


def test_overlay_leaves_original_ciphertext_immutable_and_undo_marks_entry(store, monkeypatch):
    seen, raw = setup(store, monkeypatch)
    edit = correction()
    assert tools.apply_edit(UID, edit, {'conversations/one': seen()}, authority='dream') == 'applied'
    stored = store.rows[('users', UID, 'conversations', 'one')]
    assert stored['transcript_segments'] == raw['transcript_segments']
    projected = seen()
    assert projected['transcript_segments'][0]['text'].startswith('Qorbi plans')
    assert projected['transcript_segments'][0]['original_text'].startswith('Qorby plans')
    overlay = store.rows[('users', UID, 'transcript_corrections', 'one')]
    assert 'Qorby' not in str(overlay) and 'Qorbi' not in str(overlay)
    entry = review_store.decode_doc(UID, overlay)['source'][0]
    assert entry['source'] == 'dream' and entry['segment_id'] == 'segment-one'
    journal = next(row for path, row in store.rows.items() if path[2:3] == ('review_changes',))
    assert 'Qorby' not in str(journal) and 'Qorbi' not in str(journal)
    change_id = entry['change_id']
    # Unrelated owner metadata survives Undo; transcript corrections own no raw text.
    stored['user_title'] = 'Owner title'
    review_changes.set_undone(UID, change_id, True)
    assert seen()['transcript_segments'][0]['text'].startswith('Qorby plans')
    assert stored['transcript_segments'] == raw['transcript_segments']
    assert review_store.decode_doc(UID, store.rows[('users', UID, 'transcript_corrections', 'one')])['source'][0][
        'undone'
    ]
    review_changes.set_undone(UID, change_id, False)
    assert seen()['transcript_segments'][0]['text'].startswith('Qorbi plans')
    assert not review_changes.agent_change_allowed(UID, tools.edit_key(edit, {'conversations/one': projected}))


def test_reprocessing_storage_never_persists_projected_text(store, monkeypatch):
    seen, raw = setup(store, monkeypatch)
    tools.apply_edit(UID, correction(), {'conversations/one': seen()}, authority='user')
    encoded = conversations.encode_conversation_for_write(UID, seen(), 'enhanced')
    original = conversations.decode_transcript_segments_verified(UID, raw['transcript_segments'], True)
    rewritten = conversations.decode_transcript_segments_verified(UID, encoded['transcript_segments'], True)
    assert rewritten == original
    store.rows[('users', UID, 'conversations', 'one')] = encoded
    entry = review_store.decode_doc(UID, store.rows[('users', UID, 'transcript_corrections', 'one')])['source'][0]
    review_changes.set_undone(UID, entry['change_id'], True)
    assert transcripts.originals(seen()['transcript_segments']) == original


def test_shared_authority_requires_dream_verification_but_user_applies_with_undo(store, monkeypatch):
    seen, raw = setup(store, monkeypatch)
    item = asyncio.run(stage(UID, correction(), {'conversations/one': seen()}, authority='user'))
    assert store.rows[('users', UID, 'conversations', 'one')] == raw
    with pytest.raises(ValueError, match='agent_verification_required'):
        apply_staged(UID, item, authority='dream')
    assert apply_staged(UID, item, authority='user') == 'applied'
    entry = review_store.decode_doc(UID, store.rows[('users', UID, 'transcript_corrections', 'one')])['source'][0]
    assert entry['source'] == 'user'
    review_changes.set_undone(UID, entry['change_id'], True)
    assert seen()['transcript_segments'][0]['text'].startswith('Qorby plans')


def test_original_replacement_blocks_overlay_undo(store, monkeypatch):
    seen, raw = setup(store, monkeypatch)
    tools.apply_edit(UID, correction(), {'conversations/one': seen()})
    entry = review_store.decode_doc(UID, store.rows[('users', UID, 'transcript_corrections', 'one')])['source'][0]
    replacement = {'transcript_segments': [{'id': 'segment-one', 'text': 'Different speech', 'start': 0, 'end': 5}]}
    store.rows[('users', UID, 'conversations', 'one')].update(
        conversations.encode_conversation_for_write(UID, replacement, 'enhanced')
    )
    with pytest.raises(review_store.ReviewConflict, match='Original speech changed'):
        review_changes.set_undone(UID, entry['change_id'], True)


def test_manual_edit_keeps_capture_and_restores_projection_invalidations(store, monkeypatch):
    seen, original = setup(store, monkeypatch)
    raw = store.rows[('users', UID, 'conversations', 'one')]
    raw['client_processing'] = {'synthetic': True}
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    assert (
        conversations.update_conversation_segment_text(
            UID, 'one', 'segment-one', 'Owner corrected synthetic workshop text.', firestore_client=store
        )
        == 'ok'
    )
    assert raw['transcript_segments'] == original['transcript_segments']
    assert 'client_processing' not in raw
    assert seen()['transcript_segments'][0]['text'] == 'Owner corrected synthetic workshop text.'
    journal = next(row for path, row in store.rows.items() if path[2:3] == ('review_changes',))
    assert 'Owner corrected' not in str(journal)
    change_id = review_store.decode_doc(UID, journal)['change']['change_id']
    first = review_changes.set_undone(UID, change_id, True)
    assert review_changes.set_undone(UID, change_id, True) == first
    assert raw['client_processing'] == {'synthetic': True}
    assert 'has_user_transcript_corrections' not in raw
    assert seen()['transcript_segments'][0]['text'].startswith('Qorby')
    review_changes.set_undone(UID, change_id, False)
    assert seen()['transcript_segments'][0]['text'] == 'Owner corrected synthetic workshop text.'
