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
    shadowed = []
    monkeypatch.setenv('MEMORY_OWNER_JEV_SHADOW_PERCENT', '100')
    real_shadow_helper = pc._shadow_owner_candidate
    monkeypatch.setattr(pc, '_real_owner_shadow_test_helper', real_shadow_helper, raising=False)
    monkeypatch.setattr(pc, '_shadow_owner_candidate', lambda *args, **kwargs: shadowed.append(args))
    monkeypatch.setattr(pc, '_owner_shadow_test_calls', shadowed, raising=False)

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


def test_owner_shadow_only_for_third_party_not_live_scored(capture, pc):
    run, _, _ = capture
    run(THIRD_PARTY, enabled=False)
    assert len(pc._owner_shadow_test_calls) == 1
    assert pc._owner_shadow_test_calls[0][-1] == 'speaker'
    assert pc._owner_shadow_test_calls[0][-2] is True
    pc._owner_shadow_test_calls.clear()
    run(OWNER, enabled=False)
    run(THIRD_PARTY, enabled=True, p_user=0.4)
    run(THIRD_PARTY, enabled=True, p_user=None)
    run(THIRD_PARTY, enabled=True, p_user=0.99)
    assert pc._owner_shadow_test_calls == []


def test_owner_shadow_includes_candidates_beyond_live_budget(capture, pc, monkeypatch):
    run, asked, outcomes = capture
    monkeypatch.setattr(pc, 'MAX_OWNER_CHECKS_PER_CONVERSATION', 0)
    payload = run(THIRD_PARTY, enabled=True, p_user=0.99)
    assert not asked and outcomes == ['skipped_budget']
    assert len(pc._owner_shadow_test_calls) == 1
    assert payload['subject_attribution'] == 'third_party'


def test_owner_shadow_builds_state_without_retaining_conversation(capture, pc, monkeypatch):
    run, _, _ = capture
    submitted = []
    monkeypatch.setattr(pc, '_shadow_owner_candidate', pc._real_owner_shadow_test_helper)
    monkeypatch.setattr(pc, 'submit_owner_shadow', lambda **kwargs: submitted.append(kwargs))
    run(THIRD_PARTY, enabled=False)
    assert len(submitted) == 1
    assert all(isinstance(value, (str, int, bool)) or value is None for value in submitted[0].values())
    assert 'SPEAKER_01' in submitted[0]['state']
    assert submitted[0]['user_name_present'] is True
    assert submitted[0]['candidate_index'] == 0 and submitted[0]['eligible_count'] == 1


@pytest.mark.parametrize('failure', ['exception', 'timeout'])
def test_owner_shadow_failure_cannot_change_canonical_memory(capture, pc, monkeypatch, failure):
    from concurrent.futures import Future
    from utils.conversations import jev_shadow

    run, _, _ = capture
    baseline = run(THIRD_PARTY, enabled=False)
    monkeypatch.setattr(pc, '_shadow_owner_candidate', pc._real_owner_shadow_test_helper)
    monkeypatch.setenv('MEMORY_OWNER_JEV_SHADOW_PERCENT', '100')
    monkeypatch.setattr(jev_shadow, '_admit', lambda *args: 'admitted')
    written = []
    monkeypatch.setattr(jev_shadow, 'write_jev_shadow', lambda *args: written.append(args))

    def unavailable(*args, **kwargs):
        if failure == 'exception':
            raise RuntimeError('synthetic private failure text')
        kwargs['outcome_observer']('timeout')
        return None

    def immediate(_executor, fn, *args):
        future = Future()
        fn(*args)
        future.set_result(None)
        return future

    monkeypatch.setattr(jev_shadow, 'ask_jev', unavailable)
    monkeypatch.setattr(jev_shadow, 'submit_with_context', immediate)
    actual = run(THIRD_PARTY, enabled=False)
    # Generated capture timestamps and IDs are outside attribution treatment.
    for field in (
        'content',
        'category',
        'subject_entity_id',
        'subject_attribution',
        'subject_kind',
        'subject_scope',
        'source_attribution',
    ):
        assert actual.get(field) == baseline.get(field)
    assert 'attribution_override' not in actual and written == []


@pytest.mark.parametrize('name', [None, '', '   ', 'The User'])
def test_missing_profile_name_is_visible_in_owner_shadow(capture, pc, monkeypatch, name):
    run, _, _ = capture
    monkeypatch.setattr(pc, 'get_user_name', lambda _uid: name)
    run(THIRD_PARTY, enabled=False)
    assert len(pc._owner_shadow_test_calls) == 1
    assert pc._owner_shadow_test_calls[0][-2] is False


