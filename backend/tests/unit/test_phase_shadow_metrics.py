"""Bounded labels, actual error samples, kill switch, and trustworthy age clocks."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from prometheus_client import generate_latest

from utils.conversations import phase_shadow as shadow
from utils.conversations.phase import ConversationPhase as C, EpisodePhase as E


@pytest.mark.parametrize('value', ['false', '0', 'off', 'no', ' OFF '])
def test_switch_prevents_all_derivation_and_metrics(monkeypatch, value):
    monkeypatch.setenv('PHASE_SHADOW_ENABLED', value)
    derive = Mock(side_effect=AssertionError('must never derive'))
    episode = Mock(side_effect=AssertionError('must never derive'))
    metric = Mock(side_effect=AssertionError('must never collect'))
    monkeypatch.setattr(shadow, 'derive_conversation_phase', derive)
    monkeypatch.setattr(shadow, 'derive_episode_phase', episode)
    for collector in (shadow.SHADOW, shadow.AGE, shadow.ERRORS):
        monkeypatch.setattr(collector, 'labels', metric)
    for reader in shadow.READERS:
        shadow.observe(reader, {'uid': 'secret', 'id': 'secret'}, True)
    derive.assert_not_called()
    episode.assert_not_called()
    metric.assert_not_called()


def test_default_on_emits_disagreement_for_november_3_shape(monkeypatch):
    monkeypatch.delenv('PHASE_SHADOW_ENABLED', raising=False)
    metric = shadow.SHADOW.labels('home_visibility', 'sealed', 'false')
    before = metric._value.get()
    shadow.observe(
        'home_visibility',
        {'status': 'completed', 'record_lane_owner': 'batch_live_v1', 'record_audio_closed': True},
        True,
    )
    assert metric._value.get() == before + 1


def test_collector_and_age_failures_never_escape_and_are_counted(monkeypatch):
    monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'true')
    before = shadow.ERRORS.labels('home_visibility')._value.get()
    monkeypatch.setattr(shadow.AGE, 'labels', Mock(side_effect=RuntimeError('collector failed')))
    shadow.observe('home_visibility', {'started_at': 10}, False, now=20)
    assert shadow.ERRORS.labels('home_visibility')._value.get() == before + 1
    monkeypatch.setattr(shadow.ERRORS, 'labels', Mock(side_effect=RuntimeError('collector failed')))
    shadow.observe('home_visibility', {'started_at': 10}, False, now=20)


@pytest.mark.parametrize(
    'row,phase,expected',
    [
        ({'started_at': 10}, C.CAPTURING, 10),
        ({'finished_at': 10, 'record_audio_closed': True}, C.SEALED, None),
        ({'processing_admitted_at': 20, 'created_at': 1}, C.PROCESSING, 20),
        ({'summary_first_pending_at': 30}, C.TRANSCRIBED, 30),
        ({'summary_completed_at': 40}, C.COMPLETE, 40),
        ({'wrap_up_requested_at': 50}, E.CLOSING, 50),
        ({'closed_at': 60}, E.CLOSED, 60),
        ({'composed_at': 70}, E.COMPOSED, 70),
        ({'closed_at': True}, E.CLOSED, None),
        ({'closed_at': float('nan')}, E.CLOSED, None),
        (
            {'closed_at': datetime(2026, 11, 3, tzinfo=timezone.utc)},
            E.CLOSED,
            datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp(),
        ),
    ],
)
def test_phase_age_uses_only_existing_event_clock(row, phase, expected):
    assert shadow.phase_entered_at(row, phase) == expected


def test_age_histogram_and_no_identifiers_in_export(monkeypatch):
    monkeypatch.setenv('PHASE_SHADOW_ENABLED', 'true')
    age = shadow.AGE.labels('processing')
    before = age._sum.get()
    shadow.observe(
        'processing_attention',
        {'status': 'processing', 'processing_admitted_at': 100, 'uid': 'private-user', 'id': 'private-id'},
        True,
        now=7300,
    )
    assert age._sum.get() == before + 7200
    exported = generate_latest().decode()
    lines = [line for line in exported.splitlines() if line.startswith('omi_phase_')]
    assert lines
    assert all('private-user' not in line and 'private-id' not in line and 'uid=' not in line for line in lines)
    assert shadow.SHADOW._labelnames == ('reader', 'derived_phase', 'agrees')
    assert shadow.ERRORS._labelnames == ('reader',)
    assert shadow.AGE._labelnames == ('phase',)
