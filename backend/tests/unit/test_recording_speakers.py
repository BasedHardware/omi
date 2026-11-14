"""Recording naming uses real receipt transactions and synthetic transcripts."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from database import conversations as db, recording_speakers as decisions_db
from models.recording_speakers import RecordingSelection, RecordingSpeakerRequest, RecordingVoice
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
            recording_speaker_scopes=['stream:1', 'stream:2'],
            recording_speaker_scopes_at_creation=True,
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


def request(*, whole=True, selections=None, proof=True):
    return RecordingSpeakerRequest(
        person_id='new',
        whole_recording=whole,
        use_for_speech_training=False,
        selections=selections
        or [
            RecordingSelection(
                conversation_id='c1',
                segment_ids=['c1-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0') if proof else None,
            )
        ],
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
    assert edit('u', 'c1', request(proof=False), None)['applied_count'] == 1


@pytest.mark.parametrize('whole', [True, False])
def test_legacy_unstored_ids_remain_stable_and_editable(recording, whole):
    from models.transcript_segment import legacy_conversation_segment_id

    line = recording.rows[('users', 'u', 'conversations', 'c1')]['transcript_segments'][0]
    for key in ['id', 'speaker_id', 'speaker_id_scope']:
        line.pop(key)
    expected_id = legacy_conversation_segment_id('c1', 0)
    for _ in range(2):
        rows = service.transcript('u', 'c1')['conversations']
        projected = next(row for row in rows if row['id'] == 'c1')['transcript_segments'][0]
        assert projected['id'] == expected_id
        assert projected['speaker_id'] == 0
    body = request(
        whole=whole,
        selections=[
            RecordingSelection(conversation_id='c1', segment_ids=[expected_id], speaker_id=0 if whole else None)
        ],
    )
    assert edit('u', 'c1', body, None)['applied_count'] == 1
    row = decode(recording, 'c1')
    assert row['transcript_segments'][0]['person_id'] == 'new'
    assert row['manual_speaker_assignments']['segments'][expected_id]['person_id'] == 'new'
    assert decode(recording, 'c0')['transcript_segments'][0]['person_id'] == 'old'


def test_non_episode_scope_fallback_includes_same_scope_only(recording, monkeypatch):
    monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *a: None)
    snapshots = [
        SimpleNamespace(id=cid, to_dict=lambda cid=cid: recording.rows[('users', 'u', 'conversations', cid)])
        for cid in ['c0', 'c1', 'c2']
    ]
    # An indexed array query cannot return rows without the scope field.
    collection = SimpleNamespace(stream=lambda: iter(snapshots))
    collection.select = lambda fields: collection
    collection.where = lambda **kwargs: collection
    collection.limit = lambda count: collection
    client = SimpleNamespace(
        collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: collection))
    )
    monkeypatch.setattr(
        service,
        'scope_conversation_ids',
        lambda uid, scopes: decisions_db.scope_conversation_ids(uid, scopes, firestore_client=client),
    )
    result = edit('u', 'c1', request(), None)
    assert result['applied_count'] == 3
    assert result['coverage'] == 'complete'


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


def test_recording_transcript_response_models_and_preserves_voice_proof(recording):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import recording_speakers as routes

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    path = '/v1/conversations/{conversation_id}/recording-speakers'
    schema = app.openapi()['paths'][path]['get']['responses']['200']['content']['application/json']['schema']
    assert schema == {'$ref': '#/components/schemas/RecordingTranscriptResponse'}
    with TestClient(app) as client:
        response = client.get('/v1/conversations/c1/recording-speakers')
    assert response.status_code == 200
    line = response.json()['conversations'][0]['transcript_segments'][0]
    assert (line['speaker_id_scope'], line['stream_speaker']) == ('stream:1', 'SPEAKER_0')


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
        id='donor', deleted=True, discarded=True, sync_merged_into='c1', transcript_segments=[]
    )
    body = request(
        selections=[
            RecordingSelection(
                conversation_id='donor',
                segment_ids=['c1-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0'),
            )
        ]
    )
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


def test_live_identity_proof_rejects_reconnected_same_number(recording):
    from models.recording_speakers import RecordingVoice

    line = recording.rows[('users', 'u', 'conversations', 'c1')]['transcript_segments'][1]
    line['speaker_id'] = 4
    before = deepcopy(recording.rows)
    body = request(
        selections=[
            RecordingSelection(
                conversation_id='c1',
                segment_ids=['c1-s', 'c1-other'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0'),
            )
        ]
    )
    with pytest.raises(Exception) as error:
        edit('u', 'c1', body, None)
    assert error.value.status_code == 409
    assert recording.rows == before


@pytest.mark.parametrize('budget', ['members', 'segments'])
def test_over_cap_refuses_before_any_write(recording, monkeypatch, budget):
    from config import recording_speakers as limits

    monkeypatch.setattr(limits, 'MAX_MEMBERS' if budget == 'members' else 'MAX_SEGMENTS', 2)
    before = deepcopy(recording.rows)
    with pytest.raises(Exception) as error:
        edit('u', 'c1', request(), None)
    assert error.value.status_code == 413
    assert error.value.detail == 'recording_speaker_limit_exceeded'
    assert recording.rows == before


def test_scope_discovery_is_indexed_and_bounded():
    calls = []

    class Query:
        def where(self, *, filter):
            calls.append(('where', filter.field_path, filter.op_string, filter.value))
            return self

        def select(self, fields):
            calls.append(('select', fields))
            return self

        def limit(self, count):
            calls.append(('limit', count))
            return self

        def stream(self):
            assert calls[-1] == ('limit', 65)
            return iter([])

    client = SimpleNamespace(
        collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: Query()))
    )
    assert decisions_db.scope_conversation_ids('u', {'stream:1'}, firestore_client=client) == []
    assert calls[0] == ('where', 'recording_speaker_scopes', 'array_contains_any', ['stream:1'])


def test_scope_index_is_stamped_before_transcript_encryption(world):
    _, _, segments = world
    payload = db._prepare_conversation_for_write(
        {'transcript_segments': [dict(segments[0], speaker_id_scope='stream:1')]}, 'u', 'standard'
    )
    assert payload['recording_speaker_scopes'] == ['stream:1']
    assert isinstance(payload['transcript_segments'], bytes)
    assert (
        db.decode_transcript_segments_verified('u', payload['transcript_segments'], True)[0]['speaker_id_scope']
        == 'stream:1'
    )


def test_discarded_members_are_hidden_and_never_assigned(recording):
    recording.rows[('users', 'u', 'conversations', 'c0')]['discarded'] = True
    assert {row['id'] for row in service.transcript('u', 'c1')['conversations']} == {'c1', 'c2'}
    assert edit('u', 'c1', request(), None)['applied_count'] == 2
    assert decode(recording, 'c0')['transcript_segments'][0]['person_id'] == 'old'


def test_discard_race_is_rechecked_in_assignment_transaction(recording, monkeypatch):
    original = service.commit_manual_assignment

    def raced(uid, cid, **kwargs):
        recording.rows[('users', uid, 'conversations', cid)]['discarded'] = True
        return original(uid, cid, **kwargs)

    monkeypatch.setattr(service, 'commit_manual_assignment', raced)
    result = edit('u', 'c1', request(), None)
    assert result['applied_count'] == 0
    assert all(row['error'] == 'stale_speaker' for row in result['conversations'])
    assert all(decode(recording, cid)['transcript_segments'][0]['person_id'] == 'old' for cid in ['c0', 'c1', 'c2'])


def test_later_stale_member_returns_outcomes_for_already_committed_members(recording, monkeypatch):
    original = service.commit_manual_assignment

    def raced(uid, cid, **kwargs):
        if cid == 'c1':
            recording.rows[('users', uid, 'conversations', cid)]['transcript_segments'][0][
                'speaker_id_scope'
            ] = 'reconnect'
        return original(uid, cid, **kwargs)

    monkeypatch.setattr(service, 'commit_manual_assignment', raced)
    result = edit('u', 'c1', request(), None)
    assert result['applied_count'] == 2
    outcomes = {r['conversation_id']: r for r in result['conversations']}
    assert outcomes['c1']['error'] == 'stale_speaker'
    for cid in ['c0', 'c2']:
        assert 'error' not in outcomes[cid]
        assert decode(recording, cid)['transcript_segments'][0]['person_id'] == 'new'
    assert decode(recording, 'c1')['transcript_segments'][0]['person_id'] == 'old'


def test_retry_is_noop_for_receipt_generation_and_learning_jobs(recording):
    body = request().model_copy(update={'use_for_speech_training': True})
    first = edit('u', 'c1', body, None)
    assert first['applied_count'] == 3
    before = deepcopy(recording.rows)
    second = edit('u', 'c1', body, None)
    assert second['applied_count'] == 0
    assert recording.rows == before


def test_kill_switch_defaults_on_and_off_disables_fanout_and_carry(recording, monkeypatch):
    from config.recording_speakers import enabled

    monkeypatch.delenv('RECORDING_SPEAKER_RENAME_ENABLED', raising=False)
    assert enabled()
    edit('u', 'c1', request(), None)
    monkeypatch.setenv('RECORDING_SPEAKER_RENAME_ENABLED', 'off')
    assert not enabled()
    result = service.transcript('u', 'c1')
    assert result['enabled'] is False
    assert [row['id'] for row in result['conversations']] == ['c1']
    before = deepcopy(recording.rows)
    with pytest.raises(Exception) as error:
        edit('u', 'c1', request(), None)
    assert error.value.detail == 'recording_speaker_rename_disabled'
    assert recording.rows == before
    assert service.recording_carry('u', {'transcript_segments': []}, 'stream:1') == {}


@pytest.mark.parametrize('whole', [True, False])
def test_unscoped_recording_retry_is_also_noop(recording, whole):
    recording.rows[('users', 'u', 'conversations', 'c1')]['transcript_segments'][0].pop('speaker_id_scope')
    body = request(whole=whole, proof=False)
    assert edit('u', 'c1', body, None)['applied_count'] == 1
    before = deepcopy(recording.rows)
    assert edit('u', 'c1', body, None)['applied_count'] == 0
    assert recording.rows == before


def test_legacy_fallback_cannot_assign_a_discarded_conversation(recording):
    recording.rows[('users', 'u', 'conversations', 'c1')]['discarded'] = True
    before = deepcopy(recording.rows)
    with pytest.raises(ValueError):
        db.assign_conversation_speaker('u', 'c1', person_id='new', segment_ids=['c1-s'])
    assert recording.rows == before


def test_scoped_speaker_wide_request_requires_client_voice_proof(recording):
    before = deepcopy(recording.rows)
    with pytest.raises(Exception) as error:
        edit('u', 'c1', request(proof=False), None)
    assert error.value.status_code == 409
    assert recording.rows == before


def test_scope_budget_is_checked_before_voice_expansion(recording, monkeypatch):
    monkeypatch.setattr(service, 'MAX_SCOPES', 1)
    monkeypatch.setattr(service, 'voice_segments', lambda *a: pytest.fail('Voice expansion ran before the budget'))
    before = deepcopy(recording.rows)
    body = request(whole=False, selections=[RecordingSelection(conversation_id='c1', segment_ids=['c1-s', 'c1-other'])])
    with pytest.raises(Exception) as error:
        edit('u', 'c1', body, None)
    assert error.value.status_code == 413
    assert recording.rows == before


@pytest.fixture
def legacy_recording(recording, monkeypatch):
    """Real equality builders over unindexed metadata; never a collection scan."""
    monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *a: None)
    calls = []

    class Query:
        def __init__(self, field=None, value=None):
            self.field, self.value = field, value
            self.bound = None

        def where(self, *, filter):
            calls.append((filter.field_path, filter.op_string, filter.value))
            return Query(filter.field_path, filter.value)

        def select(self, fields):
            return self

        def limit(self, bound):
            self.bound = bound
            return self

        def stream(self):
            from config.recording_speakers import MAX_MEMBERS

            assert self.field and self.bound == MAX_MEMBERS + 1
            found = []
            for path, row in recording.rows.items():
                if len(path) != 4 or path[:3] != ('users', 'u', 'conversations'):
                    continue
                if self.field == 'recording_speaker_scopes':
                    matches = bool(set(row.get(self.field) or []) & set(self.value))
                else:
                    matches = (row.get('external_data') or {}).get(self.field.split('.')[-1]) == self.value
                if matches:
                    found.append(SimpleNamespace(id=path[-1], to_dict=lambda row=row: deepcopy(row)))
            return iter(found[: self.bound])

    client = SimpleNamespace(
        collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: Query()))
    )
    monkeypatch.setattr(
        service,
        'scope_conversation_ids',
        lambda uid, scopes: decisions_db.scope_conversation_ids(uid, scopes, firestore_client=client),
    )
    monkeypatch.setattr(
        service,
        'legacy_recording_conversation_ids',
        lambda uid, origin: decisions_db.legacy_recording_conversation_ids(uid, origin, firestore_client=client),
    )
    for n in range(3):
        row = recording.rows[('users', 'u', 'conversations', f'c{n}')]
        row.pop('recording_speaker_scopes', None)
        row.pop('recording_speaker_scopes_at_creation', None)
        row['external_data'] = (
            {'recording_session_id': 'origin'}
            if n == 0
            else {'recording_origin_id': 'origin', 'recording_session_id': f'generation-{n}'}
        )
    return recording, calls


@pytest.mark.parametrize('anchor', ['c0', 'c1', 'c2'])
def test_legacy_unindexed_siblings_use_origin_and_first_generation_session(legacy_recording, anchor):
    store, calls = legacy_recording
    transcript = service.transcript('u', anchor)
    assert {row['id'] for row in transcript['conversations']} == {'c0', 'c1', 'c2'}
    assert transcript['coverage'] == 'partial'
    assert not any(
        'recording_speaker_scopes' in store.rows[('users', 'u', 'conversations', cid)] for cid in ['c0', 'c1', 'c2']
    )
    body = request(
        selections=[
            RecordingSelection(
                conversation_id=anchor,
                segment_ids=[f'{anchor}-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0'),
            )
        ]
    )
    result = edit('u', anchor, body, None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 3
    for cid in ['c0', 'c1', 'c2']:
        assert decode(store, cid)['transcript_segments'][0]['person_id'] == 'new'
        assert store.rows[('users', 'u', 'conversations', cid)]['recording_speaker_scopes'] == ['stream:1', 'stream:2']
    assert ('external_data.recording_origin_id', '==', 'origin') in calls
    assert ('external_data.recording_session_id', '==', 'origin') in calls


@pytest.mark.parametrize('hidden', ['deleted', 'discarded', 'is_locked'])
def test_legacy_discovery_excludes_hidden_members(legacy_recording, hidden):
    store, _ = legacy_recording
    store.rows[('users', 'u', 'conversations', 'c2')][hidden] = True
    before = deepcopy(store.rows[('users', 'u', 'conversations', 'c2')])
    assert {row['id'] for row in service.transcript('u', 'c1')['conversations']} == {'c0', 'c1'}
    assert edit('u', 'c1', request(), None)['applied_count'] == 2
    assert store.rows[('users', 'u', 'conversations', 'c2')] == before


@pytest.mark.parametrize('identity', [None, 'generation-only'])
def test_unproven_legacy_coverage_reports_partial_and_stays_local(legacy_recording, identity):
    store, _ = legacy_recording
    for cid in ['c0', 'c1', 'c2']:
        row = store.rows[('users', 'u', 'conversations', cid)]
        row['external_data'] = {'recording_session_id': identity} if identity else {}
        row.pop('recording_speaker_scopes', None)
    assert service.transcript('u', 'c1')['coverage'] == 'partial'
    expected = {'c1'} if identity is None else {'c0', 'c1', 'c2'}
    assert {row['id'] for row in service.transcript('u', 'c1')['conversations']} == expected
    result = edit('u', 'c1', request(), None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == len(expected)
    for cid in ['c0', 'c2']:
        assert decode(store, cid)['transcript_segments'][0]['person_id'] == ('new' if cid in expected else 'old')


@pytest.mark.parametrize('budget', ['members', 'segments'])
def test_legacy_fallback_enforces_caps_before_any_write(legacy_recording, monkeypatch, budget):
    from config import recording_speakers as limits

    store, _ = legacy_recording
    monkeypatch.setattr(limits, 'MAX_MEMBERS' if budget == 'members' else 'MAX_SEGMENTS', 2)
    before = deepcopy(store.rows)
    with pytest.raises(Exception) as error:
        edit('u', 'c1', request(), None)
    assert error.value.status_code == 413
    assert store.rows == before


@pytest.mark.parametrize('creation_indexed', [False, True])
def test_retry_repairs_only_missing_scope_index_without_new_receipt_or_learning(recording, creation_indexed):
    if not creation_indexed:
        recording.rows[('users', 'u', 'conversations', 'c1')].pop('recording_speaker_scopes_at_creation')
    edit('u', 'c1', request(), None)
    row = recording.rows[('users', 'u', 'conversations', 'c1')]
    row.pop('recording_speaker_scopes')
    before = deepcopy(recording.rows)
    assert edit('u', 'c1', request(), None)['applied_count'] == 0
    before[('users', 'u', 'conversations', 'c1')]['recording_speaker_scopes'] = ['stream:1', 'stream:2']
    assert recording.rows == before


def test_recording_openapi_documents_limit_and_both_conflicts():
    from fastapi import FastAPI
    from routers.recording_speakers import router

    app = FastAPI()
    app.include_router(router)
    spec = app.openapi()
    path = spec['paths']['/v1/conversations/{conversation_id}/recording-speakers']
    assert '413' in path['get']['responses']
    assert '413' in path['patch']['responses']
    assert '409' in path['patch']['responses']
    conflict = spec['components']['schemas']['RecordingSpeakerConflict']['properties']['detail']['anyOf']
    assert {'type': 'string', 'const': 'recording_speaker_rename_disabled'} in conflict
    assert {'$ref': '#/components/schemas/RecordingStaleDetail'} in conflict


def test_partial_coverage_survives_http_response_models(legacy_recording):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import recording_speakers as routes

    store, _ = legacy_recording
    store.rows[('users', 'u', 'conversations', 'c1')]['external_data'] = {}
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        read = client.get('/v1/conversations/c1/recording-speakers')
        assert read.status_code == 200
        assert read.json()['coverage'] == 'partial'
        saved = client.patch('/v1/conversations/c1/recording-speakers', json=request().model_dump())
        assert saved.status_code == 200
        assert saved.json()['coverage'] == 'partial'
        assert saved.json()['applied_count'] == 1


def test_partially_stamped_legacy_lineage_cannot_claim_complete(legacy_recording):
    store, _ = legacy_recording
    # First generation and a stamped rollover are discoverable; the intermediate
    # rollover has neither an origin stamp nor the newly introduced scope index.
    store.rows[('users', 'u', 'conversations', 'c1')]['external_data'].pop('recording_origin_id')
    transcript = service.transcript('u', 'c0')
    assert {row['id'] for row in transcript['conversations']} == {'c0', 'c2'}
    assert transcript['coverage'] == 'partial'
    body = request(
        selections=[
            RecordingSelection(
                conversation_id='c0',
                segment_ids=['c0-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0'),
            )
        ]
    )
    result = edit('u', 'c0', body, None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 2
    assert {row['conversation_id'] for row in result['conversations']} == {'c0', 'c2'}
    assert decode(store, 'c1')['transcript_segments'][0]['person_id'] == 'old'


@pytest.mark.parametrize('membership', ['scope', 'episode'])
@pytest.mark.parametrize('excluded', ['is_locked', 'discarded', 'deleted', 'missing'])
def test_excluded_discovered_member_makes_coverage_partial(legacy_recording, monkeypatch, membership, excluded):
    store, _ = legacy_recording
    if membership == 'episode':
        monkeypatch.setattr(
            service.episodes_db,
            'get_episode_for_conversation',
            lambda *args: {'id': 'e', 'conversation_ids': ['c0', 'c1', 'c2']},
        )
    for cid in ['c0', 'c1', 'c2']:
        store.rows[('users', 'u', 'conversations', cid)]['recording_speaker_scopes'] = ['stream:1', 'stream:2']
        store.rows[('users', 'u', 'conversations', cid)]['recording_speaker_scopes_at_creation'] = True
    if excluded == 'missing':
        original = service.conversations_db.get_conversation
        monkeypatch.setattr(
            service.conversations_db, 'get_conversation', lambda uid, cid: None if cid == 'c2' else original(uid, cid)
        )
    else:
        store.rows[('users', 'u', 'conversations', 'c2')][excluded] = True
    before = deepcopy(store.rows[('users', 'u', 'conversations', 'c2')])
    transcript = service.transcript('u', 'c1')
    assert {row['id'] for row in transcript['conversations']} == {'c0', 'c1'}
    assert transcript['coverage'] == 'partial'
    result = edit('u', 'c1', request(), None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 2
    assert store.rows[('users', 'u', 'conversations', 'c2')] == before


def test_legacy_index_repairs_never_certify_creation_time_coverage(legacy_recording):
    store, _ = legacy_recording
    assert edit('u', 'c1', request(), None)['coverage'] == 'partial'
    # Even repairing every known member cannot prove there is no invisible
    # intermediate generation. The same-value retry creates no new learning.
    before = deepcopy(store.rows)
    assert service.transcript('u', 'c1')['coverage'] == 'partial'
    result = edit('u', 'c1', request(), None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 0
    assert store.rows == before


def test_c0_c2_repaired_indexes_cannot_hide_an_invisible_c1(legacy_recording):
    store, _ = legacy_recording
    for cid in ['c0', 'c2']:
        row = store.rows[('users', 'u', 'conversations', cid)]
        row['recording_speaker_scopes'] = ['stream:1', 'stream:2']
    intermediate = store.rows[('users', 'u', 'conversations', 'c1')]
    intermediate['external_data'].pop('recording_origin_id')
    before = deepcopy(intermediate)
    body = request(
        selections=[
            RecordingSelection(
                conversation_id='c0',
                segment_ids=['c0-s'],
                speaker_id=4,
                voice=RecordingVoice(speaker_id_scope='stream:1', stream_speaker='SPEAKER_0'),
            )
        ]
    )

    for expected_changes in [2, 0]:
        transcript = service.transcript('u', 'c0')
        assert {row['id'] for row in transcript['conversations']} == {'c0', 'c2'}
        assert transcript['coverage'] == 'partial'
        outcome = edit('u', 'c0', body, None)
        assert outcome['coverage'] == 'partial'
        assert outcome['applied_count'] == expected_changes
        assert {row['conversation_id'] for row in outcome['conversations']} == {'c0', 'c2'}
        assert store.rows[('users', 'u', 'conversations', 'c1')] == before
        for cid in ['c0', 'c2']:
            assert (
                store.rows[('users', 'u', 'conversations', cid)].get('recording_speaker_scopes_at_creation') is not True
            )


@pytest.mark.parametrize('membership', ['scope', 'episode'])
@pytest.mark.parametrize('marker', [None, False, 'true'])
def test_every_member_needs_true_creation_provenance(recording, monkeypatch, membership, marker):
    if membership == 'scope':
        monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *args: None)
        monkeypatch.setattr(service, 'scope_conversation_ids', lambda *args: ['c0', 'c1', 'c2'])
    row = recording.rows[('users', 'u', 'conversations', 'c2')]
    row['recording_speaker_scopes_at_creation'] = marker
    assert service.transcript('u', 'c1')['coverage'] == 'partial'
    assert edit('u', 'c1', request(), None)['coverage'] == 'partial'
    assert recording.rows[('users', 'u', 'conversations', 'c2')].get('recording_speaker_scopes_at_creation') == marker


@pytest.mark.parametrize('membership', ['scope', 'episode'])
def test_creation_indexed_members_can_report_complete(recording, monkeypatch, membership):
    if membership == 'scope':
        monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *args: None)
        monkeypatch.setattr(service, 'scope_conversation_ids', lambda *args: ['c0', 'c1', 'c2'])
    assert service.transcript('u', 'c1')['coverage'] == 'complete'
    assert edit('u', 'c1', request(), None)['coverage'] == 'complete'
    assert edit('u', 'c1', request(), None)['coverage'] == 'complete'
    for cid in ['c0', 'c1', 'c2']:
        assert recording.rows[('users', 'u', 'conversations', cid)]['recording_speaker_scopes_at_creation'] is True


@pytest.mark.parametrize('raced', ['is_locked', 'discarded', 'deleted'])
def test_assignment_race_downgrades_complete_discovery(recording, monkeypatch, raced):
    original = service.commit_manual_assignment

    def commit(uid, cid, **kwargs):
        if cid == 'c2':
            recording.rows[('users', uid, 'conversations', cid)][raced] = True
        return original(uid, cid, **kwargs)

    monkeypatch.setattr(service, 'commit_manual_assignment', commit)
    assert service.transcript('u', 'c1')['coverage'] == 'complete'
    result = edit('u', 'c1', request(), None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 2


def test_skipping_member_without_selected_voice_is_partial(recording):
    recording.rows[('users', 'u', 'conversations', 'c2')]['transcript_segments'][0]['speaker_id_scope'] = 'other'
    result = edit('u', 'c1', request(), None)
    assert result['applied_count'] == 2
    assert result['coverage'] == 'partial'


@pytest.mark.parametrize('field', ['discarded_conversation_ids', 'duplicate_conversation_ids'])
def test_episode_exclusion_markers_are_retained_as_partial_evidence(recording, monkeypatch, field):
    episode = {'id': 'e', 'conversation_ids': ['c0', 'c1'], field: ['c2']}
    monkeypatch.setattr(service.episodes_db, 'get_episode_for_conversation', lambda *args: episode)
    before = deepcopy(recording.rows[('users', 'u', 'conversations', 'c2')])
    assert service.transcript('u', 'c1')['coverage'] == 'partial'
    result = edit('u', 'c1', request(), None)
    assert result['coverage'] == 'partial'
    assert result['applied_count'] == 2
    assert recording.rows[('users', 'u', 'conversations', 'c2')] == before
