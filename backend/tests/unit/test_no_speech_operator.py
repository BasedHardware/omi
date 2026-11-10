"""Synthetic strict-VAD/operator contracts; no cloud credentials or IO."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from google.api_core.exceptions import PreconditionFailed

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from scripts import mark_no_speech_orphans as tool
from tests.unit import test_no_speech_terminal as storage_tests
from utils.batch_pipeline import no_speech, no_speech_undo

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
    assert no_speech._classify(speech_seconds=0.0, raw_objects=0, legacy_objects=0) == 'coverage_incomplete'
    assert no_speech._classify(speech_seconds=0.0, raw_objects=0, legacy_objects=2) == 'retained_audio_unmeasured'


def test_measure_row_decode_failure_is_untouched(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [{'path': 'raw-live/x'}])
    monkeypatch.setattr(no_speech, '_measure', Mock(side_effect=ValueError('decode')))
    assert no_speech._measure_row(object(), UID, CID, original_row()) == ('decode_failed', None, None, 1, 0)


def test_measure_row_privacy_blocked_propagates(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [{'path': 'raw-live/x'}])
    monkeypatch.setattr(no_speech, '_measure', Mock(side_effect=BatchPrivacyBlocked('blocked')))
    with pytest.raises(BatchPrivacyBlocked):
        no_speech._measure_row(object(), UID, CID, original_row())


def test_measure_row_no_audio_and_legacy(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [])
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [])
    assert no_speech._measure_row(object(), UID, CID, original_row()) == ('coverage_incomplete', None, None, 0, 0)
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [{'path': 'chunks/x'}])
    assert no_speech._measure_row(object(), UID, CID, original_row()) == ('retained_audio_unmeasured', None, None, 0, 1)


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
        {
            ('users', UID): {'private_cloud_sync_enabled': True},
            storage_tests.PATH: original_row(),
            storage_tests.PRIVACY_PATH: {'generation': 7},
        }
    )
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-encryption-secret-32-characters')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(tool, 'get_firestore_client', lambda: client)
    dependencies = SimpleNamespace(
        planner=no_speech,
        store=lambda *a, **kw: SimpleNamespace(
            client=client, namespace='batch_pipeline_test_nospeech', run=lambda body: body(Mock())
        ),
        storage=Mock(return_value=Mock()),
        write_cursor=Mock(),
    )
    monkeypatch.setattr(tool, '_plan_dependencies', lambda: dependencies)
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
    monkeypatch.setattr(no_speech, 'discover', lambda *a, **kw: ([ROW_PATH], None))
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


def test_plan_keeps_upload_pending_row_local(monkeypatch):
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    pending = {**original_row(), 'record_upload_sessions': ['active-upload']}
    monkeypatch.setattr(
        no_speech, '_snapshot', lambda store, uid, cid: (pending if cid == 'pending' else original_row(), 'rev-1')
    )
    planned = no_speech.plan_no_speech(
        FakeStore(original_row()), [f'users/{UID}/conversations/pending', ROW_PATH], Mock()
    )
    assert [row['disposition'] for row in planned['entries']] == ['upload_pending', 'no_speech']
    assert planned['entries'][0]['exit'] == 'operator_review'
    assert no_speech.summary(planned)['actionable'] == 1


@pytest.mark.parametrize(
    'reason,expected', [('privacy_skipped', 'privacy_skipped'), ('unexpected-private-label', 'proof_refused')]
)
def test_plan_normalizes_refusal_exits_per_row(monkeypatch, reason, expected):
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(
        no_speech, '_snapshot', lambda store, uid, cid: ({**original_row(), 'odd': cid == 'odd'}, 'rev-1')
    )
    monkeypatch.setattr(no_speech, 'candidate_refusal', lambda row, now: reason if row.get('odd') else None)
    planned = no_speech.plan_no_speech(FakeStore(original_row()), [f'users/{UID}/conversations/odd', ROW_PATH], Mock())
    assert [row['disposition'] for row in planned['entries']] == [expected, 'no_speech']
    report = no_speech.summary(planned)
    assert report['actionable'] == 1
    assert 'unexpected-private-label' not in json.dumps(report)


def private_ledger(tmp_path, client):
    tmp_path.chmod(0o700)
    path = tmp_path / 'page.jsonl'
    ledger = tool.Ledger(path, create=True)
    ledger.prepare(
        {
            'row_sha256': no_speech.row_state(original_row()),
            'revision': client.revisions[storage_tests.PATH].isoformat(),
        },
        UID,
        CID,
        'run-1',
    )
    ledger.close()
    return path


def test_prepared_only_cli_undo_needs_no_encryption_or_storage(monkeypatch, tmp_path, capsys):
    client = operator_client(monkeypatch)
    before = dict(client.rows[storage_tests.PATH])
    path = private_ledger(tmp_path, client)
    storage_tests.close(client)  # Simulate process death before ledger.committed.
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    storage = Mock(side_effect=OSError('storage unavailable'))
    monkeypatch.setattr(tool, '_plan_dependencies', storage)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'false')
    tool.main(['--undo', '--apply', '--ledger', str(path)])
    assert json.loads(capsys.readouterr().out)['outcomes'] == {'restored': 1}
    assert client.rows[storage_tests.PATH] == before
    assert client.deletes == []
    storage.assert_not_called()


def test_empty_write_results_apply_records_unknown_then_undo_restores(monkeypatch, tmp_path, capsys):
    client = operator_client(monkeypatch)
    before = dict(client.rows[storage_tests.PATH])
    original_snapshot = no_speech._snapshot
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(no_speech, '_snapshot', original_snapshot)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'true')
    store = FakeStore(original_row())
    store.client = client
    planned = no_speech.plan_no_speech(store, [ROW_PATH], Mock(), run_id='run-1')

    def missing_result(transaction):
        transaction.write_results = []

    monkeypatch.setattr(storage_tests.Transaction, '_commit', missing_result)
    tmp_path.chmod(0o700)
    path = tmp_path / 'unknown.jsonl'
    ledger = tool.Ledger(path, create=True)
    try:
        outcomes = no_speech.apply_no_speech(store, planned, planned['plan_sha256'], Mock(), ledger=ledger)
        entries = ledger.entries()
    finally:
        ledger.close()
    assert outcomes == {'committed_revision_unknown': 1}
    assert entries[0]['committed_revision'] == storage_tests.terminal.COMMITTED_REVISION_UNKNOWN
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    monkeypatch.setattr(tool, '_plan_dependencies', Mock(side_effect=AssertionError('undo touched GCS')))
    tool.main(['--undo', '--apply', '--ledger', str(path)])
    assert json.loads(capsys.readouterr().out)['outcomes'] == {'restored': 1}
    assert client.rows[storage_tests.PATH] == before
    assert client.deletes == []


@pytest.mark.parametrize(
    'change',
    [
        {'status': 'processing'},
        {'discarded': False},
        {'terminal_no_derived_effects': False},
        {'no_speech_terminal': {'run_id': 'foreign'}},
    ],
)
def test_prepared_only_undo_refuses_foreign_or_changed_closed_shape(monkeypatch, change):
    client = operator_client(monkeypatch)
    storage_tests.close(client)
    client.rows[storage_tests.PATH].update(change)
    client.tick(storage_tests.PATH)
    before = dict(client.rows[storage_tests.PATH])
    entry = {'uid': UID, 'conversation_id': CID, 'run_id': 'run-1', 'committed_revision': None}
    result = no_speech.undo_no_speech(SimpleNamespace(client=client), [entry], ledger=Mock())
    assert result == {'not_matching_close': 1}
    assert client.rows[storage_tests.PATH] == before
    assert client.deletes == []


def test_prepared_only_undo_fences_edits_after_resolution(monkeypatch):
    client = operator_client(monkeypatch)
    storage_tests.close(client)
    snapshot = no_speech_undo._snapshot

    def racing_snapshot(store, uid, cid):
        row, revision = snapshot(store, uid, cid)
        client.rows[storage_tests.PATH]['user_title'] = 'later edit'
        client.tick(storage_tests.PATH)
        return row, revision

    monkeypatch.setattr(no_speech_undo, '_snapshot', racing_snapshot)
    entry = {'uid': UID, 'conversation_id': CID, 'run_id': 'run-1', 'committed_revision': None}
    assert no_speech.undo_no_speech(SimpleNamespace(client=client), [entry], ledger=Mock()) == {'revision_changed': 1}
    assert client.rows[storage_tests.PATH]['discarded'] is True
    assert client.rows[storage_tests.PATH]['user_title'] == 'later edit'


def test_undo_dry_run_counts_prepared_entries_without_secrets_or_storage(monkeypatch, tmp_path, capsys):
    client = operator_client(monkeypatch)
    path = private_ledger(tmp_path, client)
    storage_tests.close(client)
    before = dict(client.rows[storage_tests.PATH])
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    monkeypatch.setattr(tool, '_plan_dependencies', Mock(side_effect=AssertionError('undo touched GCS')))
    tool.main(['--undo', '--ledger', str(path)])
    assert json.loads(capsys.readouterr().out)['outcomes'] == {'would_restore': 1}
    assert client.rows[storage_tests.PATH] == before


@pytest.mark.parametrize(
    'args,tier,emulator',
    [
        ([], 'ro-dev', False),
        (['--apply', '--approve-plan-sha256', 'digest', '--ledger', '/private/ledger'], 'ro-prod', False),
        ([], 'prod-operator', True),
        (['--limit', '0'], 'prod-operator', False),
        (['--limit', '129'], 'prod-operator', False),
        (['--pace-seconds', '0'], 'prod-operator', False),
        (['--pace-seconds', '61'], 'prod-operator', False),
        (['--apply', '--approve-plan-sha256', 'digest'], 'prod-operator', False),
        (['--apply', '--ledger', '/private/ledger'], 'prod-operator', False),
        (['--undo', '--ledger', '/private/ledger', '--after-file', '/private/cursor'], 'prod-operator', False),
        (['--undo', '--ledger', '/private/ledger', '--next-file', '/private/cursor'], 'prod-operator', False),
        (['--after-file', '/private/cursor', '--next-file', '/private/cursor'], 'prod-operator', False),
    ],
)
def test_cli_guard_table_is_counts_only_before_any_io(monkeypatch, capsys, args, tier, emulator):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'true')
    if emulator:
        monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:9999')
    else:
        monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    run = Mock(side_effect=AssertionError('invalid request performed IO'))
    monkeypatch.setattr(tool, 'run', run)
    with pytest.raises(SystemExit) as error:
        tool.main(args)
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out) == {'operation': no_speech.OPERATION, 'outcome': 'invalid_arguments'}
    run.assert_not_called()


def test_ledger_refuses_mode_symlink_and_reusing_page_path(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / 'ledger.jsonl'
    path.write_text('private existing bytes')
    path.chmod(0o644)
    with pytest.raises(ValueError, match='private ledger mode required'):
        tool.Ledger(path)
    path.chmod(0o600)
    link = tmp_path / 'ledger-link.jsonl'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='private ledger path required'):
        tool.Ledger(link)
    with pytest.raises(FileExistsError):
        tool.Ledger(path, create=True)
    assert path.read_text() == 'private existing bytes'


@pytest.mark.parametrize('apply', [False, True])
def test_fresh_process_undo_imports_without_encryption_secret(tmp_path, apply):
    tmp_path.chmod(0o700)
    path = tmp_path / 'empty-ledger.jsonl'
    path.touch(mode=0o600)
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            'ENCRYPTION_SECRET',
            'GOOGLE_APPLICATION_CREDENTIALS',
            'CLOUDSDK_CONFIG',
            'CLOUDSDK_CORE_ACCOUNT',
            'SERVICE_ACCOUNT_JSON',
            'FIREBASE_AUTH_CREDENTIALS_PATH',
        }
    }
    env['GCP_AGENT_TIER'] = 'prod-operator'
    env['NO_SPEECH_TERMINAL_ENABLED'] = 'false'
    env.pop('FIRESTORE_EMULATOR_HOST', None)
    code = """
