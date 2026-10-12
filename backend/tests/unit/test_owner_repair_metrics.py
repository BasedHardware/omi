"""Late repair counters reflect committed readable identity changes."""

from copy import deepcopy

import pytest

from models.conversation import Conversation
from tests.unit.test_owner_repair_committed import _counter, _commit_store
from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _capture_shifted_conversation,
)
from utils.conversations import speaker_resolution as stage
from utils.observability import owner_recognition as metrics


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('omitted', ['speaker_id', 'speaker', 'speaker_label_source'])
def test_legacy_identity_defaults_are_not_committed_repairs(env, monkeypatch, level, omitted):
    # Use the real flag-off resolver, actual codec and transaction writer. The
    # legacy row is already rendered with these defaults before the CAS write.
    monkeypatch.setenv('CONVERSATION_SPEAKER_RESOLUTION_ENABLED', 'false')
    conversation = _capture_shifted_conversation([0])
    segment = conversation.transcript_segments[0]
    segment.is_user = True
    segment.speaker_match_source = stage.MATCH_SOURCE
    assert stage.MATCH_SOURCE == 'conversation_voice'
    _, _, read = _commit_store(monkeypatch, conversation, level, omit_identity_fields=(omitted,))
    stored_before = read()['transcript_segments'][0]
    assert omitted not in stored_before
    before_transcript = Conversation(**read()).model_dump()['transcript_segments']
    before = {label: _counter(label) for label in ('owner_added', 'owner_removed', 'identity_updated')}
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert omitted in read()['transcript_segments'][0]
    assert Conversation(**read()).model_dump()['transcript_segments'] == before_transcript
    assert {label: _counter(label) for label in before} == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize(
    'field,value', [('speaker_id', 1), ('speaker', 'SPEAKER_01'), ('speaker_label_source', 'manual')]
)
def test_canonical_identity_change_after_legacy_default_is_counted(env, monkeypatch, level, field, value):
    conversation = _capture_shifted_conversation([0])
    conversation.transcript_segments[0].is_user = True
    conversation.transcript_segments[0].speaker_match_source = stage.MATCH_SOURCE
    _, _, read = _commit_store(monkeypatch, conversation, level, omit_identity_fields=(field,))
    before_transcript = Conversation(**read()).model_dump()['transcript_segments']

    def change_identity(uid, conv, **kwargs):
        setattr(conv.transcript_segments[0], field, value)
        return True

    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', change_identity)
    before = {label: _counter(label) for label in ('owner_added', 'owner_removed', 'identity_updated')}
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    after_transcript = Conversation(**read()).model_dump()['transcript_segments']
    assert after_transcript != before_transcript and after_transcript[0][field] == value
    before['identity_updated'] += 1
    assert {label: _counter(label) for label in before} == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('omit_ids', [False, True])
def test_unchanged_late_identity_is_not_a_repair(env, monkeypatch, level, omit_ids):
    conversation = _capture_shifted_conversation([0])
    conversation.transcript_segments[0].is_user = True
    _commit_store(monkeypatch, conversation, level, omit_ids=omit_ids)
    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', lambda *a, **kw: True)
    before = {label: _counter(label) for label in ('owner_added', 'owner_removed', 'identity_updated')}
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert {label: _counter(label) for label in before} == before


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_repair_metric_observes_transaction_manual_veto(env, monkeypatch, level):
    conversation = _capture_shifted_conversation([0])
    receipt = {'generation': 1, 'speakers': {'0': {'generation': 1, 'rejection': {'kind': 'not_me'}}}}
    _, _, read = _commit_store(monkeypatch, conversation, level, receipt=receipt)

    def predict_owner(uid, conv, **kwargs):
        conv.transcript_segments[0].is_user = True
        return True

    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', predict_owner)
    before = _counter('owner_added')
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert not read()['transcript_segments'][0]['is_user']
    assert _counter('owner_added') == before


def test_counter_receives_distinct_readable_snapshots(monkeypatch):
    record = {'id': 'c1', 'transcript_segments': [{'id': 's', 'is_user': False, 'text': 'Hello', 'start': 0, 'end': 1}]}
    before = deepcopy(record)
    record['transcript_segments'][0]['is_user'] = True
    count = _counter('owner_added')
    metrics.record_owner_identity_repair(before, record)
    assert _counter('owner_added') == count + 1


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_transaction_commit_survives_metric_failure(env, monkeypatch, level):
    conversation = _capture_shifted_conversation([0])
    _, _, read = _commit_store(monkeypatch, conversation, level)

    def predict_owner(uid, conv, **kwargs):
        conv.transcript_segments[0].is_user = True
        return True

    def fail(*args):
        raise RuntimeError('metric failure')

    monkeypatch.setattr(stage, 'resolve_speakers_for_processing', predict_owner)
    monkeypatch.setattr(stage, 'record_owner_identity_repair', fail)
    assert stage.refresh_completed_speaker_identity('u1', 'c1')
    assert read()['transcript_segments'][0]['is_user']


@pytest.mark.parametrize(
    'change,outcome', [({'is_user': False}, 'owner_removed'), ({'person_id': 'p1'}, 'identity_updated')]
)
def test_committed_identity_delta_classifies_removal_and_person_updates(change, outcome):
    before = {
        'id': 'c1',
        'transcript_segments': [
            {'id': 's', 'is_user': outcome == 'owner_removed', 'text': 'Hello', 'start': 0, 'end': 1}
        ],
    }
    after = deepcopy(before)
    after['transcript_segments'][0].update(change)
    count = _counter(outcome)
    metrics.record_owner_identity_repair(before, after)
    assert _counter(outcome) == count + 1
