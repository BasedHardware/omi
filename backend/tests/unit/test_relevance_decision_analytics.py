"""Content-free analytics for the final persisted relevance outcome."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import RelevanceDecision, final_relevance


@pytest.fixture
def relevance_io():
    # Neighbor lookup dependencies are irrelevant to the capture boundary.
    with stub_modules({'database.conversations': AutoMockModule('database.conversations')}):
        module = load_module_fresh(
            'utils.conversations.relevance_io',
            Path(__file__).resolve().parents[2] / 'utils/conversations/relevance_io.py',
        )
        yield module


@pytest.mark.parametrize(
    'verdict,reason,arm',
    [
        ('keep', 'keep_all_arm', 'keep_all'),
        ('discard', 'jev_discard', 'jev'),
        ('keep', 'jev_keep', 'jev'),
        ('discard', 'model_discard', None),
    ],
)
def test_emits_one_content_free_final_decision(relevance_io, monkeypatch, verdict, reason, arm):
    capture = Mock()
    monkeypatch.setattr(relevance_io, 'emit_posthog_event', capture)
    decision = RelevanceDecision(verdict, 'model', reason, ProcessingTrigger.SYNC_UPDATE, arm=arm)

    relevance_io.emit_recorded_decision('user-id', 'conversation-id', decision)

    properties = {'conversation_id': 'conversation-id', 'reason': reason, 'discarded': verdict == 'discard'}
    if arm is not None:
        properties['arm'] = arm
    capture.assert_called_once_with('user-id', 'Relevance Decision Recorded', properties)


def test_structuring_override_emits_the_final_discard(relevance_io, monkeypatch):
    capture = Mock()
    monkeypatch.setattr(relevance_io, 'emit_posthog_event', capture)
    decision = RelevanceDecision('keep', 'jev', 'jev_keep', ProcessingTrigger.SYNC_UPDATE, arm='jev')

    relevance_io.emit_recorded_decision('user-id', 'conversation-id', final_relevance(decision, discarded=True))

    capture.assert_called_once_with(
        'user-id',
        'Relevance Decision Recorded',
        {'conversation_id': 'conversation-id', 'reason': 'empty_title', 'arm': 'jev', 'discarded': True},
    )


def test_capture_exception_never_propagates(relevance_io, monkeypatch, caplog):
    capture = Mock(side_effect=RuntimeError('sensitive vendor response'))
    monkeypatch.setattr(relevance_io, 'emit_posthog_event', capture)
    decision = RelevanceDecision('keep', 'policy', 'keep_all_arm', ProcessingTrigger.SYNC_UPDATE, arm='keep_all')

    relevance_io.emit_recorded_decision('user-id', 'conversation-id', decision)

    assert capture.call_count == 1
    assert 'RuntimeError' in caplog.text
    assert 'sensitive vendor response' not in caplog.text
