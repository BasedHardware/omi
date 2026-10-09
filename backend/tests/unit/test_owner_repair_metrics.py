"""Late repair counters reflect committed readable identity changes."""

from copy import deepcopy

import pytest

from tests.unit.test_owner_repair_committed import _counter, _commit_store
from tests.unit.test_conversation_speaker_resolution_stage import (
    env,
    empty_manual_receipt,
    _capture_shifted_conversation,
)
from utils.conversations import speaker_resolution as stage
from utils.observability import owner_recognition as metrics


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
    record = {'id': 'c1', 'transcript_segments': [{'id': 's', 'is_user': False}]}
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
    before = {'id': 'c1', 'transcript_segments': [{'id': 's', 'is_user': outcome == 'owner_removed'}]}
    after = deepcopy(before)
    after['transcript_segments'][0].update(change)
    count = _counter(outcome)
    metrics.record_owner_identity_repair(before, after)
    assert _counter(outcome) == count + 1
