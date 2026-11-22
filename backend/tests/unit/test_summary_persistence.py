"""The actual lifecycle writer emits only after its transaction commits."""

from unittest.mock import Mock
from datetime import datetime, timezone

import pytest
from google.api_core.exceptions import InvalidArgument
from database import conversations as db
from utils.conversations import lifecycle
from utils.conversations import summary_delivery as delivery
from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient, EXPIRED_MESSAGE
from tests.unit.test_process_conversation_free_tier_branch import (
    pc,  # noqa: F401 - real process_conversation with isolated external dependencies
    _existing_desktop,
    _spy_managed_effects,
    _drive_reprocess,
)


@pytest.fixture
def writer(monkeypatch):
    old = {
        'id': 'c',
        'status': 'completed',
        'data_protection_level': 'standard',
        'summary_first_pending_at': 100,
        'summary_due_at': 220,
        'summary_title_provenance': 'server_minimum',
        'sync_content_revision': 3,
    }
    client = _FakeFirestoreClient(old)
    monkeypatch.setattr(db, 'db', client)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _: None)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *_: None)
    return client


def payload(overview='Synthetic real summary'):
    return {
        'id': 'c',
        'status': 'completed',
        'sync_content_revision': 3,
        'data_protection_level': 'standard',
        'structured': {'title': 'Title', 'overview': overview},
    }


def test_terminal_receipt_after_fenced_commit_and_expired_transaction_retry(writer, monkeypatch):
    client = writer
    client.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    receipts = []

    def emit(receipt):
        assert len(client.commits) == 1
        assert client.commits[0]['summary_completed_at']
        receipts.append(receipt)

    monkeypatch.setattr(delivery, 'emit', emit)
    assert db.persist_processing_result_with_lifecycle('u', payload())
    # One expired real transaction, one retry, and the ledger's own noted and
    # done stages in one ledger write.
    assert len(client.commits) == 1 and len(client.ledger_commits) == 1 and len(receipts) == 1
    assert client.ledger_commits[0]['stage'] == 'done' and client.ledger_commits[0]['home_ready_at']
    assert receipts[0]['reason'] == 'summary' and receipts[0]['present']


@pytest.mark.parametrize('record_owner', ['batch_live_v1', 'batch_sync_v1'])
def test_summary_commit_preserves_record_lane_owner(writer, record_owner):
    writer.document['record_lane_owner'] = record_owner
    assert db.persist_processing_result_with_lifecycle('u', {**payload(), 'record_lane_owner': 'legacy_final_pass_v1'})
    assert writer.commits[0]['record_lane_owner'] == record_owner
    assert writer.commits[0]['summary_completed_at']


@pytest.mark.parametrize('sections_only', [False, True])
def test_long_notes_use_the_lifecycle_summary_ledger_writer(writer, sections_only):
    notes = payload()
    # Scaled notes change the body, not the persistence authority or receipt contract.
    notes['transcript_segments'] = [{'start': 0, 'end': 3600, 'text': 'Launch planning. ' * 1500}]
    body = 'The team agreed to validate the launch before sending invitations. ' * 100
    notes['structured'] = {
        'title': 'Launch planning',
        'overview': '' if sections_only else body,
        'sections': [{'title': 'Launch decisions', 'body_markdown': body}] if sections_only else [],
    }
    assert lifecycle.persist_processed_conversation('u', notes)
    assert len(writer.commits) == 1 and len(writer.ledger_commits) == 1
    assert writer.ledger_commits[0]['stage'] == 'done'
    assert writer.ledger_commits[0]['home_ready_at'] >= writer.commits[0]['summary_completed_at']


