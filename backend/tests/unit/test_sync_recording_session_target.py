"""Unbound safety-WAL uploads attach to the live conversation of the same recording.

The selector is pure. Intake uses the existing explicit-target path, including
the live-target transcript slop, only when that selector returns one id.
"""

from copy import deepcopy

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
from utils.sync.recording_session_target import (
    resolve_recording_session_sync_target,
    select_recording_session_target,
)

SESSION = 'recording-live'
TEXT = 'A narrated explanation of this chapter.'


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations  # noqa: F401


def live_row(**extra):
    row = chunk('live', 1000, text=TEXT)
    row['status'] = 'in_progress'
    row['external_data'] = {'recording_session_id': SESSION}
    row.update(extra)
    return row


def select(rows, session_id=SESSION, **kwargs):
    return select_recording_session_target(
        rows,
        session_id,
        source=kwargs.get('source', 'omi'),
        client_device_id=kwargs.get('client_device_id', 'pendant'),
        is_locked=kwargs.get('is_locked', False),
        audio_start_seconds=kwargs.get('audio_start_seconds', 1001.0),
        audio_end_seconds=kwargs.get('audio_end_seconds', 1008.0),
    )


def test_one_compatible_live_conversation_is_the_explicit_target():
    assert select([live_row()]) == 'live'


@pytest.mark.parametrize(
    'mutation',
    [
        {'client_device_id': 'other-phone'},
        {'source': 'phone'},
        {'client_device_id': ''},
        {'is_locked': True},
        {'deleted': True},
        {'external_data': {'recording_session_id': 'other-recording'}},
        {'external_data': None},
    ],
)
def test_incompatible_recording_session_rows_stay_unbound(mutation):
    assert select([live_row(**mutation)]) is None


@pytest.mark.parametrize(
    ('audio_start_seconds', 'audio_end_seconds'), [(999.0, 1008.0), (1001.0, 1010.0), (1008.0, 1008.0)]
)
def test_audio_outside_or_spanning_live_generation_stays_unbound(audio_start_seconds, audio_end_seconds):
    assert select([live_row()], audio_start_seconds=audio_start_seconds, audio_end_seconds=audio_end_seconds) is None


def test_ambiguous_recording_session_matches_stay_unbound():
    second = live_row()
    second['id'] = 'live-2'
    assert select([live_row(), second]) is None


def test_missing_audio_interval_stays_unbound():
    assert (
        select_recording_session_target(
            [live_row()], SESSION, source='omi', client_device_id='pendant', is_locked=False
        )
        is None
    )


def test_blank_recording_session_id_does_not_query():
    class MustNotQuery:
        def collection(self, name):
            raise AssertionError(name)

    assert (
        resolve_recording_session_sync_target(
            'u', '   ', 'omi', 'pendant', False, 1001.0, 1008.0, firestore_client=MustNotQuery()
        )
        is None
    )


def test_recording_session_lookup_failure_stays_unbound():
    class Unavailable:
        def collection(self, name):
            raise RuntimeError('firestore down')

    assert (
        resolve_recording_session_sync_target(
            'u', SESSION, 'omi', 'pendant', False, 1001.0, 1008.0, firestore_client=Unavailable()
        )
        is None
    )


class _Docs:
    def __init__(self, rows):
        self.rows = rows
        self.uid = None

    def document(self, uid):
        self.uid = uid
        return self

    def collection(self, name):
        return self

    def where(self, **kwargs):
        return self

    def limit(self, count):
        return self

    def stream(self):
        return self.rows


class _Doc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


def test_resolve_returns_the_one_stored_match():
    client = _Docs([_Doc(live_row())])
    assert (
        resolve_recording_session_sync_target(
            'u', SESSION, 'omi', 'pendant', False, 1001.0, 1008.0, firestore_client=client
        )
        == 'live'
    )
    assert client.uid == 'u'


def test_matching_recording_session_dedupes_into_the_live_conversation():
    store = StrictFirestore()
    original = live_row()
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(original)
    target_id = select([original])
    incoming = chunk('wal', 1030, text=TEXT)
    result, created, survivors = intake(store, incoming, target_id=target_id)
    assert target_id == 'live'
    assert not created and not survivors
    assert result['id'] == 'live'
    assert len(result['transcript_segments']) == 1
    assert len(conversations(store)) == 1


def test_missing_recording_session_id_leaves_the_live_conversation_unchanged():
    store = StrictFirestore()
    original = live_row()
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(original)
    assert (
        select_recording_session_target([original], '', source='omi', client_device_id='pendant', is_locked=False)
        is None
    )
    result, created, _ = intake(store, chunk('wal', 1030, text=TEXT))
    assert created and result['id'] == 'wal'
    assert store.rows[('users', 'u', 'conversations', 'live')] == original
    assert {row['id'] for row in conversations(store)} == {'live', 'wal'}
