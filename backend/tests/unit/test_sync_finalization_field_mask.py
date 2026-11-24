"""Keep the Go ordinary-sync persist mask tied to the Python payload builder."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from models.conversation import Conversation
from routers.sync_finalization_reference import _notes_source_projection, _notes_title_evidence
from utils.conversations import process_conversation as processor, sync_notes_request
from utils.conversations.process_conversation import _normal_persist_payload


def test_go_sync_field_mask_covers_python_persist_payload():
    contract = Path(__file__).resolve().parents[3] / 'backend-go/internal/adapters/conversations/sync_field_mask.json'
    mask = json.loads(contract.read_text(encoding='utf-8'))
    conversation = Conversation(
        id='synthetic-sync-mask',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=None,
        finished_at=None,
        structured={},
    )
    payload = _normal_persist_payload(conversation, clear_terminal_marker=True)
    groups = [set(keys) for name, keys in mask.items() if name != 'conditional_fields']
    covered = set().union(*groups)
    assert sum(map(len, groups)) == len(covered), 'A field belongs to one group'
    assert payload.keys() == covered
    # JSON preserves the distinction between false, zero, null and an empty list.
    actual_defaults = {key: payload[key] for key in mask['defaults']}
    assert json.dumps(actual_defaults, sort_keys=True) == json.dumps(mask['defaults'], sort_keys=True)

    pending = conversation.model_copy(update={'processing_state': 'local_pending', 'summary_retryable': True})
    clearing = _normal_persist_payload(pending, clear_terminal_marker=True)
    assert clearing.keys() - covered == set(mask['conditional_fields'])
    assert all(clearing[key] is None for key in mask['conditional_fields'])


def test_notes_source_projection_preserves_sync_tail_and_arrival():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(seconds=42)
    arrival = end + timedelta(hours=1)
    conversation = Conversation(
        id='synthetic-source',
        created_at=start,
        started_at=start,
        finished_at=end,
        arrival_at=arrival,
        sync_content_revision=3,
        structured={},
        transcript_segments=[{'text': '日本語 report', 'start': 2, 'end': 10, 'is_user': True}],
    )
    assert _notes_source_projection(conversation) == {
        'recorded_start': (start + timedelta(seconds=2)).isoformat(),
        'recorded_end': end.isoformat(),
        'arrival_at': arrival.isoformat(),
        'clock': 'device',
        'content_word_units': 4,
    }


def test_notes_title_evidence_recognizes_provisional_and_owner_titles():
    from types import SimpleNamespace

    text = 'these are the first eight words of speech with more'
    conversation = SimpleNamespace(transcript_segments=[{'text': text}])
    row = {'structured': {'title': ' '.join(text.split()[:8])}, 'title_content_units': 21}
    assert _notes_title_evidence(row, conversation) == {'prior': '', 'valid_prior': '', 'previous_units': 21}
    row['structured'] = {'title': 'Prior plan', 'overview': 'Notes'}
    assert _notes_title_evidence(row, conversation) == {
        'prior': 'Prior plan', 'valid_prior': 'Prior plan', 'previous_units': 21,
    }
    assert _notes_title_evidence({**row, 'user_title': 'My title'}, conversation) is None


@pytest.mark.parametrize('texts', [[], ['']], ids=['empty-capture', 'transcript-empty-text'])
def test_empty_ordinary_sync_notes_use_python_discard_rule(monkeypatch, texts):
    monkeypatch.setattr(sync_notes_request, 'get_conversation_photos', lambda *args, **kwargs: [])
    monkeypatch.setattr(processor, '_calendar_overlap_retains_conversation', lambda *args: False)
    monkeypatch.setattr(
        sync_notes_request, 'one_shot_notes_messages', lambda *args, **kwargs: pytest.fail('discard must skip notes')
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id='synthetic-empty',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured={},
        transcript_segments=[{'text': text, 'start': 0, 'end': 2, 'is_user': True} for text in texts],
    )
    minimum = sync_notes_request.notes_request(None, 'synthetic-owner', conversation, user_kept=False)['minimum']
    assert minimum['title'] == ''
    assert minimum['discarded'] is True
    assert minimum['reason'] == 'empty_transcript'
