"""The C2 census: classifier parity, KM, stuck, real-speech, end types, privacy."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from database import pipeline_ledger, pipeline_ledger_census as census

NOW = 1_800_000_000.0


def _row(**overrides):
    row = {
        'schema_version': 1,
        'owner_key': 'owner-a',
        'stage': pipeline_ledger.NOTED,
        'entered_at': NOW - 60,
        'deadline_at': NOW + 60,
        'attempt': 1,
        'reason': 'summary',
        'end_type': 'user_initiated',
        'end_at': NOW - 120,
        'admitted_at': NOW - 180,
        'created_at': NOW - 180,
        'updated_at': NOW - 10,
        'revision': 1,
        'terminal': False,
        'terminal_reason': None,
        'speech_seconds': 12.0,
        'has_speech': True,
        'speech_basis': 'vad',
        'home_ready_at': NOW - 30,
        'episode_done_at': None,
        'expires_at': None,
        'capture_id': 'conversation-1',
    }
    row.update(overrides)
    return row


def _conversation(**overrides):
    row = {
        'status': 'completed',
        'structured': {'title': 'A real title'},
        'created_at': datetime.fromtimestamp(NOW - 180, tz=timezone.utc),
        'finished_at': datetime.fromtimestamp(NOW - 120, tz=timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.fixture
def wire(monkeypatch):
    state = {'rows': [], 'conversations': {}}

    def fake_window(start, end, *, uid, limit=None, firestore_client=None, include_key=False):
        return list(state['rows'])

    def fake_conversation(client, uid, conversation_id):
        return state['conversations'].get(conversation_id)

    monkeypatch.setattr(pipeline_ledger, 'census_window', fake_window)
    monkeypatch.setattr(census, '_conversation', fake_conversation)
    return state


def _census(state, **kwargs):
    return census.census('owner', 0, NOW + 1, now=NOW, firestore_client=object(), **kwargs)


def test_classifier_parity_ready_transcribing_writing_notes_failed_noise_none(wire):
    cases = {
        'ready': (_conversation(), True),
        'transcribing': (_conversation(status='processing', structured={}), False),
        'writing_notes': (_conversation(status='processing'), False),
        'failed': (_conversation(status='failed'), False),
        'noise': (
            _conversation(
                structured={'title_provenance': 'server_minimum'},
                summary_blocked_reason='content_below_floor',
            ),
            False,
        ),
        'none': (_conversation(status='in_progress'), False),
    }
    for name, (row, expected) in cases.items():
        visible, step = census._home_visible(row, NOW)
        assert visible is expected, name
        if name == 'none':
            assert step is None, name
        else:
            assert step is not None, name


def test_missing_conversation_is_home_unknown(wire):
    wire['rows'] = [_row()]
    result = _census(wire)
    assert result['home_visible']['home_unknown'] == 1
    assert result['home_visible']['visible'] == 0


def test_km_unfinished_rows_are_censored_not_dropped():
    one_event = [(10.0, None, True)] + [(None, 100.0, False)] * 3
    assert census._km_quantiles(one_event) == {0.5: None, 0.9: None}
    four_events = [(10.0, None, True)] * 4 + [(None, 100.0, False)] * 4
    assert census._km_quantiles(four_events)[0.5] == 10.0


def test_stuck_is_grouped_by_stage_and_never_merged(wire):
    wire['rows'] = [
        _row(stage=pipeline_ledger.SEALED, deadline_at=NOW - 10, capture_id='a'),
        _row(stage=pipeline_ledger.TRANSCRIBED, deadline_at=NOW - 20, capture_id='b'),
        _row(stage=pipeline_ledger.NOTED, deadline_at=NOW - 30, capture_id='c'),
        _row(stage=pipeline_ledger.NOTED, deadline_at=NOW + 30, capture_id='d'),
    ]
    result = _census(wire)
    assert result['stuck']['by_stage'] == {'capturing': 0, 'sealed': 1, 'transcribed': 1, 'noted': 1}
    assert result['stuck']['total'] == 3
    assert result['stuck']['oldest_age_seconds']['noted'] == 30
    assert result['new_stuck_per_hour']['total'] == 3


def test_terminal_rows_are_never_stuck(wire):
    wire['rows'] = [_row(stage=pipeline_ledger.DONE, terminal=True, deadline_at=NOW - 10)]
    result = _census(wire)
    assert result['stuck']['total'] == 0


def test_real_speech_denominator_uses_the_conservative_lower_bound(wire):
    wire['rows'] = [
        _row(capture_id='a', speech_seconds=10.0, speech_basis='vad'),
        _row(capture_id='b', speech_seconds=10.0, speech_basis='vad'),
        _row(capture_id='c', speech_seconds=None, has_speech=None, speech_basis='unknown'),
    ]
    wire['conversations'] = {'a': _conversation(), 'b': _conversation(), 'c': _conversation()}
    result = _census(wire)
    home = result['home_visible']
    assert home['real_speech'] == 2
    assert home['speech_unknown'] == 1
    assert home['denominator'] == 3
    assert home['visible'] == 2
    assert home['share'] == 1.0
    assert home['share_lower_bound'] == pytest.approx(2 / 3)
    assert home['share_upper_bound'] == 1.0
    assert home['speech_unknown_share'] == pytest.approx(1 / 3)


def test_zero_real_speech_reports_null_not_zero(wire):
    wire['rows'] = [_row(speech_seconds=0.0, has_speech=False, speech_basis='vad')]
    result = _census(wire)
    assert result['home_visible']['share'] is None
    assert result['home_visible']['share_lower_bound'] is None


def test_end_types_are_reported_and_unknown_is_never_dropped(wire):
    wire['rows'] = [
        _row(capture_id='a', end_type='user_initiated'),
        _row(capture_id='b', end_type='silence_backstop'),
        _row(capture_id='c', end_type='unknown'),
    ]
    wire['conversations'] = {'a': _conversation(), 'b': _conversation(), 'c': _conversation()}
    result = _census(wire)
    assert result['end_types']['user_initiated']['rows'] == 1
    assert result['end_types']['silence_backstop']['rows'] == 1
    assert result['end_types']['unknown']['rows'] == 1
    assert result['end_types']['unknown_share'] == pytest.approx(1 / 3)
    assert result['end_types']['jev_initiated']['sample_status'] == 'insufficient_sample'


def test_schema_mismatch_fails_closed(wire):
    wire['rows'] = [_row(schema_version=2)]
    with pytest.raises(census.CensusSchemaMismatch):
        _census(wire)


def test_zero_rows_is_not_a_measured_share(wire):
    result = _census(wire)
    assert result['rows'] == 0
    assert result['home_visible']['share'] is None
    assert result['stuck']['total'] == 0


def test_output_has_no_uid_conversation_id_title_or_transcript(wire):
    wire['rows'] = [_row(capture_id='conversation-secret')]
    wire['conversations'] = {'conversation-secret': _conversation()}
    rendered = json.dumps(_census(wire))
    for forbidden in ('owner-a', 'conversation-secret', 'A real title', 'transcript_segments'):
        assert forbidden not in rendered


def test_explain_returns_transitions_and_no_content(monkeypatch):
    class _Snapshot:
        exists = True

        def to_dict(self):
            return {
                'stage': pipeline_ledger.NOTED,
                'entered_at': NOW - 60,
                'deadline_at': NOW + 60,
                'attempt': 2,
                'reason': 'summary',
                'end_type': 'user_initiated',
                'end_at': NOW - 120,
                'transitions': [
                    {'stage': pipeline_ledger.SEALED, 'at': NOW - 180, 'reason': 'sealed'},
                    {'stage': pipeline_ledger.NOTED, 'at': NOW - 60, 'reason': 'summary'},
                ],
                'title': 'secret',
                'transcript_segments': [{'text': 'secret'}],
            }

    class _Ref:
        def get(self):
            return _Snapshot()

    monkeypatch.setattr(pipeline_ledger, 'ledger_ref', lambda client, uid, cid: _Ref())
    result = census.explain('owner', 'conversation-1', firestore_client=object())
    assert result['conversation_id'] == 'conversation-1'
    assert [t['stage'] for t in result['transitions']] == [pipeline_ledger.SEALED, pipeline_ledger.NOTED]
    rendered = json.dumps(result)
    assert 'secret' not in rendered
    assert 'owner' not in rendered
