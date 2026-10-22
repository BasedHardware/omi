from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.llm import action_item_v2 as v2
from utils.conversations import action_item_extraction as extraction


@pytest.fixture(autouse=True)
def profile(monkeypatch):
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda *_: 'Riley Vale')


def test_offer_to_owner_admitted_without_reattributing_promisor(monkeypatch):
    offered = {
        'description': 'Review the resume',
        'owner_name': 'Morgan',
        'capture_kind': 'clear_commitment',
        'context': 'Morgan offered a resume review to Riley',
    }
    unrelated = {
        'description': 'Ask Riley to review the resume',
        'owner_name': 'Morgan',
        'capture_kind': 'clear_commitment',
        'context': 'Morgan needs a review from Riley',
    }
    assert extraction.filter_extracted_items('synthetic-owner', [offered, unrelated]) == []
    monkeypatch.setenv(v2.FLAG, 'serve')
    assert extraction.filter_extracted_items('synthetic-owner', [offered, unrelated]) == [offered]
    assert offered['owner_name'] == 'Morgan'


@pytest.mark.parametrize(
    'owner,kind,due,kept',
    [
        (None, None, None, False),
        ('Riley', 'inferred_next_step', None, False),
        ('Riley', 'clear_commitment', None, True),
        (None, None, datetime(2026, 1, 1, tzinfo=timezone.utc), True),
    ],
)
def test_vague_social_smalltalk_needs_a_committed_owner_or_time(monkeypatch, owner, kind, due, kept):
    monkeypatch.setenv(v2.FLAG, 'serve')
    item = {'description': 'Go hiking together', 'owner_name': owner, 'capture_kind': kind, 'due_at': due}
    assert bool(extraction.filter_extracted_items('synthetic-owner', [item])) is kept


def test_stale_requires_exact_recording_and_actual_transcript():
    task = {'capture_gap_conversation_id': 'call-1', 'conversation_id': 'complaint-1', 'status': 'active'}
    captured = SimpleNamespace(id='call-1', is_call=True, transcript_segments=[object()])
    patch = v2.contradicted_capture(task, captured)
    assert patch['stale_reason'] == 'referenced_call_capture_exists'
    assert patch['status'] == 'cancelled'
    assert task['conversation_id'] == 'complaint-1'
    assert v2.contradicted_capture({**task, 'capture_gap_conversation_id': 'other'}, captured) is None
    assert v2.contradicted_capture({**task, 'completed': True}, captured) is None
    captured.transcript_segments = []
    assert v2.contradicted_capture(task, captured) is None


def test_provenance_cannot_be_overridden_by_projection(monkeypatch):
    monkeypatch.setenv(v2.FLAG, 'serve')
    item = SimpleNamespace(
        description='Send the file',
        completed=False,
        created_at=None,
        updated_at=None,
        due_at=None,
        completed_at=None,
        owner_name='Riley',
    )
    conversation = SimpleNamespace(
        id='conversation-1', is_locked=False, structured=SimpleNamespace(action_items=[item])
    )
    rows = extraction.action_items_for_write(
        'synthetic-owner', conversation, datetime.now(timezone.utc), lambda *_: {'conversation_id': None}
    )
    assert rows[0]['conversation_id'] == 'conversation-1'


def test_media_suppression_is_v2_gated(monkeypatch):
    conversation = SimpleNamespace(id='conversation-1', content_kind='media')
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    assert (
        extraction.action_items_for_write('synthetic-owner', conversation, datetime.now(timezone.utc), lambda *_: {})
        == []
    )


def test_prompt_changes_serve_only(monkeypatch):
    assert v2.rules_for('synthetic-owner', 'legacy') == 'legacy'
    monkeypatch.setenv(v2.FLAG, 'serve')
    assert 'offers/promises by another person to the owner' in v2.rules_for('synthetic-owner', 'legacy')


def test_notes_task_block_swap_is_idempotent_and_keeps_other_rules(monkeypatch):
    from utils.llm.conversation_notes_prompts import ACTION_ITEM_EXTRACTION_RULES

    prompt = 'Existing notes rules\n' + ACTION_ITEM_EXTRACTION_RULES + '\nExisting speaker rules'
    assert v2.instructions_for('synthetic-owner', prompt) == prompt
    monkeypatch.setenv(v2.FLAG, 'serve')
    selected = v2.instructions_for('synthetic-owner', prompt)
    assert selected == 'Existing notes rules\n' + v2.RULES + '\nExisting speaker rules'
    assert v2.instructions_for('synthetic-owner', selected) == selected
