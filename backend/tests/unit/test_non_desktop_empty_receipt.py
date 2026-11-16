"""Non-desktop empty projections settle compose with the desktop assignment fences."""

from dataclasses import asdict
from datetime import timedelta
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from database import batch_pipeline_projection_session as sessions
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_episode_composer import T0, UID, _c, _row, store  # noqa: F401
from tests.unit.test_episode_compose_wait_repairs import clock  # noqa: F401
from utils.batch_pipeline import empty_transcription, projection
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.live_projection import replace_record
from utils.episodes import composer


def project_empty(monkeypatch, current, *, desktop=False, targeted=True, offset=0, fresh_outcome=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    binding = ProjectionBinding(
        'synthetic-owner',
        'job',
        'content',
        ('segment',),
        target_conversation_id=current['id'] if targeted else None,
        record_origin=desktop,
    )
    item = WorkItem(
        'segment',
        binding.owner_id,
        current['started_at'].timestamp() + offset,
        'gs://synthetic/audio',
        10,
        Priority.DEEP,
    )
    entry = {'result': {'outcome': 'silence'}}
    projector = projection.Projector(Mock(), Mock())
    projector.store = Mock()
    client = StrictFirestore()
    target = client.collection('users').document(binding.owner_id).collection('conversations').document(current['id'])
    target.create(current)
    real_store = ProjectionStore(Mock(client=client))
    session = real_store.session('segment', binding, 0, policy=ProjectionPolicy())

    def prepare(transaction, **_):
        if fresh_outcome is not None:
            session.entry = {'result': {'outcome': fresh_outcome}}

    session.prepare = Mock(side_effect=prepare)
    result_ref = client.collection('synthetic_results').document('segment')
    result_ref.create({'state': 'pending'})

    def persist(transaction, planned=None, **_):
        if transaction is not None:
            transaction.update(result_ref, {'state': 'persisted'})
        return {'state': 'persisted'}

    session.persist = Mock(side_effect=persist)
    session.entry = entry
    monkeypatch.setattr(sessions.firestore, 'transactional', lambda operation: operation)
    monkeypatch.setattr(real_store, 'run', lambda operation, **_: operation(client.transaction()))
    projector.store.session.return_value = session
    persist_empty = Mock(wraps=session.persist_empty)
    session.persist_empty = persist_empty
    assigned = []

    def assign(owner, incoming, **kwargs):
        # Exercise the actual silence assignment payload and replacement writer;
        # only the Firestore transport is substituted.
        assert kwargs['before_assign'] == session.prepare
        assert kwargs['validate_plan'] == session.validate_plan
        result, _ = replace_record(current, incoming, incoming['_batch_replace_live'])
        kwargs['after_assign'](None, result)
        assigned.append(result)

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', assign)
    projector._assign(
        'segment', {**asdict(item), 'policy_parts': {'projection': ProjectionPolicy().to_dict()}}, entry, binding
    )
    if not desktop and empty_transcription.FIELD in target.get().to_dict():
        assigned.append(target.get().to_dict())
    return assigned, session


def recording(now):
    row = _row('c1', T0, 1, title='', overview='', lines=[])
    row.update(
        record_lane_owner='batch_live_v1',
        record_projection_revision=1,
        server_batch_audio_closed=True,
        server_batch_audio_start=T0.timestamp(),
        server_batch_audio_end=T0.timestamp() + 10,
        home_transcription_pending_at=now,
    )
    return row


@pytest.mark.parametrize('desktop', [False, True])
def test_silence_receipt_settles_compose_on_first_attempt(monkeypatch, store, clock, desktop):
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'true')
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'true')
    row = recording(clock.current)
    assert composer._transcript_wait_until(row) > clock.current
    assigned, session = project_empty(monkeypatch, row, desktop=desktop)
    (result,) = assigned
    assert empty_transcription.terminal(result)
    assert session.persist_empty.call_count == (0 if desktop else 1)
    session.persist.assert_called_once()
    store.rows = {'c1': result}
    store.episode['conversation_ids'] = ['c1']
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'empty'
    assert all(not write.get('compose_transcript_wait_until') for write in store.writes)
    assert store.episode['composed_fingerprint']
    assert not store.episode.get('composed_at')

    # A later speech assignment increments the same revision and wins over
    # the preserved empty receipt; a renewed pending generation also fences it.
    incoming = {
        'id': 'c1',
        'started_at': T0,
        'transcript_segments': [
            {
                'id': 'synthetic-speech',
                'start': 0,
                'end': 5,
                'text': 'Synthetic speech.',
                'speaker': 'SPEAKER_01',
                'speaker_id': 0,
                'is_user': False,
            },
        ],
    }
    speech, new = replace_record(result, incoming, {'start': T0.timestamp(), 'end': T0.timestamp() + 10})
    assert new and speech['transcript_segments']
    assert not empty_transcription.terminal(speech)
    renewed = {**result, 'home_transcription_pending_at': clock.current + timedelta(seconds=1)}
    assert not empty_transcription.terminal(renewed)


@pytest.mark.parametrize('flag', ['EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'HOME_SETTLED_EMPTY_WIRE_ENABLED'])
@pytest.mark.parametrize('desktop', [False, True])
def test_either_switch_restores_result_only_path_without_changing_desktop(monkeypatch, clock, flag, desktop):
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'true')
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'true')
    monkeypatch.setenv(flag, 'false')
    assigned, session = project_empty(monkeypatch, recording(clock.current), desktop=desktop)
    assert bool(assigned) is desktop
    assert session.persist_empty.call_count == (0 if desktop else 1)


def test_non_record_silence_keeps_result_only_path(monkeypatch, clock):
    assigned, session = project_empty(monkeypatch, recording(clock.current), targeted=False)
    assert not assigned
    session.persist_empty.assert_called_once_with()


@pytest.mark.parametrize(
    'changes',
    [
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'status': 'processing'},
        {'sync_merged_into': 'synthetic-survivor'},
        {'transcript_segments': [{'text': 'Synthetic late speech.'}]},
    ],
)
def test_receipt_only_stamp_never_overwrites_speech_or_non_record_target(monkeypatch, clock, changes):
    current = recording(clock.current)
    current.update(changes)
    assigned, session = project_empty(monkeypatch, current)
    assert not assigned
    session.persist.assert_called_once()


def test_partial_silence_units_only_settle_after_covering_closed_audio(monkeypatch, clock):
    current = recording(clock.current)
    current['server_batch_audio_end'] += 10
    first, _ = project_empty(monkeypatch, current)
    assert not empty_transcription.terminal(first[0])
    second, _ = project_empty(monkeypatch, first[0], offset=10)
    assert empty_transcription.terminal(second[0])
    assert second[0][empty_transcription.FIELD]['spans'] == [
        {'start': T0.timestamp(), 'end': T0.timestamp() + 20},
    ]


def test_fresh_speech_result_cannot_receive_stale_empty_receipt(monkeypatch, clock):
    assigned, session = project_empty(monkeypatch, recording(clock.current), fresh_outcome='success')
    assert not assigned
    session.persist.assert_called_once()
