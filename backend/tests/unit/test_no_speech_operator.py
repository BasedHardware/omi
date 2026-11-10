"""Synthetic strict-VAD/operator contracts; no cloud credentials or IO."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from scripts import mark_no_speech_orphans as tool
from tests.unit import test_no_speech_terminal as storage_tests
from utils.batch_pipeline import no_speech

UID, CID = storage_tests.UID, storage_tests.CID
ROW_PATH = storage_tests.ROW_PATH
original_row = storage_tests.original_row


@pytest.mark.parametrize(
    'speech,expected',
    [(0.0, 'no_speech'), (9.999, 'no_speech'), (10.0, 'has_speech'), (10.001, 'has_speech')],
)
def test_classification_threshold(speech, expected):
    assert no_speech._classify(speech_seconds=speech, raw_objects=1, legacy_objects=0) == expected


def test_classification_without_retained_audio():
    assert no_speech._classify(speech_seconds=0.0, raw_objects=0, legacy_objects=0) == 'no_retained_audio'
    assert no_speech._classify(speech_seconds=0.0, raw_objects=0, legacy_objects=2) == 'retained_audio_unmeasured'


def test_measure_row_decode_failure_is_untouched(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [{'path': 'raw-live/x'}])
    monkeypatch.setattr(no_speech, '_measure', Mock(side_effect=ValueError('decode')))
    assert no_speech._measure_row(object(), UID, CID) == ('decode_failed', None, None, 1, 0)


def test_measure_row_privacy_blocked_propagates(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [{'path': 'raw-live/x'}])
    monkeypatch.setattr(no_speech, '_measure', Mock(side_effect=BatchPrivacyBlocked('blocked')))
    with pytest.raises(BatchPrivacyBlocked):
        no_speech._measure_row(object(), UID, CID)


def test_measure_row_no_audio_and_legacy(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [])
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [])
    assert no_speech._measure_row(object(), UID, CID) == ('no_retained_audio', None, None, 0, 0)
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [{'path': 'chunks/x'}])
    assert no_speech._measure_row(object(), UID, CID) == ('retained_audio_unmeasured', None, None, 0, 1)


class FakeStore:
    namespace = 'batch_pipeline_test_nospeech'

    def __init__(self, row):
        self.row = row
        self.client = Mock()
        self.runs = 0

    def run(self, body):
        self.runs += 1
        return body(Mock())


def plan_for(monkeypatch, disposition, *, speech=None, audio=None):
    store = FakeStore(original_row())
    monkeypatch.setattr(no_speech, 'privacy_read', lambda *a, **k: 7)
    monkeypatch.setattr(no_speech, '_snapshot', lambda *a, **k: (original_row(), 'rev-1'))
    monkeypatch.setattr(no_speech, '_job_exists', lambda *a, **k: False)
    monkeypatch.setattr(
        no_speech,
        '_measure_row',
        lambda *a, **k: (disposition, speech, audio, 1 if speech is not None else 0, 0),
    )
    return no_speech.plan_no_speech(store, [ROW_PATH], object(), run_id='run-1')


def test_plan_marks_only_actionable_rows(monkeypatch):
    planned = plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    entry = planned['entries'][0]
    assert entry['disposition'] == 'no_speech'
    assert entry['exit'] == 'operator_undo_restores_original_fields'
    assert entry['row_sha256'] and entry['revision'] == 'rev-1' and entry['privacy_generation'] == 7
    report = no_speech.summary(planned)
    assert report['actionable'] == 1
    assert report['measured_speech_seconds'] == 0.0
    assert UID not in json.dumps(report) and CID not in json.dumps(report)


def test_plan_leaves_decode_and_privacy_rows_untouched(monkeypatch):
    for disposition in ('decode_failed', 'privacy_blocked', 'has_speech', 'retained_audio_unmeasured'):
        planned = plan_for(monkeypatch, disposition, speech=12.0, audio=12.0)
        entry = planned['entries'][0]
        assert entry['disposition'] == disposition
        assert 'row_sha256' not in entry
        assert no_speech.summary(planned)['actionable'] == 0


def test_apply_refuses_when_kill_switch_is_off(monkeypatch):
    planned = plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(no_speech, 'no_speech_terminal_enabled', lambda: False)
    monkeypatch.setattr(no_speech.lifecycle, 'close_no_speech_capture', Mock(side_effect=AssertionError('closed')))
    outcomes = no_speech.apply_no_speech(
        FakeStore(original_row()), planned, planned['plan_sha256'], object(), ledger=Mock()
    )
    assert outcomes == {'disabled': 1}


def test_apply_skips_non_actionable_rows(monkeypatch):
    planned = plan_for(monkeypatch, 'decode_failed')
    monkeypatch.setattr(no_speech, 'no_speech_terminal_enabled', lambda: True)
    monkeypatch.setattr(no_speech.lifecycle, 'close_no_speech_capture', Mock(side_effect=AssertionError('closed')))
    outcomes = no_speech.apply_no_speech(
        FakeStore(original_row()), planned, planned['plan_sha256'], object(), ledger=Mock()
    )
    assert outcomes == {'decode_failed': 1}


def test_apply_requires_the_approved_digest(monkeypatch):
    planned = plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    with pytest.raises(ValueError):
        no_speech.apply_no_speech(FakeStore(original_row()), planned, 'wrong', object(), ledger=Mock())


def test_discover_rejects_unbounded_pages():
    with pytest.raises(ValueError):
        no_speech.discover(Mock(), limit=0)
    with pytest.raises(ValueError):
        no_speech.discover(Mock(), limit=129)


def test_operator_tool_refuses_apply_when_kill_switch_is_off(monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(tool, 'no_speech_terminal_enabled', lambda: False)
    with pytest.raises(SystemExit) as error:
        tool.main(['--apply', '--approve-plan-sha256', 'digest', '--ledger', '/tmp/ledger.jsonl'])
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        'operation': no_speech.OPERATION,
        'outcome': 'invalid_arguments',
    }


def operator_client(monkeypatch):
    client = storage_tests.Client(
        {('users', UID): {'private_cloud_sync_enabled': True}, storage_tests.PATH: original_row()}
    )
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-encryption-secret-32-characters')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(tool, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(
        tool,
        'FirestoreStore',
        lambda *a, **kw: SimpleNamespace(
            client=client, namespace='batch_pipeline_test_nospeech', run=lambda body: body(Mock())
        ),
    )
    monkeypatch.setattr(tool, 'create_storage_client', Mock(return_value=Mock()))
    monkeypatch.setattr(no_speech.time, 'sleep', lambda *a: None)
    return client


def test_disabled_cli_undo_restores_valid_private_ledger(monkeypatch, tmp_path, capsys):
    client = operator_client(monkeypatch)
    before = dict(client.rows[storage_tests.PATH])
    tmp_path.chmod(0o700)
    ledger_path = tmp_path / 'undo.jsonl'
    ledger = tool.Ledger(ledger_path, create=True)
    try:
        entry = {
            'row_sha256': no_speech.row_state(before),
            'revision': client.revisions[storage_tests.PATH].isoformat(),
        }
        token = ledger.prepare(entry, UID, CID, 'run-1')
        committed = storage_tests.close(client)
        ledger.committed(token, committed)
    finally:
        ledger.close()
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'false')
    # Both the CLI gate and lower-level undo must allow this rescue path.
    tool.main(['--undo', '--apply', '--ledger', str(ledger_path)])
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['outcomes'] == {'restored': 1}
    assert report['undo'] is True
    assert client.rows[storage_tests.PATH] == before
    assert client.deletes == []
    assert UID not in output and CID not in output and str(ledger_path) not in output


def test_cli_reconstructs_approved_page_and_reports_success(monkeypatch, tmp_path, capsys):
    client = operator_client(monkeypatch)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'true')
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(
        no_speech, '_snapshot', lambda *a: (original_row(), client.revisions[storage_tests.PATH].isoformat())
    )
    monkeypatch.setattr(tool, 'discover', lambda *a, **kw: ([ROW_PATH], None))
    monkeypatch.setattr(no_speech, '_reprove', lambda *a: (UID, CID, 0.0, 1.0))
    tmp_path.chmod(0o700)
    ledger_path = tmp_path / 'apply.jsonl'
    # Dry-run and a separate apply invocation must reconstruct the same digest.
    tool.main([])
    dry = json.loads(capsys.readouterr().out)
    tool.main(['--apply', '--approve-plan-sha256', dry['plan_sha256'], '--ledger', str(ledger_path)])
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['plan_sha256'] == dry['plan_sha256']
    assert report['outcomes'] == {'closed': 1}
    assert report['outcome_exits']['closed'] == 'operator_undo_restores_original_fields'
    ledger = tool.Ledger(ledger_path)
    try:
        entries = ledger.entries()
    finally:
        ledger.close()
    assert len(entries) == 1 and entries[0]['committed_revision'] == client.revisions[storage_tests.PATH].isoformat()
    assert UID not in output and CID not in output
    assert client.deletes == []


def test_plan_identity_changes_with_row_proof(monkeypatch):
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    store = FakeStore(original_row())
    first = no_speech.plan_no_speech(store, [ROW_PATH], Mock())
    second = no_speech.plan_no_speech(store, [ROW_PATH], Mock())
    assert first == second
    monkeypatch.setattr(no_speech, '_snapshot', lambda *a: (original_row(), 'new-revision'))
    changed = no_speech.plan_no_speech(store, [ROW_PATH], Mock())
    assert changed['run_id'] != first['run_id']
    assert changed['plan_sha256'] != first['plan_sha256']


def test_apply_rejects_changed_row_before_ledger_or_close(monkeypatch):
    planned = plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(no_speech, 'no_speech_terminal_enabled', lambda: True)
    monkeypatch.setattr(no_speech, '_snapshot', lambda *a: (original_row(), 'changed'))
    close = Mock(side_effect=AssertionError('must not close'))
    monkeypatch.setattr(no_speech.lifecycle, 'close_no_speech_capture', close)
    ledger = Mock()
    assert no_speech.apply_no_speech(
        FakeStore(original_row()), planned, planned['plan_sha256'], Mock(), ledger=ledger
    ) == {'state_changed': 1}
    ledger.prepare.assert_not_called()
    close.assert_not_called()