def test_record_owner_does_not_bypass_summary_processing_fence(writer):
    writer.document.update(record_lane_owner='batch_live_v1', summary_processing_owner='winner')
    token = delivery.PROCESS_CONTEXT.set({'owner': 'loser', 'claimed': True})
    try:
        assert not db.persist_processing_result_with_lifecycle('u', payload())
        assert all(value is None for value in writer.commits)
        assert writer.document['record_lane_owner'] == 'batch_live_v1'
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_empty_model_result_cannot_commit_or_emit(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    with pytest.raises(delivery.SummaryOutputUnavailable):
        db.persist_processing_result_with_lifecycle('u', payload(''))
    assert not writer.commits
    emit.assert_not_called()


def test_empty_model_result_without_open_obligation_commits(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    for marker in ('summary_title_provenance', 'summary_first_pending_at', 'summary_due_at'):
        writer.document.pop(marker, None)
    assert db.persist_processing_result_with_lifecycle('u', payload(''))
    emit.assert_called_once_with(None)


def test_empty_model_result_after_exhausted_empty_budget_commits(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    writer.document['summary_blocked_reason'] = 'empty_output_exhausted'
    writer.document['summary_due_at'] = None
    assert db.persist_processing_result_with_lifecycle('u', payload(''))
    emit.assert_called_once_with(None)


def test_stale_generation_and_failed_commit_emit_nothing(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    assert not db.persist_processing_result_with_lifecycle('u', {**payload(), 'sync_content_revision': 2})
    emit.assert_not_called()
    writer.commit_errors = [RuntimeError('synthetic commit failure')]
    with pytest.raises(RuntimeError):
        db.persist_processing_result_with_lifecycle('u', payload())
    emit.assert_not_called()


@pytest.mark.parametrize('record_owner', ['batch_live_v1', 'batch_sync_v1'])
def test_manual_edit_after_repair_admission_fences_write(writer, monkeypatch, record_owner):
    writer.document.update(user_title='Manually authored title', record_lane_owner=record_owner)
    token = delivery.REPAIR_CONTEXT.set({'summary_expected_revision': 3})
    try:
        assert not db.persist_processing_result_with_lifecycle('u', payload())
        assert all(value is None for value in writer.commits)
    finally:
        delivery.REPAIR_CONTEXT.reset(token)


def test_same_owners_lease_expires_during_long_process_conversation_but_summary_commits(writer, pc, monkeypatch):
    from models.structured import Structured

    # This lease test exercises funded processing, independently of cap admission.
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda uid, lane=None: False)
    _spy_managed_effects(monkeypatch, pc)
    conversation = _existing_desktop('c')
    conversation.sync_content_revision = 3
    clock = [100.0]
    monkeypatch.setattr(delivery, 'time', type('Clock', (), {'time': staticmethod(lambda: clock[0])}))
    writer.document.update(summary_processing_owner='same-owner', summary_processing_lease_until=220)
    context = {'owner': 'same-owner', 'claimed': True, 'lease_until': 220}

    def slow_notes(*_args, **_kwargs):
        clock[0] = 221  # Simulated model latency exceeds the original lease.
        assert writer.document['summary_processing_lease_until'] < clock[0]
        return Structured(title='Synthetic title', overview='Synthetic long-request summary'), False

    monkeypatch.setattr(pc, '_get_structured', slow_notes)
    monkeypatch.setattr(
        pc.lifecycle_service, 'persist_processed_conversation', db.persist_processing_result_with_lifecycle
    )
    token = delivery.PROCESS_CONTEXT.set(context)
    try:
        result = _drive_reprocess(pc, conversation, uid='u')
    finally:
        delivery.PROCESS_CONTEXT.reset(token)
    assert result.structured.overview == 'Synthetic long-request summary'
    assert len(writer.commits) == 1
    assert writer.commits[0]['structured']['overview'] == result.structured.overview
    assert writer.commits[0]['summary_completed_at'] == 221


def test_reprocess_preserves_visible_title_and_refreshes_body(writer):
    writer.document['structured'] = {'title': 'Pilot budget', 'overview': 'Earlier notes'}
    notes = payload('Approval is due Friday.')
    notes['structured']['title'] = 'Launch and approval'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    assert writer.commits[0]['structured']['title'] == 'Pilot budget'
    assert writer.commits[0]['structured']['overview'] == 'Approval is due Friday.'


def test_unsafe_title_repair_records_reason_and_filters_body(writer):
    writer.document['structured'] = {'title': 'Missing transcript', 'overview': 'Old notes'}
    notes = payload('The pilot budget is $8,000. Transcript is missing.')
    notes['structured']['title'] = 'Pilot budget'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    written = writer.commits[0]
    assert written['structured']['title'] == 'Pilot budget'
    assert written['structured']['overview'] == 'The pilot budget is $8,000.'
    assert written['title_change_reason'] == 'invalid_title_repaired'
    assert written['title_changed_at']


def test_user_title_remains_authoritative_even_if_it_mentions_mechanics(writer):
    writer.document.update(user_title='Missing transcript', structured={'title': 'Earlier generated title'})
    assert db.persist_processing_result_with_lifecycle('u', payload())
    assert writer.commits[0]['structured']['title'] == 'Missing transcript'


def test_preserved_title_checkpoints_and_home_projection_match_the_committed_output(writer):
    from datetime import datetime, timezone
    from models.structured import Structured
    from utils.conversations.llm_input_dedupe import NOTES_OUTPUT_HASH, output_fingerprint
    from utils.home_feed.projection import DISPLAY, reveal_display

    writer.document.update(structured={'title': 'Pilot budget'}, started_at=datetime.now(timezone.utc))
    notes = payload('Approval is due Friday.')
    notes['structured']['title'] = 'Rephrased pilot budget'
    notes[NOTES_OUTPUT_HASH] = output_fingerprint(Structured.model_validate(notes['structured']))
    assert db.persist_processing_result_with_lifecycle('u', notes)
    written = writer.commits[0]
    assert written[NOTES_OUTPUT_HASH] == output_fingerprint(Structured.model_validate(written['structured']))
    assert reveal_display('u', written[DISPLAY])['title'] == 'Pilot budget'


@pytest.mark.parametrize('marked', [False, True])
def test_first_real_summary_replaces_provisional_preview_and_home_agrees(writer, marked):
    from utils.home_feed.projection import DISPLAY, reveal_display

    preview = 'We should review the pilot budget before Friday'
    writer.document.update(
        structured={
            'title': ' '.join(preview.split()[:8]),
            **({'title_provenance': 'server_minimum'} if marked else {}),
        },
        transcript_segments=[{'text': preview, 'start': 0, 'end': 5}],
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    notes = payload('Approval is due Friday.')
    notes['structured']['title'] = 'Pilot budget approval'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    written = writer.commits[0]
    assert written['structured']['title'] == 'Pilot budget approval'
    assert reveal_display('u', written[DISPLAY])['title'] == 'Pilot budget approval'
    # A subsequent automatic refresh must retain the first actual headline.
    writer.document.update(written)
    notes['structured']['title'] = 'New wording of the pilot budget'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    assert writer.commits[-1]['structured']['title'] == 'Pilot budget approval'


def test_actual_summary_matching_preview_prefix_still_keeps_its_title(writer):
    speech = 'We should review the pilot budget before Friday'
    title = ' '.join(speech.split()[:8])
    writer.document.update(
        structured={'title': title, 'overview': 'Approval is due Friday.'},
        transcript_segments=[{'text': speech}],
    )
    assert db.persist_processing_result_with_lifecycle('u', payload('Updated supported notes'))
    assert writer.commits[0]['structured']['title'] == title


@pytest.mark.parametrize('units,expected', [(120, 'Pilot budget'), (200, 'Launch decision')])
def test_title_material_boundary_and_reason_use_saved_basis(writer, units, expected):
    writer.document.update(structured={'title': 'Pilot budget', 'overview': 'Earlier notes'}, title_content_units=100)
    notes = payload('The launch was approved.')
    notes.update(content_word_units=units)
    notes['structured']['title'] = 'Launch decision'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    written = writer.commits[0]
    assert written['structured']['title'] == expected
    assert written['title_content_units'] == (100 if units == 120 else 200)
    if units == 200:
        assert written['title_change_reason'] == 'material_content_growth'
        assert written['title_changed_at']


def test_manual_title_wins_even_after_material_growth(writer):
    writer.document.update(user_title='My title', structured={'title': 'My title'}, title_content_units=100)
    notes = payload('The launch was approved.')
    notes.update(content_word_units=200)
    notes['structured']['title'] = 'Launch decision'
    assert db.persist_processing_result_with_lifecycle('u', notes)
    assert writer.commits[0]['structured']['title'] == 'My title'
