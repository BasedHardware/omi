"""Only actual STT outcomes can settle every closed audio span."""

from copy import deepcopy

import pytest

from utils.batch_pipeline import empty_transcription as empty


def row():
    return {
        'server_batch_audio_closed': True,
        'server_batch_audio_start': 100.0,
        'server_batch_audio_end': 200.0,
        'record_projection_revision': 1,
        'home_transcription_pending_at': 'generation-1',
    }


def project(current, start=100.0, end=200.0, outcome='silence'):
    result = deepcopy(current)
    result['record_projection_revision'] += 1
    empty.stamp(current, result, {'start': start, 'end': end, 'terminal_empty_outcome': outcome})
    return result


@pytest.mark.parametrize('outcome', ['silence', 'no_recoverable_speech'])
def test_only_validated_empty_outcomes_settle_the_complete_closed_record(outcome):
    result = project(row(), outcome=outcome)
    assert empty.terminal(result)
    assert not empty.terminal(project(row(), outcome='success'))
    assert not empty.terminal(project(row(), outcome='empty_output_exhausted'))


def test_all_units_must_cover_the_closed_record_without_a_gap():
    first = project(row(), 100, 140)
    assert not empty.terminal(first)
    second = project(first, 150, 200)
    assert not empty.terminal(second)
    final = project(second, 140, 150)
    assert empty.terminal(final)
    assert final[empty.FIELD]['spans'] == [{'start': 100, 'end': 200}]
    assert first[empty.FIELD]['spans'] == [{'start': 100, 'end': 140}]


@pytest.mark.parametrize(
    'changes',
    [
        {'home_transcription_pending_at': 'generation-2'},
        {'episode_transcription_pending_at': 'new-episode-generation'},
        {'record_projection_revision': 100},
        {'server_batch_audio_closed': False},
        {'server_batch_audio_end': 250},
        {'record_upload_sessions': ['still-uploading']},
        {'record_audio_partial': {'reason': 'tail_lagging'}},
    ],
)
def test_old_writer_preserving_unknown_receipt_cannot_settle_new_work(changes):
    result = project(row())
    assert empty.terminal(result)
    result.update(changes)
    assert not empty.terminal(result)


def test_old_projection_invalidates_spans_before_a_new_partial_result():
    result = project(row(), 100, 150)
    result['record_projection_revision'] += 1  # old image ignores the receipt
    assert not empty.terminal(project(result, 150, 200))


def test_kill_switches_off_write_no_new_receipt(monkeypatch):
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'false')
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'false')
    assert empty.FIELD not in project(row())
