"""Operator hides are recorded as ledger terminals only after the real close commits."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from database import pipeline_ledger
from utils.conversations import lifecycle


class _Ref:
    def __init__(self, path):
        self.path = path

    def collection(self, name):
        return _Ref(f'{self.path}/{name}')

    def document(self, name):
        return _Ref(f'{self.path}/{name}')


class _Client:
    def collection(self, name):
        return _Ref(name)


@pytest.fixture
def advance(monkeypatch):
    spy = Mock(return_value=True)
    monkeypatch.setattr(lifecycle.pipeline_ledger, 'advance', spy)
    return spy


def test_no_speech_close_writes_the_no_speech_terminal_with_vad_speech(monkeypatch, advance):
    monkeypatch.setattr(lifecycle.no_speech_terminal_db, 'close_no_speech', Mock(return_value='rev-2'))
    committed = lifecycle.close_no_speech_capture(
        'u',
        'c',
        expected_revision='rev-1',
        run_id='run',
        speech_seconds=3.0,
        audio_seconds=40.0,
        firestore_client=_Client(),
    )
    assert committed == 'rev-2'
    (uid, capture, stage), fields = advance.call_args
    assert (uid, capture, stage) == ('u', 'c', pipeline_ledger.NO_SPEECH)
    assert fields['reason'] == 'no_speech' and fields['speech_seconds'] == 3.0
    assert fields['has_speech'] is False and fields['speech_basis'] == 'vad'
    assert fields['owner_ref'].path == 'users/u'
    assert fields['source_ref'].path == 'users/u/conversations/c'


def test_noise_close_writes_the_noise_terminal(monkeypatch, advance):
    monkeypatch.setattr(lifecycle.stuck_backfill_db, 'close_noise', Mock(return_value='rev-9'))
    committed = lifecycle.close_stuck_backfill_noise(
        'u',
        'c',
        expected_revision='rev-8',
        cutoff=datetime(2026, 11, 1, tzinfo=timezone.utc),
        expected_session_revision=None,
        run_id='run',
        firestore_client=_Client(),
    )
    assert committed == 'rev-9'
    (uid, capture, stage), fields = advance.call_args
    assert (uid, capture, stage) == ('u', 'c', pipeline_ledger.NOISE) and fields['reason'] == 'noise'
    assert fields['source_ref'].path == 'users/u/conversations/c'


def test_a_refused_close_writes_no_ledger_terminal(monkeypatch, advance):
    monkeypatch.setattr(lifecycle.no_speech_terminal_db, 'close_no_speech', Mock(side_effect=RuntimeError('conflict')))
    with pytest.raises(RuntimeError):
        lifecycle.close_no_speech_capture(
            'u', 'c', expected_revision='rev-1', run_id='run', speech_seconds=3.0, audio_seconds=40.0
        )
    advance.assert_not_called()
