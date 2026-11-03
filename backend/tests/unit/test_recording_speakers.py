"""Recording naming uses real receipt transactions and synthetic transcripts."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from database import conversations as db, recording_speakers as decisions_db
from models.recording_speakers import RecordingSelection, RecordingSpeakerRequest
from routers.recording_speakers import edit
from tests.unit.test_manual_speaker_assignments import world
from utils import recording_speakers as service
from utils.manual_speaker_assignments import apply_manual_assignments


def decode(store, cid):
    raw = deepcopy(store.rows[('users', 'u', 'conversations', cid)])
    raw['transcript_segments'] = db.decode_transcript_segments_verified(
        'u', raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
    )
    raw['manual_speaker_assignments'] = db.decode_manual_speaker_assignments(
        'u', raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    return raw


@pytest.fixture
def recording(world, monkeypatch):
    store, _, segments = world
    for n in range(3):
        cid = f'c{n}'
        store.rows[('users', 'u', 'conversations', cid)] = dict(
            id=cid,
            status='completed',
            transcript_segments=[
                dict(segments[1], id=f'{cid}-s', speaker_id_scope='stream:1', speaker='SPEAKER_0', speaker_id=4),
                dict(segments[1], id=f'{cid}-other', speaker_id_scope='stream:2', speaker='SPEAKER_0', speaker_id=5),
            ],
        )
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: decode(store, cid))
    episode = {'id': 'e', 'conversation_ids': ['c0', 'c1', 'c2']}
    monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *a: episode)
    monkeypatch.setattr(service.episodes_db, 'get_episode', lambda *a: episode)
    monkeypatch.setattr(decisions_db, 'get_firestore_client', lambda: store)
    return store


def request(*, whole=True, selections=None):
    return RecordingSpeakerRequest(
        person_id='new',
        whole_recording=whole,
        use_for_speech_training=False,
        selections=selections or [RecordingSelection(conversation_id='c1', segment_ids=['c1-s'], speaker_id=4)],
    )


def test_middle_member_rename_reaches_earlier_later_and_replays(recording):
    result = edit('u', 'c1', request(), None, episode_id='e')
    assert result['applied_count'] == 3
    assert {r['conversation_id'] for r in result['conversations']} == {'c0', 'c1', 'c2'}
    for cid in ['c0', 'c1', 'c2']:
        row = decode(recording, cid)
        assert row['transcript_segments'][0]['person_id'] == 'new'
        assert row['transcript_segments'][1]['person_id'] == 'old'
        assert row['manual_speaker_assignments']['segments'][f'{cid}-s']['person_id'] == 'new'
        stale = deepcopy(row['transcript_segments'])
        stale[0]['person_id'] = None
        assert apply_manual_assignments(stale, row['manual_speaker_assignments'])[0]['person_id'] == 'new'


def test_late_rename_preseeds_next_rollover_even_if_previous_has_no_voice(recording):
    edit('u', 'c1', request(), None)
    previous = dict(decode(recording, 'c2'), transcript_segments=[])
    receipt = service.recording_carry('u', previous, 'stream:1')
    assert receipt['speakers']['4']['person_id'] == 'new'
    assert service.recording_carry('u', previous, 'different-scope') == {}


def test_multiselect_two_members_is_one_request_and_only_selected_lines(recording):
    body = request(
        whole=False,
        selections=[
            RecordingSelection(conversation_id='c0', segment_ids=['c0-s']),
            RecordingSelection(conversation_id='c2', segment_ids=['c2-other']),
        ],
    )
    assert edit('u', 'c0', body, None)['applied_count'] == 2
    assert decode(recording, 'c1')['transcript_segments'][0]['person_id'] == 'old'


def test_stale_speaker_is_typed_409_without_partial_writes(recording):
    before = deepcopy(recording.rows)
    body = request(
        selections=[RecordingSelection(conversation_id='c1', segment_ids=['c1-s', 'c1-other'], speaker_id=4)]
    )
    with pytest.raises(Exception) as error:
        edit('u', 'c1', body, None)
    assert error.value.status_code == 409
    assert error.value.detail['code'] == 'stale_speaker'
    assert recording.rows == before


def test_unscoped_rows_only_change_the_source_member(recording):
    for cid in ['c0', 'c1', 'c2']:
        recording.rows[('users', 'u', 'conversations', cid)]['transcript_segments'][0].pop('speaker_id_scope')
    assert edit('u', 'c1', request(), None)['applied_count'] == 1


def test_non_episode_scope_fallback_includes_same_scope_only(recording, monkeypatch):
    monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *a: None)
    snapshots = [
        SimpleNamespace(id=cid, to_dict=lambda cid=cid: recording.rows[('users', 'u', 'conversations', cid)])
        for cid in ['c0', 'c1', 'c2']
    ]
    snapshots.append(SimpleNamespace(id='empty', to_dict=lambda: {'transcript_segments': None}))
    collection = SimpleNamespace(stream=lambda: iter(snapshots))
    collection.select = lambda fields: collection
    client = SimpleNamespace(
        collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: collection))
    )
    monkeypatch.setattr(
        service,
        'scope_conversation_ids',
        lambda uid, scopes: decisions_db.scope_conversation_ids(uid, scopes, firestore_client=client),
    )
    assert edit('u', 'c1', request(), None)['applied_count'] == 3


def test_real_http_route_renames_and_reports_member_counts(recording):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import recording_speakers as routes

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.patch('/v1/conversations/c1/recording-speakers', json=request().model_dump())
    assert response.status_code == 200
    assert response.json()['applied_count'] == 3
    assert len(response.json()['conversations']) == 3


def test_voice_request_and_latest_decision_win_on_next_rollover(recording):
    from models.recording_speakers import RecordingVoice

    body = RecordingSpeakerRequest(
        is_user=True,
        use_for_speech_training=False,
        voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_00'),
    )
    assert edit('u', 'c1', body, None)['applied_count'] == 3
    assert service.recording_carry('u', decode(recording, 'c2'), 'stream:1')['speakers']['4']['is_user']
    edit('u', 'c1', request(), None)
    receipt = service.recording_carry('u', dict(decode(recording, 'c0'), transcript_segments=[]), 'stream:1')
    assert receipt['speakers']['4']['person_id'] == 'new'


def test_whole_recording_receipt_labels_later_lines_only_on_the_same_voice(recording):
    edit('u', 'c1', request(), None)
    row = decode(recording, 'c1')
    later = dict(row['transcript_segments'][0], id='later', person_id=None)
    different = dict(later, id='reconnected', speaker_id_scope='another-stream')
    applied = apply_manual_assignments([later, different], row['manual_speaker_assignments'])
    assert applied[0]['person_id'] == 'new'
    assert applied[1]['person_id'] is None


def test_live_receipt_lookup_cannot_join_a_different_scope(recording):
    from utils.manual_speaker_assignments import manual_voice_decision

    edit('u', 'c1', request(), None)
    receipt = decode(recording, 'c1')['manual_speaker_assignments']
    assert manual_voice_decision(receipt, 4, 'stream:1')['person_id'] == 'new'
    assert manual_voice_decision(receipt, 4, 'different-stream') is None


def test_recording_transcript_is_ordered_at_recorded_offsets(recording):
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for n in range(3):
        recording.rows[('users', 'u', 'conversations', f'c{n}')]['started_at'] = start + timedelta(minutes=n)
    service.episodes_db.get_episode_for_conversation('u', 'c1')['conversation_ids'].reverse()
    rows = service.transcript('u', 'c1')['conversations']
    assert [row['id'] for row in rows] == ['c0', 'c1', 'c2']
    assert [row['recording_offset_seconds'] for row in rows] == [0, 60, 120]


def test_client_voice_proof_rejects_scope_reuse_before_any_write(recording):
    from models.recording_speakers import RecordingVoice

    before = deepcopy(recording.rows)
    body = request(
        selections=[
            RecordingSelection(
                conversation_id='c1',
                segment_ids=['c1-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stale-stream', stream_speaker='SPEAKER_0'),
            )
        ]
    )
    with pytest.raises(Exception) as error:
        edit('u', 'c1', body, None)
    assert error.value.status_code == 409
    assert error.value.detail['code'] == 'stale_speaker'
    assert recording.rows == before


def test_sync_merge_redirect_keeps_recording_rename_available(recording):
    recording.rows[('users', 'u', 'conversations', 'donor')] = dict(
        id='donor', deleted=True, sync_merged_into='c1', transcript_segments=[]
    )
    body = request(selections=[RecordingSelection(conversation_id='donor', segment_ids=['c1-s'], speaker_id=4)])
    assert edit('u', 'donor', body, None)['applied_count'] == 3


def test_episode_http_route_uses_episode_admission_and_fans_out(recording, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import episodes as routes

    episode = service.episodes_db.get_episode('u', 'e')
    admitted = []
    monkeypatch.setattr(routes, '_admitted', lambda uid, channel: admitted.append((uid, channel)) or True)
    monkeypatch.setattr(routes.service, 'episode_by_id', lambda *args: episode)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.patch(
            '/v1/episodes/e/assign-speaker', json=request().model_dump(), headers={routes.APP_CHANNEL_HEADER: 'beta'}
        )
        assert response.status_code == 200
        assert response.json()['applied_count'] == 3
        assert admitted == [('u', 'beta')]
        assert decode(recording, 'c0')['transcript_segments'][0]['person_id'] == 'new'
        assert decode(recording, 'c2')['transcript_segments'][0]['person_id'] == 'new'
        before = deepcopy(recording.rows)
        monkeypatch.setattr(routes, '_admitted', lambda *args: False)
        denied = client.patch('/v1/episodes/e/assign-speaker', json=request().model_dump())
        assert denied.status_code == 404
        assert recording.rows == before
