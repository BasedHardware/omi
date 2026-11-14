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
        '_uid': 'owner',
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
    state = {'rows': [], 'conversations': {}, 'capture_creates': 0, 'retention': NOW - 10_000}

    def fake_window(start, end, *, limit=None, firestore_client=None):
        return list(state['rows'])

    def fake_conversation(client, uid, conversation_id):
        return state['conversations'].get(conversation_id)

    def fake_capture_creates(client, start, end):
        state['capture_window'] = (start, end)
        return state['capture_creates']

    def fake_retention(*, firestore_client=None):
        return state['retention']

    monkeypatch.setattr(census, '_global_window', fake_window)
    monkeypatch.setattr(census, '_conversation', fake_conversation)
    monkeypatch.setattr(census, '_capture_creates', fake_capture_creates)
    monkeypatch.setattr(pipeline_ledger, 'retention_start', fake_retention)
    return state


def _census(state, **kwargs):
    return census.census(0, NOW + 1, now=NOW, firestore_client=object(), **kwargs)


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
        _row(capture_id='a', end_type='user_initiated', terminal=True),
        _row(capture_id='b', end_type='silence_backstop', terminal=True),
        _row(capture_id='c', end_type='unknown', terminal=True),
    ]
    wire['conversations'] = {'a': _conversation(), 'b': _conversation(), 'c': _conversation()}
    result = _census(wire)
    assert result['end_types']['user_initiated']['rows'] == 1
    assert result['end_types']['silence_backstop']['rows'] == 1
    assert result['end_types']['unknown']['rows'] == 1
    assert result['end_types']['terminal_rows'] == 3
    assert result['end_types']['unknown_share'] == pytest.approx(1 / 3)
    assert result['end_types']['jev_initiated']['sample_status'] == 'insufficient_sample'


def test_in_flight_rows_are_not_an_unknown_end_type(wire):
    wire['rows'] = [_row(capture_id='ended', end_type='unknown', terminal=True)] + [
        _row(capture_id=f'live-{index}', end_type='unknown', terminal=False) for index in range(9)
    ]
    wire['conversations'] = {row['capture_id']: _conversation() for row in wire['rows']}
    result = _census(wire)
    assert result['end_types']['terminal_rows'] == 1
    assert result['end_types']['unknown']['rows'] == 1
    assert result['end_types']['unknown_share'] == 1.0


def test_real_speech_and_unknown_are_disjoint(wire):
    # plan_advance defaults speech_basis to 'unknown' independently of has_speech.
    wire['rows'] = [_row(capture_id='a', speech_seconds=None, has_speech=True, speech_basis='unknown')]
    wire['conversations'] = {'a': _conversation()}
    result = _census(wire)
    home = result['home_visible']
    assert home['real_speech'] == 1
    assert home['speech_unknown'] == 0
    assert home['denominator'] == 1
    assert home['speech_unknown_share'] == 0.0


def test_per_end_type_latency_is_reported(wire):
    wire['rows'] = [
        _row(capture_id='a', end_type='user_initiated', terminal=True, end_at=NOW - 100, home_ready_at=NOW - 10),
        _row(capture_id='b', end_type='user_initiated', terminal=True, end_at=NOW - 100, home_ready_at=NOW - 20),
        _row(capture_id='c', end_type='silence_backstop', terminal=True, end_at=NOW - 100, home_ready_at=NOW - 5),
    ]
    wire['conversations'] = {row['capture_id']: _conversation() for row in wire['rows']}
    result = _census(wire)
    assert result['end_types']['user_initiated']['p50_seconds'] == 80.0
    assert result['end_types']['user_initiated']['p50_status'] == 'measured'
    assert result['end_types']['silence_backstop']['p50_seconds'] == 95.0
    assert result['end_types']['jev_initiated']['p50_seconds'] is None


