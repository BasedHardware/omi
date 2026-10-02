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
    from utils.sync import pipeline

    return pipeline


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
    ('audio_start_seconds', 'audio_end_seconds'), [(994.99, 1008.0), (1001.0, 1069.51), (1008.0, 1008.0)]
)
def test_audio_outside_or_spanning_live_generation_stays_unbound(audio_start_seconds, audio_end_seconds):
    assert select([live_row()], audio_start_seconds=audio_start_seconds, audio_end_seconds=audio_end_seconds) is None


@pytest.mark.parametrize(('audio_start_seconds', 'audio_end_seconds'), [(995.0, 1008.0), (1001.0, 1069.5)])
def test_bounded_skew_and_trailing_silence_bind(audio_start_seconds, audio_end_seconds):
    assert select([live_row()], audio_start_seconds=audio_start_seconds, audio_end_seconds=audio_end_seconds) == 'live'


def test_adjacent_conversations_made_ambiguous_by_allowance_stay_unbound():
    first = live_row()
    second = live_row(started_at=first['finished_at'])
    second['id'] = 'live-2'
    second['finished_at'] = second['started_at'] + (first['finished_at'] - first['started_at'])
    assert select([first, second], audio_start_seconds=1006.0, audio_end_seconds=1012.0) is None


def test_trailing_allowance_does_not_bind_an_interval_without_overlap():
    assert select([live_row()], audio_start_seconds=1040.0, audio_end_seconds=1050.0) is None


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


def test_recording_session_lookup_failure_stays_unbound(caplog, monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'unit-test-secret')

    class Unavailable:
        def collection(self, name):
            raise RuntimeError('firestore down')

    assert (
        resolve_recording_session_sync_target(
            'private-account-id', SESSION, 'omi', 'pendant', False, 1001.0, 1008.0, firestore_client=Unavailable()
        )
        is None
    )
    assert 'uid_hash=' in caplog.text
    assert 'private-account-id' not in caplog.text


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
        self.query_limit = count
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('stamped_target', 'candidate_id', 'expected_target'),
    [
        ('live', 'live', 'live'),
        ('previous-generation', 'live', 'live'),
        ('previous-generation', None, None),
        (None, None, None),
    ],
)
async def test_pipeline_uses_unique_recording_match_over_local_stamp(
    monkeypatch, dependencies, stamped_target, candidate_id, expected_target
):
    from utils.sync import recording_session_target

    pipeline = dependencies

    async def run_inline(_executor, fn, *args):
        return fn(*args)

    rows = [live_row()] if candidate_id else []
    monkeypatch.setattr(recording_session_target, '_candidate_rows', lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(pipeline, 'run_blocking', run_inline)
    assert (
        await pipeline._resolve_safety_wal_target(
            'u', stamped_target, SESSION, pipeline.ConversationSource.omi, 'pendant', False, 1001.0, 1008.0
        )
        == expected_target
    )


@pytest.mark.asyncio
async def test_pipeline_keeps_legacy_stamp_without_recording_proof(dependencies):
    pipeline = dependencies
    assert (
        await pipeline._resolve_safety_wal_target(
            'u', 'legacy-target', None, pipeline.ConversationSource.omi, 'pendant', False, None, None
        )
        == 'legacy-target'
    )


def test_truncated_candidate_query_cannot_establish_uniqueness():
    rows = [live_row()]
    rows += [live_row(client_device_id=f'other-{i}') for i in range(5)]
    client = _Docs([_Doc(row) for row in rows])
    assert (
        resolve_recording_session_sync_target(
            'u', SESSION, 'omi', 'pendant', False, 1001.0, 1008.0, firestore_client=client
        )
        is None
    )
    assert client.query_limit == 6


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


def test_live_bound_mixed_wal_drops_one_near_exact_repeat_and_keeps_new_speech():
    store = StrictFirestore()
    original = live_row()
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(original)
    incoming = chunk('wal', 1001, text=TEXT)
    incoming['finished_at'] = incoming['started_at'] + (original['finished_at'] - original['started_at']) * 2
    incoming['transcript_segments'].append(
        {'start': 10.0, 'end': 19.5, 'text': 'A new discussion after the repeated line.', 'speaker_id': 0}
    )
    result, created, survivors = intake(store, incoming, target_id=select([original]))
    assert not created
    assert len(survivors) == 1
    assert len(result['transcript_segments']) == 2
    assert [segment['text'] for segment in result['transcript_segments']] == [
        TEXT,
        'A new discussion after the repeated line.',
    ]


def test_live_bound_mixed_wal_keeps_single_match_with_loose_time_alignment():
    store = StrictFirestore()
    original = live_row()
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(original)
    incoming = chunk('wal', 1004, text=TEXT)
    incoming['finished_at'] = incoming['started_at'] + (original['finished_at'] - original['started_at']) * 2
    incoming['transcript_segments'].append(
        {'start': 10.0, 'end': 19.5, 'text': 'A new discussion after the repeated line.', 'speaker_id': 0}
    )
    _, _, survivors = intake(store, incoming, target_id=select([original]))
    assert len(survivors) == 2


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
