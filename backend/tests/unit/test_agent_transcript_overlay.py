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
from utils.agent_capabilities.session import Session
from utils.agent_capabilities.limits import SessionLimits


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


def test_correction_anchor_guard_permits_append_but_refuses_text_replacement_or_reorder():
    original = [{'id': 'one', 'start': 0, 'end': 5, 'text': 'Synthetic captured speech'}]
    entries = [{'segment_index': 0, 'undone': False}]
    appended = [*original, {'id': 'two', 'start': 5, 'end': 10, 'text': 'Later speech'}]
    assert transcripts.preserves_correction_anchors(original, appended, entries)
    assert not transcripts.preserves_correction_anchors(original, list(reversed(appended)), entries)
    assert not transcripts.preserves_correction_anchors(original, [{**original[0], 'text': 'Replacement'}], entries)


def test_undo_survives_unrelated_captured_speech_append(store, monkeypatch):
    seen, _ = setup(store, monkeypatch)
    edit = correction()
    tools.apply_edit(UID, edit, {'conversations/one': seen()}, authority='dream')
    path = ('users', UID, 'conversations', 'one')
    current = deepcopy(store.rows[path])
    captured = conversations.decode_transcript_segments_verified(UID, current['transcript_segments'], True)
    captured.append({'id': 'two', 'start': 6, 'end': 9, 'text': 'Unrelated appended speech'})
    encoded = conversations.encode_conversation_for_write(UID, {'transcript_segments': captured}, 'enhanced')
    store.rows[path].update(encoded)
    journal = next(
        review_store.decode_doc(UID, row)['change']
        for key, row in store.rows.items()
        if key[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, journal['change_id'], True)
    projected = seen()['transcript_segments']
    assert projected[0]['text'].startswith('Qorby') and projected[1]['text'] == 'Unrelated appended speech'


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


def test_processor_preserves_exact_legacy_capture_and_its_projection(store, monkeypatch):
    from database.conversations import _protect_json_value
    from models.transcript_segment import legacy_conversation_segment_id

    seen, _ = setup(store, monkeypatch)
    path = ('users', UID, 'conversations', 'one')
    captured = [{'text': 'Qorby plans a synthetic workshop.', 'start': 0, 'end': 5}]
    store.rows[path]['transcript_segments'] = _protect_json_value(captured, UID, 'enhanced')
    before = deepcopy(store.rows[path])
    assert (
        conversations.update_conversation_segment_text(
            UID,
            'one',
            legacy_conversation_segment_id('one', 0),
            'Qorbi plans a synthetic workshop.',
            firestore_client=store,
        )
        == 'ok'
    )
    candidate = conversations.encode_conversation_for_write(UID, seen(), 'enhanced')
    conversations._reapply_current_manual_assignments(UID, candidate, store.rows[path])
    assert candidate['transcript_segments'] == before['transcript_segments']
    assert candidate['transcript_segments_compressed'] == before['transcript_segments_compressed']
    store.rows[path].update(candidate)
    assert seen()['transcript_segments'][0]['text'].startswith('Qorbi')
    assert (
        conversations.decode_transcript_segments_verified(UID, store.rows[path]['transcript_segments'], True)
        == captured
    )


def test_translation_binds_to_corrected_speech_and_undo_hides_stale_translation(store, monkeypatch):
    seen, raw = setup(store, monkeypatch)
    tools.apply_edit(UID, correction(), {'conversations/one': seen()}, authority='user')
    corrected = seen()['transcript_segments'][0]['text']
    materialized = conversations.materialize_translation(
        UID, 'one', 'segment-one', corrected, 'xx', 'Synthetic translated corrected speech', firestore_client=store
    )
    assert materialized['text'] == corrected and materialized['original_text'].startswith('Qorby')
    assert seen()['transcript_segments'][0]['translations'][0]['text'] == 'Synthetic translated corrected speech'
    journal = next(
        review_store.decode_doc(UID, row)['change']
        for path, row in store.rows.items()
        if path[2:3] == ('review_changes',)
    )
    review_changes.set_undone(UID, journal['change_id'], True)
    assert not seen()['transcript_segments'][0]['translations']
    captured = conversations.decode_transcript_segments_verified(
        UID, store.rows[('users', UID, 'conversations', 'one')]['transcript_segments'], True
    )
    assert captured[0]['text'].startswith('Qorby')


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


def test_user_request_updates_populated_title_with_review_disabled_and_keeps_undo(store, monkeypatch):
    seen, _ = setup(store, monkeypatch)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    operation = correction(
        kind='title', target='conversations/one', before='Qorby workshop', after='Owner chosen title'
    )
    item = asyncio.run(stage(UID, operation, {'conversations/one': seen()}, authority='user'))
    assert apply_staged(UID, item, authority='user') == 'applied'
    assert seen()['structured']['title'] == 'Owner chosen title'
    journal = next(row for path, row in store.rows.items() if path[2:3] == ('review_changes',))
    change = review_store.decode_doc(UID, journal)['change']
    assert change['before'] == 'Qorby workshop' and change['after'] == 'Owner chosen title'
    review_changes.set_undone(UID, change['change_id'], True)
    assert seen()['structured']['title'] == 'Qorby workshop'
    with pytest.raises(review_store.ReviewConflict, match='review_surface_disabled'):
        review_store.require_enabled(UID)


def test_user_authority_does_not_grant_review_access_to_another_owner(monkeypatch):
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    with review_store.user_request_authority(UID):
        review_store.require_enabled(UID)
        with pytest.raises(review_store.ReviewConflict, match='review_surface_disabled'):
            review_store.require_enabled('synthetic-other-owner')
        with pytest.raises(review_store.ReviewConflict, match='review_surface_disabled'):
            review_store.require_enabled()
    with pytest.raises(review_store.ReviewConflict, match='review_surface_disabled'):
        review_store.require_enabled(UID)


@pytest.mark.asyncio
async def test_immediate_user_edits_still_obey_the_session_edit_cap(store, monkeypatch):
    seen, _ = setup(store, monkeypatch)
    session = Session(
        UID,
        source=None,
        limits=SessionLimits(edits=1),
        seed={},
        authority='user',
        records={'conversations/one': seen()},
    )
    first = correction(kind='title', target='conversations/one', before='Qorby workshop', after='Owner title')
    assert (await session.propose(first))['status'] == 'applied'
    session.records['conversations/one'] = seen()
    second = first.model_copy(update={'before': 'Owner title', 'after': 'Another owner title'})
    with pytest.raises(ValueError, match='agent_edit_cap'):
        await session.propose(second)
    assert seen()['structured']['title'] == 'Owner title'


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


def test_legacy_in_place_receipt_stays_undoable_after_dependent_overlay_is_undone(store, monkeypatch):
    from datetime import datetime, timezone
    from models.review import ReviewChange
    from database.review_changes import AgentEdit

    seen, _ = setup(store, monkeypatch)
    path = ('users', UID, 'conversations', 'one')
    speech = [{'id': 'segment-one', 'start': 0, 'end': 5, 'text': 'Qorby plans. Qorbix is the correct spelling.'}]
    store.rows[path].update(
        conversations.encode_conversation_for_write(UID, {'transcript_segments': speech}, 'enhanced')
    )
    original = deepcopy(store.rows[path]['transcript_segments'])
    historical = deepcopy(speech)
    historical[0]['text'] = historical[0]['text'].replace('Qorby', 'Qorbi')
    encoded = conversations.encode_conversation_for_write(UID, {'transcript_segments': historical}, 'enhanced')
    legacy = ReviewChange(
        change_id='synthetic-old-receipt',
        kind='rename',
        title='Legacy correction',
        created_at=datetime.now(timezone.utc),
    )
    review_changes.record_agent_change(
        UID,
        legacy,
        [
            AgentEdit(
                collection='conversations',
                document_id='one',
                patch={'transcript_segments': encoded['transcript_segments']},
            )
        ],
        edit_key='synthetic-legacy-key',
    )
    tools.apply_edit(UID, correction(before='Qorbi', after='Qorbix'), {'conversations/one': seen()}, authority='user')
    overlay = review_store.decode_doc(UID, store.rows[('users', UID, 'transcript_corrections', 'one')])['source'][0]
    with pytest.raises(review_store.ReviewConflict, match='dependent newer correction'):
        review_changes.set_undone(UID, legacy.change_id, True)
    review_changes.set_undone(UID, overlay['change_id'], True)
    review_changes.set_undone(UID, legacy.change_id, True)
    assert store.rows[path]['transcript_segments'] == original


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