import socket
import sys

def blocked(*a, **kw):
    raise AssertionError('unexpected network or audio dependency')

socket.create_connection = blocked
socket.socket.connect = blocked
from scripts import mark_no_speech_orphans as tool
tool.get_firestore_client = lambda: object()
tool._plan_dependencies = blocked
tool.main(sys.argv[1:])
"""
    args = ['--undo', '--ledger', str(path)] + (['--apply'] if apply else [])
    result = subprocess.run(
        [sys.executable, '-c', code, *args],
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['outcomes'] == ({} if apply else {'would_restore': 0})


def test_apply_refuses_privacy_generation_changed_after_reproof(monkeypatch):
    client = operator_client(monkeypatch)
    original_snapshot = no_speech._snapshot
    plan_for(monkeypatch, 'no_speech', speech=0.0, audio=1.0)
    monkeypatch.setattr(no_speech, '_snapshot', original_snapshot)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'true')
    store = FakeStore(original_row())
    store.client = client
    planned = no_speech.plan_no_speech(store, [ROW_PATH], Mock(), run_id='run-1')
    before = dict(client.rows[storage_tests.PATH])
    original_revision = client.revisions[storage_tests.PATH]
    privacy_read = Mock(return_value=7)
    monkeypatch.setattr(no_speech, 'privacy_read', privacy_read)

    def revoke_and_reenable(*args):
        # prepare follows the real _reprove. Consent is enabled again and the
        # conversation revision is unchanged, but the approval is now stale.
        privacy_read.assert_called_once_with(ANY, UID, (CID,), expected_generation=7)
        client.rows[storage_tests.PRIVACY_PATH]['generation'] = 9
        client.tick(storage_tests.PRIVACY_PATH)
        return 'prepared-token'

    ledger = Mock()
    ledger.prepare.side_effect = revoke_and_reenable
    assert no_speech.apply_no_speech(store, planned, planned['plan_sha256'], Mock(), ledger=ledger) == {
        'privacy_changed': 1
    }
    ledger.prepare.assert_called_once()
    ledger.committed.assert_not_called()
    assert client.rows[storage_tests.PATH] == before
    assert client.revisions[storage_tests.PATH] == original_revision
    assert all(not txn.has_written for txn in client.transactions)
    assert client.deletes == []


def coverage_operator(monkeypatch, specs):
    """Actual listing, coverage, VAD wiring, plan/reproof and lifecycle storage."""
    client = operator_client(monkeypatch)
    start = storage_tests.NOW - storage_tests.timedelta(days=1)
    client.rows[storage_tests.PATH].update(started_at=start, finished_at=start + storage_tests.timedelta(seconds=8))
    blobs, pcm_by_path = [], {}

    def replace_sources(specs):
        blobs.clear()
        pcm_by_path.clear()
        for index, (offset, duration, value) in enumerate(specs):
            path = f'raw-live/{UID}/{CID}/{index}.flac'
            metadata = {
                'capture_start': str(start.timestamp() + offset),
                'capture_end': str(start.timestamp() + offset + duration),
                'gap_count': '0',
            }
            blobs.append(
                SimpleNamespace(
                    name=path, generation=1, metadata=metadata, size=round(duration * 32000), metageneration=1
                )
            )
            pcm_by_path[path] = value * round(duration * 16000)

    replace_sources(specs)
    storage = Mock()
    storage.bucket.return_value.list_blobs.side_effect = lambda **kwargs: list(reversed(blobs))
    monkeypatch.setattr(no_speech, 'read_reference', lambda client, ref, *a, **kw: pcm_by_path[ref['path']])
    monkeypatch.setattr(no_speech, 'privacy_read', lambda *a, **kw: 7)
    monkeypatch.setattr(no_speech, '_job_exists', lambda *a: False)
    # Every decoded sample is treated as speech; duplicate frames would cross
    # the ten-second threshold if overlaps were concatenated instead of trimmed.
    vad = Mock(side_effect=lambda pcm: [{'duration': len(pcm) / 32000}])
    monkeypatch.setattr(no_speech, 'offline_pcm_speech_segments', vad)
    monkeypatch.setenv('NO_SPEECH_TERMINAL_ENABLED', 'true')
    store = FakeStore(original_row())
    store.client = client
    return client, store, storage, replace_sources, vad


def test_gap_page_is_coverage_incomplete_and_never_closes(monkeypatch):
    client, store, storage, _, vad = coverage_operator(monkeypatch, [(0, 3, b'\x01\0'), (4, 4, b'\x01\0')])
    before = dict(client.rows[storage_tests.PATH])
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    assert planned['entries'][0]['disposition'] == 'coverage_incomplete'
    report = no_speech.summary(planned)
    assert report['dispositions'] == {'coverage_incomplete': 1}
    assert report['exits'] == {'coverage_incomplete': 'operator_review'}
    assert report['actionable'] == 0
    ledger = Mock()
    assert no_speech.apply_no_speech(store, planned, planned['plan_sha256'], storage, ledger=ledger) == {
        'coverage_incomplete': 1
    }
    vad.assert_not_called()
    ledger.prepare.assert_not_called()
    assert client.rows[storage_tests.PATH] == before
    assert client.transactions == []


@pytest.mark.parametrize('specs', [[(0, 4, b'\x01\0'), (4, 4, b'\x01\0')], [(0, 6, b'\x01\0'), (2, 6, b'\x01\0')]])
def test_full_coverage_classifies_and_counts_overlaps_once(monkeypatch, specs):
    _, store, storage, _, vad = coverage_operator(monkeypatch, specs)
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    entry = planned['entries'][0]
    assert entry['disposition'] == 'no_speech'
    assert entry['speech_seconds'] == entry['audio_seconds'] == 8
    assert len(vad.call_args.args[0]) == 8 * 32000


@pytest.mark.parametrize(
    'added,expected',
    [
        ((2, 4, b'\x02\0'), 'coverage_incomplete'),
        ((8, 1, b'\x01\0'), 'coverage_incomplete'),
        ((2, 4, b'\x01\0'), 'closed'),
    ],
)
def test_added_object_must_pass_fresh_coverage_reproof(monkeypatch, added, expected):
    client, store, storage, replace, vad = coverage_operator(monkeypatch, [(0, 8, b'\x01\0')])
    before = dict(client.rows[storage_tests.PATH])
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    assert planned['entries'][0]['disposition'] == 'no_speech'
    replace([(0, 8, b'\x01\0'), added])
    ledger = Mock()
    assert no_speech.apply_no_speech(store, planned, planned['plan_sha256'], storage, ledger=ledger) == {expected: 1}
    assert storage.bucket.return_value.list_blobs.call_count == 2
    if expected == 'coverage_incomplete':
        ledger.prepare.assert_not_called()
        assert client.rows[storage_tests.PATH] == before
        assert client.transactions == []
    else:
        assert client.rows[storage_tests.PATH]['discarded'] is True
        assert len(vad.call_args.args[0]) == 8 * 32000


def test_missing_chunk_at_apply_is_coverage_incomplete(monkeypatch):
    client, store, storage, replace, _ = coverage_operator(monkeypatch, [(0, 4, b'\x01\0'), (4, 4, b'\x01\0')])
    before = dict(client.rows[storage_tests.PATH])
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    replace([(0, 4, b'\x01\0')])
    ledger = Mock()
    assert no_speech.apply_no_speech(store, planned, planned['plan_sha256'], storage, ledger=ledger) == {
        'coverage_incomplete': 1
    }
    ledger.prepare.assert_not_called()
    assert client.rows[storage_tests.PATH] == before


@pytest.mark.parametrize('metadata_changed', [False, True])
def test_coverage_download_fences_listed_metadata_version(monkeypatch, metadata_changed):
    from utils.batch_pipeline import source_audio

    client, store, storage, _, vad = coverage_operator(monkeypatch, [(0, 8, b'\x01\0')])
    listed = storage.bucket.return_value.list_blobs()[0]
    raw = b'\x01\0' * (8 * 16000)
    listed.metadata.update(sha256=hashlib.sha256(raw).hexdigest(), format='pcm16le', sample_rate='16000', channels='1')
    downloaded = storage.bucket.return_value.blob.return_value
    downloaded.download_as_bytes.side_effect = (
        PreconditionFailed('synthetic metageneration mismatch') if metadata_changed else lambda **kwargs: raw
    )
    monkeypatch.setattr(no_speech, 'read_reference', source_audio.read_reference)
    before = dict(client.rows[storage_tests.PATH])
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    assert planned['entries'][0]['disposition'] == ('coverage_incomplete' if metadata_changed else 'no_speech')
    downloaded.reload.assert_not_called()
    assert downloaded.download_as_bytes.call_args.kwargs['if_generation_match'] == 1
    assert downloaded.download_as_bytes.call_args.kwargs['if_metageneration_match'] == 1
    if metadata_changed:
        vad.assert_not_called()
        ledger = Mock()
        assert no_speech.apply_no_speech(store, planned, planned['plan_sha256'], storage, ledger=ledger) == {
            'coverage_incomplete': 1
        }
        ledger.prepare.assert_not_called()
        assert client.rows[storage_tests.PATH] == before


@pytest.mark.parametrize('field', ['size', 'metageneration'])
def test_coverage_refuses_unversioned_listing_metadata(monkeypatch, field):
    _, store, storage, _, vad = coverage_operator(monkeypatch, [(0, 8, b'\x01\0')])
    setattr(storage.bucket.return_value.list_blobs()[0], field, None)
    planned = no_speech.plan_no_speech(store, [ROW_PATH], storage)
    assert planned['entries'][0]['disposition'] == 'coverage_incomplete'
    vad.assert_not_called()
