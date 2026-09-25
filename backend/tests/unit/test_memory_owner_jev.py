"""Capture-time Jev owner flip (owner_jev.py + _extract_memories_canonical, #14835).

Pins: flag off asks nothing; only third-party candidates are asked; P(user) at
or above 0.9 re-attributes to the user with subject, kind, category and scope
consistent; below it, or with no answer, the pipeline's attribution stands; a
user-attributed candidate is never asked (no user -> other flip); provenance
reaches the canonical item. All transcripts are synthetic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from utils.conversations import owner_jev, transcript_for_llm
from utils.llm.jev_client import JevAnswers
from utils.memory.canonical_memory_adapter import (
    _product_metadata_from_payload,  # pyright: ignore[reportPrivateUsage]
)
from tests.unit.test_memory_replace_policy import _memory_replace_import_isolation, _load_process_conversation

__all__ = ['_memory_replace_import_isolation']

OWNER_TEXT = 'I am flying to Denver next week.'
OTHER_TEXT = 'I just adopted a beagle named Pixel.'


@pytest.fixture(scope='module')
def pc(_memory_replace_import_isolation):
    return _load_process_conversation()


def _conversation() -> Conversation:
    segments = [
        TranscriptSegment(text=OWNER_TEXT, speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0, end=1),
        TranscriptSegment(text=OTHER_TEXT, speaker='SPEAKER_01', speaker_id=1, is_user=False, start=1, end=2),
    ]
    return Conversation(
        structured={'title': 'Weekend plans', 'overview': 'Two people compare plans.', 'category': 'personal'},
        id='owner-jev-conv',
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source='omi',
        transcript_segments=segments,
    )


def _candidate(content: str, *, about: str, speaker_label: str, quote: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        about=about,
        speaker_label=speaker_label,
        evidence_quotes=[quote],
        risk_flags=[],
        archive_class='general',
        subject_scope='third_party',
        belief_class=None,
        half_life_days=None,
        valid_to=None,
        predicate=None,
        arguments={},
    )


THIRD_PARTY = _candidate(
    'User adopted a beagle named Pixel.', about='speaker_1', speaker_label='speaker_1', quote=OTHER_TEXT
)
OWNER = _candidate('User is flying to Denver next week.', about='user', speaker_label='speaker_0', quote=OWNER_TEXT)


@pytest.fixture
def capture(monkeypatch, pc):
    """Run canonical capture on one candidate; returns (run, asked, outcomes)."""
    service = MagicMock()
    asked: list[dict] = []
    outcomes: list[str] = []
    answer: dict = {'p_user': None}

    def fake_ask(state, questions, *, lane):
        asked.append({'state': state, 'questions': questions, 'lane': lane})
        if answer['p_user'] is None:
            return None
        return JevAnswers(
            served_model='typesafe/jev-1.13-20260917',
            answers={'owner': {'probabilities': {'user': answer['p_user'], 'third_party': 1 - answer['p_user']}}},
        )

    monkeypatch.setattr(owner_jev, 'ask_jev', fake_ask)
    monkeypatch.setattr(pc, 'record_memory_owner_jev', outcomes.append)
    monkeypatch.setattr(pc, 'MemoryService', lambda **_kwargs: service)
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda _uid: 'en')
    monkeypatch.setattr(pc, 'get_user_name', lambda *_args, **_kwargs: 'Alex')
    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_args, **_kwargs: 'Alex')
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda _uid: 'UTC')
    monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: False)
    monkeypatch.setattr(pc, 'belief_model_enabled', lambda: True)
    monkeypatch.setattr(pc, '_rejected_memory_examples_for_l1', lambda *_args, **_kwargs: ())

    def run(candidate: SimpleNamespace, *, enabled: bool, p_user: float | None = None) -> dict:
        answer['p_user'] = p_user
        monkeypatch.setattr(pc, 'memory_owner_jev_flip_enabled', lambda: enabled)
        monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', lambda *_a, **_k: [candidate])
        service.reset_mock()
        result = pc._extract_memories_canonical('uid-synthetic', _conversation(), db_client=MagicMock())
        assert result.count == 1
        return service.replace_conversation_memories.call_args.args[2][0]

    return run, asked, outcomes


def test_flag_off_asks_nothing_and_keeps_the_third_party_attribution(capture):
    run, asked, outcomes = capture

    payload = run(THIRD_PARTY, enabled=False, p_user=0.99)

    assert asked == [] and outcomes == []
    assert payload['subject_attribution'] == 'third_party'
    assert payload['subject_entity_id'].startswith('source:')
    assert 'attribution_override' not in payload


@pytest.mark.parametrize('p_user', [owner_jev.OWNER_FLIP_THRESHOLD, 0.97])
def test_confident_answer_flips_third_party_to_user_consistently(capture, p_user):
    run, asked, outcomes = capture
    pipeline = run(THIRD_PARTY, enabled=False)

    payload = run(THIRD_PARTY, enabled=True, p_user=p_user)

    assert outcomes == ['flipped']
    assert (payload['subject_attribution'], payload['subject_entity_id'], payload['subject_kind']) == (
        'user',
        'user',
        'user',
    )
    assert payload['category'] == 'system'
    assert payload['subject_scope'] == 'primary_user'
    override = payload['attribution_override']
    assert override['source'] == 'jev' and override['p_user'] == p_user
    assert override['pipeline_subject_entity_id'] == pipeline['subject_entity_id']
    assert override['pipeline_subject_kind'] == 'speaker'
    (question,) = asked
    assert question['lane'] == 'memory_owner'
    assert '[SPEAKER_01] "I just adopted a beagle named Pixel."' in question['state']
    assert 'Conversation title: Weekend plans' in question['state']
    assert 'Candidate memory: "User adopted a beagle named Pixel."' in question['state']


def test_below_threshold_keeps_the_pipeline_attribution(capture):
    run, _, outcomes = capture

    payload = run(THIRD_PARTY, enabled=True, p_user=0.8999)

    assert outcomes == ['kept_third_party']
    assert payload['subject_attribution'] == 'third_party'
    assert payload['subject_scope'] == 'third_party'
    assert 'attribution_override' not in payload


def test_no_answer_keeps_the_pipeline_attribution(capture):
    run, _, outcomes = capture

    payload = run(THIRD_PARTY, enabled=True, p_user=None)

    assert outcomes == ['unavailable']
    assert payload['subject_attribution'] == 'third_party'


def test_a_user_attributed_candidate_is_never_asked(capture):
    run, asked, outcomes = capture

    payload = run(OWNER, enabled=True, p_user=0.0)

    assert asked == [] and outcomes == []
    assert payload['subject_attribution'] == 'user'


def test_checks_per_conversation_are_bounded(capture, monkeypatch, pc):
    run, asked, outcomes = capture
    monkeypatch.setattr(pc, 'MAX_OWNER_CHECKS_PER_CONVERSATION', 0)

    payload = run(THIRD_PARTY, enabled=True, p_user=0.99)

    assert asked == [] and outcomes == ['skipped_budget']
    assert payload['subject_attribution'] == 'third_party'


def test_provenance_is_stored_beside_the_subject_the_planner_reads():
    override = {
        'source': 'jev',
        'p_user': 0.93,
        'pipeline_subject_attribution': 'third_party',
        'pipeline_subject_entity_id': 'source:abc',
        'pipeline_subject_kind': 'speaker',
        'unexpected': 'dropped',
    }

    flipped = _product_metadata_from_payload(
        {
            'subject_attribution': 'user',
            'subject_entity_id': 'user',
            'subject_kind': 'user',
            'attribution_override': override,
        }
    )
    plain = _product_metadata_from_payload({'subject_attribution': 'third_party', 'subject_entity_id': 'source:abc'})
    foreign = _product_metadata_from_payload({'subject_attribution': 'user', 'attribution_override': {'source': 'x'}})

    attribution = flipped['source_attribution']
    assert (attribution['subject_attribution'], attribution['subject_entity_id']) == ('user', 'user')
    assert attribution['override'] == {key: value for key, value in override.items() if key != 'unexpected'}
    assert 'override' not in plain['source_attribution']
    assert 'override' not in foreign['source_attribution']


def test_owner_state_uses_a_generic_preamble_and_bounds_quotes():
    state = owner_jev.owner_state(
        candidate='Likes tea.',
        quotes=[(f'SPEAKER_0{i}', f'quote {i}') for i in range(7)],
        title='T',
        overview='o' * 1000,
        source='desktop',
        user_name='the user',
    )

    assert 'The owner ("the user") is the device owner.' in state
    assert 'Omi desktop app' in state
    assert state.count('[SPEAKER_0') == owner_jev.MAX_QUOTES
    assert 'o' * (owner_jev.MAX_OVERVIEW_CHARS + 1) not in state