def test_extraction_hash_selects_entire_eligible_batch_before_submission(capture, pc, monkeypatch):
    from utils.conversations import jev_shadow

    candidates = [
        _candidate(f'Synthetic candidate {i}.', about='speaker_1', speaker_label='speaker_1', quote=OTHER_TEXT)
        for i in range(20)
    ]
    monkeypatch.setattr(pc, 'memory_owner_jev_flip_enabled', lambda: False)
    monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', lambda *_a, **_k: iter(candidates))
    calls = []
    monkeypatch.setattr(pc, '_shadow_owner_candidate', lambda *args, **kwargs: calls.append((args, kwargs)))
    pc._extract_memories_canonical('uid-synthetic', _conversation(), db_client=MagicMock())
    identities = [
        jev_shadow.owner_shadow_identity(
            candidate_content=c.content,
            state=pc._owner_shadow_state(_conversation(), c.content, c.evidence_quotes, 'Alex'),
            user_name='Alex',
            pipeline_subject_kind='speaker',
            pipeline_subject_entity_id=pc._l1_candidate_subject(
                source_id=_conversation().id,
                about=c.about,
                speaker_label=c.speaker_label,
                evidence_quotes=c.evidence_quotes,
                user_name='Alex',
                segments=_conversation().transcript_segments,
            )[0],
        )
        for c in candidates
    ]
    expected, eligible_count = jev_shadow.select_owner_shadow_indices(_conversation().id, identities)
    assert eligible_count == 20
    assert len(calls) == jev_shadow.MAX_OWNER_SHADOWS_PER_CONVERSATION
    assert [kwargs['candidate_index'] for _, kwargs in calls] == expected
    assert all(kwargs['eligible_count'] == 20 for _, kwargs in calls)
    assert [args[2] for args, _ in calls] == [candidates[i].content for i in expected]
    assert set(expected) != set(range(8))


def test_extraction_records_unique_population_before_cap_with_original_indices(capture, pc, monkeypatch):
    from utils.conversations import jev_shadow

    # Position 0 is not eligible; exact duplicates must not inflate the denominator.
    candidates = (
        [OWNER]
        + [THIRD_PARTY] * 3
        + [
            _candidate(f'Synthetic unique {i}.', about='speaker_1', speaker_label='speaker_1', quote=OTHER_TEXT)
            for i in range(12)
        ]
    )
    monkeypatch.setattr(pc, 'memory_owner_jev_flip_enabled', lambda: False)
    monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', lambda *_a, **_k: candidates)
    monkeypatch.setattr(pc, '_shadow_owner_candidate', pc._real_owner_shadow_test_helper)
    submitted = []
    monkeypatch.setattr(pc, 'submit_owner_shadow', lambda **kwargs: submitted.append(kwargs))
    pc._extract_memories_canonical('uid-synthetic', _conversation(), db_client=MagicMock())
    assert len(submitted) == jev_shadow.MAX_OWNER_SHADOWS_PER_CONVERSATION
    assert all(record['eligible_count'] == 13 for record in submitted)
    indices = [record['candidate_index'] for record in submitted]
    assert len(set(indices)) == 8 and not set(indices).intersection({0, 2, 3})
    assert all(record['candidate_content'] == candidates[record['candidate_index']].content for record in submitted)


def test_extraction_preserves_same_text_with_different_grounded_evidence(capture, pc, monkeypatch):
    other_quote = 'I walk Pixel every morning.'
    conversation = _conversation()
    conversation.transcript_segments.append(
        TranscriptSegment(text=other_quote, speaker='SPEAKER_01', speaker_id=1, is_user=False, start=2, end=3)
    )
    candidates = [
        THIRD_PARTY,
        _candidate(
            THIRD_PARTY.content,
            about='speaker_1',
            speaker_label='speaker_1',
            quote=other_quote,
        ),
    ]
    monkeypatch.setattr(pc, 'memory_owner_jev_flip_enabled', lambda: False)
    monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', lambda *_a, **_k: candidates)
    monkeypatch.setattr(pc, '_shadow_owner_candidate', pc._real_owner_shadow_test_helper)
    submitted = []
    monkeypatch.setattr(pc, 'submit_owner_shadow', lambda **kwargs: submitted.append(kwargs))
    pc._extract_memories_canonical('uid-synthetic', conversation, db_client=MagicMock())
    assert len(submitted) == 2
    assert {r['candidate_index'] for r in submitted} == {0, 1}
    assert all(r['eligible_count'] == 2 for r in submitted)
    assert submitted[0]['state'] != submitted[1]['state']
