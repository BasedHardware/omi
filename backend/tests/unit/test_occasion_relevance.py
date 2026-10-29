"""Occasion retention precedes rules and paid rejection; only actual merges absorb."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import occasion_relevance
from utils.conversations import relevance_io
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import Neighbor, decide_relevance
from tests.unit.test_late_audio_recorded_time import T0
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def decide(*, member=None, neighbor=None, text='Mm-hmm.', model=None):
    return decide_relevance(
        trigger=ProcessingTrigger.SYNC_UPDATE,
        texts=[text],
        speech_seconds=5,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=model,
        calendar_retains=lambda: False,
        occasion_retains=lambda: member,
        neighbor=lambda: neighbor,
    )


@pytest.mark.parametrize('context', ['occasion_member', 'occasion_neighbor'])
@pytest.mark.parametrize('text', ['Mm-hmm.', 'Coming over there in a second.'])
def test_related_content_never_has_an_independent_rule_or_model_discard(context, text):
    model = Mock(return_value=True)
    decision = decide(member=context, text=text, model=model)
    assert not decision.discard and decision.reason == context
    model.assert_not_called()


def test_neighbor_content_is_kept_until_absorption_and_isolated_clip_can_discard():
    model = Mock(return_value=True)
    decision = decide(neighbor=Neighbor('kept', 12, 'before'), text='Coming over there in a second.', model=model)
    assert not decision.discard and decision.reason == 'occasion_neighbor'
    assert decision.neighbor_id == 'kept'
    assert decide(text='Mm-hmm.').discard
    assert decide(text='Coming over there in a second.', model=model).discard
    model.assert_called_once()


def test_kill_switch_restores_independent_rules_and_intake(monkeypatch):
    monkeypatch.delenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', raising=False)
    assert occasion_relevance.enabled()
    assert not intake(StrictFirestore(), chunk('a', T0.timestamp(), 'Mm-hmm.'))[0]['discarded']
    monkeypatch.setenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'false')
    assert not occasion_relevance.enabled()
    assert decide(member='occasion_member').discard
    assert intake(StrictFirestore(), chunk('a', T0.timestamp(), 'Mm-hmm.'))[0]['discarded']


@pytest.mark.parametrize(
    'membership,covering,neighbor,reason',
    [
        ({'id': 'e'}, None, None, 'occasion_member'),
        (None, {'id': 'closed'}, None, 'occasion_member'),
        (None, None, Neighbor('kept', 10, 'before'), 'occasion_neighbor'),
        (None, None, None, None),
    ],
)
def test_production_context_reads_recorded_ownership_and_neighbors(monkeypatch, membership, covering, neighbor, reason):
    from database import episodes
    from utils.episodes import timeline

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', lambda *a: membership)
    monkeypatch.setattr(timeline, 'episode_owning_recorded_time', lambda *a, **kw: covering)
    monkeypatch.setattr(relevance_io, 'adjacent_conversation', lambda *a, **kw: neighbor)
    conversation = SimpleNamespace(id='c', started_at=T0, finished_at=T0 + timedelta(seconds=18))
    assert relevance_io.occasion_retention('u', conversation) == reason


def test_missing_ownership_read_is_not_proof_of_isolation(monkeypatch):
    from database import episodes

    monkeypatch.setattr(episodes, 'get_episode_for_conversation', Mock(side_effect=RuntimeError('offline')))
    assert (
        relevance_io.occasion_retention('u', SimpleNamespace(id='c', started_at=T0, finished_at=T0))
        == 'occasion_lookup_unavailable'
    )


def test_neighbor_prompt_cannot_reject_unabsorbed_content(monkeypatch):
    from utils.llm import conversation_processing

    model = Mock(side_effect=AssertionError('continuation must never buy a discard call'))
    monkeypatch.setattr(conversation_processing, 'get_llm', model)
    assert not conversation_processing.should_discard_conversation('Coming over there.', neighbor_gap_seconds=10)
    model.assert_not_called()


def test_full_neighbor_page_cannot_prove_isolation(monkeypatch):
    rows = [
        dict(id=f'future-{i}', started_at=T0 + timedelta(hours=3), finished_at=T0 + timedelta(hours=4))
        for i in range(10)
    ]
    monkeypatch.setattr(relevance_io.conversations_db, 'get_conversations_finished_after', lambda *a, **kw: rows)
    with pytest.raises(RuntimeError, match='neighbor_window_incomplete'):
        relevance_io.adjacent_conversation(
            'u', SimpleNamespace(id='c', started_at=T0, finished_at=T0), 'c', require_complete=True
        )
