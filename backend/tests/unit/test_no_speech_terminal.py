"""Reversible no-speech terminal: classification, reversibility, no deletion.

Synthetic only: no cloud IO, no audio, no provider. The fake models the narrow
Firestore surface the storage primitive uses, including document update_time,
transaction read-before-write ordering and DELETE_FIELD.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from google.cloud import firestore

from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key
from database import no_speech_terminal as terminal
from database.conversations import is_visible_conversation
from database import quiet_check_retirement

NOW = datetime.now(timezone.utc)
UID, CID = 'synthetic-owner', 'synthetic-capture'
PATH = ('users', UID, 'conversations', CID)
PRIVACY_PATH = (PRIVACY_COLLECTION, privacy_owner_key(UID))
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
def client():
    return Client({('users', UID): {'private_cloud_sync_enabled': True}, PATH: original_row()})


def close(client, *, run_id='run-1', speech=0.0, audio=1.0, expected_privacy_generation=None):
    return terminal.close_no_speech(
        UID,
        CID,
        expected_revision=client.revisions[PATH].isoformat(),
        run_id=run_id,
        speech_seconds=speech,
        audio_seconds=audio,
        firestore_client=client,
        expected_privacy_generation=expected_privacy_generation,
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


def test_close_preserves_retained_audio_and_never_deletes_row(client):
    audio = client.rows[PATH]['audio_files']
    close(client)
    assert client.rows[PATH]['audio_files'] == audio
    assert client.deletes == []


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'status': 'completed'}, 'not_in_progress'),
        ({'discarded': True}, 'already_discarded'),
        ({'deleted': True}, 'row_retired_or_locked'),
        ({'sync_merged_into': 'successor'}, 'row_retired_or_locked'),
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


def test_home_hides_the_closed_row(client):
    close(client)
    closed = client.rows[PATH]
    assert is_visible_conversation(closed) is False
    # Export/compliance readers still see the preserved row.
    assert is_visible_conversation(closed, include_discarded=True) is True


def test_close_returns_receipt_when_post_commit_io_would_fail(monkeypatch, client):
    def fail(*args, **kwargs):
        raise OSError('injected post-commit outage')

    def commit(transaction):
        # The commit result is available, but every subsequent read/retirement
        # fails. Close must return that result without touching either service.
        monkeypatch.setattr(Document, 'get', fail)
        monkeypatch.setattr(client, 'collection', fail)
        monkeypatch.setattr(client, 'transaction', fail)

    monkeypatch.setattr(Transaction, '_commit', commit)
    committed = close(client)
    assert committed == client.revisions[PATH].isoformat()
    assert client.rows[PATH]['no_speech_terminal']['run_id'] == 'run-1'
    assert len(client.transactions) == 1


def test_restore_preserves_existing_quiet_check(client):
    quiet_path = ('conversation_finalization_jobs', quiet_check_retirement.quiet_check_id(UID, CID))
    quiet = {
        'kind': 'listen_quiet_check',
        'status': 'waiting_quiet',
        'dispatch_generation': 3,
        'due_at': NOW,
        'reconcile_after_at': NOW,
    }
    client.rows[quiet_path] = dict(quiet)
    client.revisions[quiet_path] = NOW
    before = dict(client.rows[PATH])
    committed = close(client)
    assert client.rows[quiet_path] == quiet
    assert client.revisions[quiet_path] == NOW
    terminal.restore_no_speech(UID, CID, expected_closed_revision=committed, run_id='run-1', firestore_client=client)
    assert client.rows[PATH] == before
    assert client.rows[quiet_path] == quiet
    assert client.revisions[quiet_path] == NOW


@pytest.mark.parametrize('discarded,effects', [(False, False), (None, None), (False, True)])
def test_restore_preserves_present_field_values(client, discarded, effects):
    client.rows[PATH].update(discarded=discarded, terminal_no_derived_effects=effects)
    before = dict(client.rows[PATH])
    committed = close(client)
    terminal.restore_no_speech(UID, CID, expected_closed_revision=committed, run_id='run-1', firestore_client=client)
    assert client.rows[PATH] == before


@pytest.mark.parametrize('row_flag,custom_stt', [(False, False), (None, False), (True, True)])
def test_close_enforces_canonical_row_privacy(client, row_flag, custom_stt):
    if row_flag is None:
        client.rows[PATH].pop('private_cloud_sync_enabled')
    else:
        client.rows[PATH]['private_cloud_sync_enabled'] = row_flag
    client.rows[PATH]['uses_custom_stt'] = custom_stt
    before = dict(client.rows[PATH])
    with pytest.raises(terminal.NoSpeechConflict, match='^privacy_changed$'):
        close(client)
    assert client.rows[PATH] == before
    assert client.deletes == []


@pytest.mark.parametrize('results', [[], None, [None], [SimpleNamespace(update_time=None)]])
def test_close_records_unknown_revision_without_raising_after_commit(monkeypatch, client, results):
    def commit(transaction):
        transaction.write_results = results

    monkeypatch.setattr(Transaction, '_commit', commit)
    assert close(client) == terminal.COMMITTED_REVISION_UNKNOWN
    assert client.rows[PATH]['no_speech_terminal']['run_id'] == 'run-1'
    assert client.rows[PATH]['discarded'] is True
    assert client.deletes == []


def test_restore_keeps_owner_row_recoverable_after_privacy_opt_out(client):
    before = dict(client.rows[PATH])
    committed = close(client)
    client.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    terminal.restore_no_speech(UID, CID, expected_closed_revision=committed, run_id='run-1', firestore_client=client)
    assert client.rows[PATH] == before
    assert is_visible_conversation(client.rows[PATH]) is True
    assert client.deletes == []


@pytest.mark.parametrize('generation,expected', [(None, 0), (7, 7), (9, None)])
def test_close_optional_privacy_generation_accepts_matching_or_direct_call(client, generation, expected):
    if generation is not None:
        client.rows[PRIVACY_PATH] = {'generation': generation}
        client.revisions[PRIVACY_PATH] = NOW
    close(client, expected_privacy_generation=expected)
    assert client.rows[PATH]['no_speech_terminal']['run_id'] == 'run-1'


def test_close_refuses_changed_privacy_generation_without_write(client):
    client.rows[PRIVACY_PATH] = {'generation': 9}
    client.revisions[PRIVACY_PATH] = NOW
    before = dict(client.rows[PATH])
    with pytest.raises(terminal.NoSpeechConflict, match='^privacy_changed$'):
        close(client, expected_privacy_generation=7)
    assert client.rows[PATH] == before
    assert all(not txn.has_written for txn in client.transactions)
    assert client.deletes == []