def test_retention_and_coverage_are_reported(wire):
    wire['rows'] = [_row(capture_id='a', terminal=True)]
    wire['conversations'] = {'a': _conversation(created_at=datetime.fromtimestamp(NOW - 500, tz=timezone.utc))}
    wire['capture_creates'] = 1
    result = _census(wire)
    assert result['retention'] == {'earliest_admitted_at': NOW - 10_000, 'basis': 'collection_group_min'}
    assert result['coverage']['ledger_admits'] == 1
    assert result['coverage']['cohort_admits'] == 1
    assert result['coverage']['excluded_admits'] == 0
    assert result['coverage']['capture_creates'] == 1
    assert result['coverage']['unmatched_creates'] == 0
    assert result['coverage']['ratio'] == 1.0
    assert result['coverage']['basis'] == 'conversations_created_in_window'
    # The denominator is read over the settled cohort, not the raw window end.
    assert wire['capture_window'][1] == NOW + 1 - census.COVERAGE_SETTLE_SECONDS


def test_coverage_compares_the_same_created_at_cohort(wire):
    # A row admitted in the window but created before it must not inflate the
    # numerator, and a conversation created too close to the window end has not
    # had time to be admitted, so it is excluded from both sides.
    wire['rows'] = [
        _row(capture_id='in-cohort', admitted_at=NOW - 500),
        _row(capture_id='created-before', admitted_at=NOW - 500),
        _row(capture_id='created-at-the-edge', admitted_at=NOW - 100),
    ]
    wire['conversations'] = {
        'in-cohort': _conversation(created_at=datetime.fromtimestamp(NOW - 500, tz=timezone.utc)),
        'created-before': _conversation(created_at=datetime.fromtimestamp(NOW - 2_000, tz=timezone.utc)),
        'created-at-the-edge': _conversation(created_at=datetime.fromtimestamp(NOW - 100, tz=timezone.utc)),
    }
    wire['capture_creates'] = 2
    result = census.census(NOW - 1_000, NOW + 1, now=NOW, firestore_client=object())
    coverage = result['coverage']
    assert coverage['ledger_admits'] == 3
    assert coverage['cohort_admits'] == 1
    assert coverage['excluded_admits'] == 2
    assert coverage['capture_creates'] == 2
    assert coverage['unmatched_creates'] == 1
    assert coverage['ratio'] == 0.5
    assert coverage['settle_seconds'] == census.COVERAGE_SETTLE_SECONDS


def test_latency_excludes_rows_without_end_at_and_counts_them(wire):
    wire['rows'] = [
        _row(capture_id='ended', terminal=True, end_at=NOW - 100, home_ready_at=NOW - 10),
        _row(capture_id='terminal-no-end', terminal=True, end_at=None, admitted_at=NOW - 200),
        _row(capture_id='in-flight', terminal=False, end_at=None, admitted_at=NOW - 200),
        _row(capture_id='no-clock', terminal=False, end_at=None, admitted_at=None),
    ]
    wire['conversations'] = {row['capture_id']: _conversation() for row in wire['rows']}
    result = _census(wire)
    latency = result['latency']
    assert latency['clock_start'] == 'end_at'
    assert latency['clock_basis'] == 'end_at_only'
    assert latency['clock_fallback_count'] == 2
    assert latency['clock_unknown_count'] == 1
    assert latency['event_count'] == 1
    assert latency['p50_seconds'] == 90.0
    assert result['end_types']['user_initiated']['clock_fallback'] == 1


def test_conversation_read_is_field_projected_and_transcript_is_a_boolean(monkeypatch):
    calls = {}

    def fake_snapshot(uid, conversation_id, *, firestore_client=None, field_paths=None):
        calls['field_paths'] = field_paths
        return {'status': 'completed', 'transcript_segments': [{'text': 'secret'}]}

    monkeypatch.setattr(census.conversations_db, 'get_conversation_raw_snapshot', fake_snapshot)
    row = census._conversation(object(), 'owner', 'conversation-1')
    assert calls['field_paths'] == list(census.CONVERSATION_FIELDS)
    assert row['transcript_segments'] is True
    assert 'secret' not in json.dumps(row)


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
