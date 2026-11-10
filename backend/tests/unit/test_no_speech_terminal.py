"""Reversible no-speech terminal: classification, reversibility, no deletion.

Synthetic only: no cloud IO, no audio, no provider. The fake models the narrow
Firestore surface the storage primitive uses, including document update_time,
transaction read-before-write ordering and DELETE_FIELD.
"""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.cloud import firestore

from database import no_speech_terminal as terminal
from database.conversations import is_visible_conversation
from utils.batch_pipeline import no_speech

NOW = datetime.now(timezone.utc)
UID, CID = 'synthetic-owner', 'synthetic-capture'
PATH = ('users', UID, 'conversations', CID)
ROW_PATH = f'users/{UID}/conversations/{CID}'


class Snapshot:
    def __init__(self, data, update_time):
        self._data = data
        self.exists = data is not None
        self.update_time = update_time
        self.reference = None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class Document:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def collection(self, name):
        return Collection(self.client, (*self.path, name))

    def get(self, transaction=None, **kwargs):
        if transaction is not None:
            transaction._assert_read_allowed()
        data = self.client.rows.get(self.path)
        snapshot = Snapshot(data, self.client.revisions.get(self.path))
        snapshot.reference = self
        return snapshot


class Collection:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def document(self, name):
        return Document(self.client, (*self.path, name))


class Transaction:
    def __init__(self, client):
        self.client = client
        self.has_written = False
        self.write_results = []
        self._id = None
        self._max_attempts = 1
        self._read_only = False

    def _begin(self, retry_id=None):
        self._id = retry_id or b'strict'

    def _commit(self):
        return None

    def _rollback(self):
        return None

    def _clean_up(self):
        self._id = None

    def _assert_read_allowed(self):
        if self.has_written:
            raise RuntimeError('read after write')

    def get(self, ref):
        return ref.get(transaction=self)

    def update(self, ref, patch):
        self.has_written = True
        row = self.client.rows[ref.path]
        for key, value in patch.items():
            if value is firestore.DELETE_FIELD:
                row.pop(key, None)
            else:
                row[key] = value
        self.client.tick(ref.path)
        self.write_results.append(SimpleNamespace(update_time=self.client.revisions[ref.path]))

    def set(self, ref, data, merge=False):
        self.has_written = True
        self.client.rows[ref.path] = dict(data)
        self.client.tick(ref.path)
        self.write_results.append(SimpleNamespace(update_time=self.client.revisions[ref.path]))

    def delete(self, ref):
        self.has_written = True
        self.client.rows.pop(ref.path, None)
        self.client.deletes.append(ref.path)


class Client:
    def __init__(self, rows):
        self.rows = {path: dict(row) for path, row in rows.items()}
        self.revisions = {path: NOW for path in rows}
        self.deletes = []
        self.transactions = []
        self._clock = 0

    def tick(self, path):
        self._clock += 1
        self.revisions[path] = NOW + timedelta(seconds=self._clock)

    def collection(self, name):
        return Collection(self, (name,))

    def document(self, path):
        return Document(self, tuple(path.split('/')))

    def transaction(self, max_attempts=None):
        transaction = Transaction(self)
        self.transactions.append(transaction)
        return transaction


def original_row():
    return {
        'record_lane_owner': 'batch_live_v1',
        'server_batch_only': True,
        'status': 'in_progress',
        'created_at': NOW - timedelta(days=1),
        'private_cloud_sync_enabled': True,
        'audio_files': [{'duration': 1.0, 'chunk_timestamps': [1.0]}],
        'transcript_segments': [],
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(terminal, 'stop_quiet_check_for_conversation', lambda *a, **k: None)
    return Client({('users', UID): {'private_cloud_sync_enabled': True}, PATH: original_row()})


def close(client, *, run_id='run-1', speech=0.0, audio=1.0):
    return terminal.close_no_speech(
        UID,
        CID,
        expected_revision=client.revisions[PATH].isoformat(),
        run_id=run_id,
        speech_seconds=speech,
        audio_seconds=audio,
        firestore_client=client,
    )


def test_close_then_restore_restores_original_fields_exactly(client):
    before = dict(client.rows[PATH])
    revision = close(client)
    row = client.rows[PATH]
    assert row['status'] == 'completed'
    assert row['discarded'] is True
    assert row['terminal_no_derived_effects'] is True
    marker = row['no_speech_terminal']
    assert marker['state'] == 'no_speech'
    assert marker['policy'] == terminal.POLICY
    assert marker['run_id'] == 'run-1'
    assert marker['prior']['status'] == {'present': True, 'value': 'in_progress'}
    assert marker['prior']['discarded'] == {'present': False, 'value': None}
    # Audio and content are untouched; nothing is deleted.
    assert row['audio_files'] == before['audio_files']
    assert row['transcript_segments'] == before['transcript_segments']
    assert client.deletes == []

    terminal.restore_no_speech(UID, CID, expected_closed_revision=revision, run_id='run-1', firestore_client=client)
    assert client.rows[PATH] == before
    assert client.deletes == []


def test_close_never_calls_audio_deletion(monkeypatch, client):
    import utils.other.storage as storage

    monkeypatch.setattr(storage, 'delete_conversation_audio_files', Mock(side_effect=AssertionError('deleted')))
    close(client)
    assert client.rows[PATH]['audio_files']


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'status': 'completed'}, 'not_in_progress'),
        ({'discarded': True}, 'already_discarded'),
        ({'deleted': True}, 'row_retired_or_locked'),
        ({'is_locked': True}, 'row_retired_or_locked'),
        ({'finalization_job_id': 'job'}, 'row_retired_or_locked'),
        ({'record_lane_owner': 'batch_sync_v1'}, 'not_batch_live_owner'),
        ({'no_speech_terminal': {'state': 'no_speech'}}, 'already_marked'),
    ],
)
def test_close_refuses_rows_it_does_not_own(client, change, reason):
    client.rows[PATH].update(change)
    with pytest.raises(terminal.NoSpeechConflict) as error:
        close(client)
    assert str(error.value) == reason
    assert client.deletes == []


def test_close_refuses_a_stale_revision(client):
    with pytest.raises(terminal.NoSpeechConflict) as error:
        terminal.close_no_speech(
            UID,
            CID,
            expected_revision='stale',
            run_id='run-1',
            speech_seconds=0.0,
            audio_seconds=1.0,
            firestore_client=client,
        )
    assert str(error.value) == 'revision_changed'


def test_close_refuses_owner_privacy_change(client):
    client.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    with pytest.raises(terminal.NoSpeechConflict) as error:
        close(client)
    assert str(error.value) == 'privacy_changed'


def test_restore_refuses_a_later_edit(client):
    revision = close(client)
    client.rows[PATH]['user_title'] = 'edited'
    client.tick(PATH)
    with pytest.raises(terminal.NoSpeechConflict) as error:
        terminal.restore_no_speech(UID, CID, expected_closed_revision=revision, run_id='run-1', firestore_client=client)
    assert str(error.value) == 'revision_changed'


def test_restore_refuses_a_foreign_run(client):
    revision = close(client)
    with pytest.raises(terminal.NoSpeechConflict) as error:
        terminal.restore_no_speech(UID, CID, expected_closed_revision=revision, run_id='other', firestore_client=client)
    assert str(error.value) == 'not_matching_close'


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
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

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


def test_home_hides_the_closed_row():
    closed = {
        'status': 'completed',
        'discarded': True,
        'terminal_no_derived_effects': True,
        'no_speech_terminal': {'state': 'no_speech'},
    }
    assert is_visible_conversation(closed) is False
    # Export/compliance readers still see the preserved row.
    assert is_visible_conversation(closed, include_discarded=True) is True


def test_discover_rejects_unbounded_pages():
    with pytest.raises(ValueError):
        no_speech.discover(Mock(), limit=0)
    with pytest.raises(ValueError):
        no_speech.discover(Mock(), limit=129)


def test_operator_tool_refuses_apply_when_kill_switch_is_off(monkeypatch, capsys):
    from scripts import mark_no_speech_orphans as tool

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
