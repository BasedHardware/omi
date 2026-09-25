"""Exercise the manual owner through real transactions with synthetic storage."""

from copy import deepcopy
import json
import os

import pytest

from routers.listen import receiver, transcripts
from database import conversations as db
from utils.manual_speaker_assignments import acknowledged_teaching, apply_manual_assignments, teaching_segment_ids
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


def _flush_processor(host):
    from types import SimpleNamespace
    from routers.listen.transcripts import TranscriptProcessor

    host.limits = SimpleNamespace(max_segment_buffer_size=8, max_photo_buffer_size=8)
    host.translation_language = None
    return TranscriptProcessor(host)


@pytest.fixture
def world(monkeypatch):
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'c')
    segments = [
        dict(
            id=f's{i}',
            speaker='SPEAKER_00',
            speaker_id=4,
            text='Synthetic speech',
            start=i,
            end=i + 1,
            is_user=i == 0,
            person_id=None if i == 0 else 'old',
        )
        for i in range(2)
    ]
    store.rows[path] = dict(
        id='c', status='in_progress', transcript_segments=segments, client_processing={'structure': {'title': 'old'}}
    )
    store.rows[('users', 'u', 'people', 'old')] = dict(
        speech_samples=['sample'],
        speaker_embedding=[1, 0],
        speech_sample_source=dict(conversation_id='c', segment_ids=['s1']),
    )
    store.rows[('users', 'u', 'people', 'new')] = dict(name='New')
    # Keep codec real; decode the returned persisted payload in assertions.
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    return store, path, segments


def read(world):
    store, path, _ = world
    raw = deepcopy(store.rows[path])
    raw['transcript_segments'] = db._decode_transcript_segments_strict(
        'u', raw['transcript_segments'], raw.get('transcript_segments_compressed', False)
    )
    raw['manual_speaker_assignments'] = db.decode_manual_speaker_assignments(
        'u', raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    return raw


def test_selected_edit_survives_stale_snapshot_and_preserves_append(world):
    store, path, stale = world
    appended = dict(stale[1], id='later', start=2, end=3)
    store.rows[path]['transcript_segments'].append(appended)
    raw, ids, removed, before = db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    assert ids == ['s1'] and removed == ['sample']
    assert len(raw['transcript_segments']) == 3
    assert raw['manual_speaker_assignments']['segments']['s1']['person_id'] == 'new'
    assert 'origin' not in raw['manual_speaker_assignments']['segments']['s1']
    assert raw['manual_speaker_assignments']['generation'] == 1
    assert acknowledged_teaching(raw, 'new', ['s1'])
    assert not acknowledged_teaching(raw, 'new', ['s0'])
    db.update_conversation_segments('u', 'c', stale[:2], preserve_unseen=True)
    saved = read(world)
    assert [s['id'] for s in saved['transcript_segments']] == ['s0', 's1', 'later']
    assert saved['transcript_segments'][1]['person_id'] == 'new'
    assert saved['transcript_segments'][0]['is_user'] is True
    assert store.rows[('users', 'u', 'people', 'old')]['speaker_embedding'] is None
    assert store.rows[path]['client_processing'] is db.firestore.DELETE_FIELD


def test_whole_speaker_default_and_newer_selected_override(world):
    raw, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', speaker_id=4)
    assert all(s['person_id'] == 'new' and not s['is_user'] for s in raw['transcript_segments'])
    assert not raw['manual_speaker_assignments'].get('segments')
    assert raw['manual_speaker_assignments']['speakers']['4']['person_id'] == 'new'
    assert acknowledged_teaching(raw, 'new', ['s0', 's1'])
    db.assign_conversation_speaker('u', 'c', is_user=True, segment_ids=['s0'])
    added = dict(world[2][0], id='future')
    db.update_conversation_segments('u', 'c', [*world[2], added])
    saved = read(world)
    assert saved['transcript_segments'][0]['is_user'] is True
    assert saved['transcript_segments'][1]['person_id'] == 'new'
    assert saved['transcript_segments'][2]['person_id'] == 'new'
    assert saved['manual_speaker_assignments']['generation'] == 2
    assert saved['manual_speaker_assignments']['segments']['s0']['is_user'] is True
    assert not acknowledged_teaching(saved, 'new', ['s0'])


@pytest.mark.parametrize(
    'selector,error',
    [
        ({'segment_index': -1}, LookupError),
        ({'segment_ids': ['s0', 'missing']}, ValueError),
        ({'segment_ids': ['#index:0']}, ValueError),
        ({'speaker_id': 9}, LookupError),
    ],
)
def test_invalid_selection_is_atomic(world, selector, error):
    before = deepcopy(world[0].rows)
    with pytest.raises(error):
        db.assign_conversation_speaker('u', 'c', person_id='new', **selector)
    assert world[0].rows == before


def test_legacy_completed_index_and_missing_person(world):
    world[0].rows[world[1]]['status'] = 'completed'
    world[0].rows[world[1]]['transcript_segments'][0].pop('id')
    raw, ids, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['#index:0'])
    assert ids[0] and raw['transcript_segments'][0]['person_id'] == 'new'
    with pytest.raises(LookupError):
        db.assign_conversation_speaker('u', 'c', person_id='foreign', segment_index=0)
    world[0].rows[world[1]]['deleted'] = True
    with pytest.raises(LookupError):
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_index=0)


def test_silent_flush_retries_dirty_write_and_publishes_acknowledged_identity(world):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from models.transcript_segment import TranscriptSegment
    from routers.listen import transcripts
    from unittest.mock import patch

    async def exercise():
        snapshot = dict(
            id='c',
            transcript_segments=[dict(segment, person_id=None) for segment in deepcopy(world[2])],
        )
        calls = []

        async def persist(fn, *args, **kwargs):
            calls.append(True)
            return False if len(calls) == 1 else args[2]

        processor = _flush_processor(
            SimpleNamespace(
                request=SimpleNamespace(uid='u'),
                state=SimpleNamespace(active=True, speaker_map_dirty=True),
                persistence=SimpleNamespace(call=persist),
                speakers=SimpleNamespace(
                    speaker_to_person={}, segment_assignments={'s1': 'new'}, segment_identity_status={}
                ),
            )
        )
        processor.cache = SimpleNamespace(
            get=AsyncMock(return_value=snapshot), protection_level='standard', update_segments=lambda segments: None
        )
        processor._deliver_segments = AsyncMock()
        with patch.object(
            transcripts,
            'deserialize_conversation',
            lambda data: SimpleNamespace(
                id='c', transcript_segments=[TranscriptSegment(**s) for s in data['transcript_segments']]
            ),
        ):
            await processor.flush_speaker_assignments('c')
            assert processor.host.state.speaker_map_dirty
            assert processor._flush_failures == 1
            assert processor._flush_backoff_until > 0
            processor._deliver_segments.assert_not_awaited()
            await processor.flush_speaker_assignments('c')
        assert not processor.host.state.speaker_map_dirty
        delivered = processor._deliver_segments.call_args.args[0]
        assert any(item['id'] == 's1' and item['person_id'] == 'new' for item in delivered)
        assert len(delivered) < len(snapshot['transcript_segments']) + 1

    asyncio.run(exercise())


def test_silence_flush_payload_is_proportional_to_changed_identities():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from models.transcript_segment import TranscriptSegment
    from routers.listen import transcripts

    async def exercise():
        segments = [
            dict(
                id=f's{i}',
                speaker='SPEAKER_00',
                speaker_id=0,
                text='Synthetic speech',
                start=i,
                end=i + 1,
                is_user=False,
                person_id=None,
            )
            for i in range(500)
        ]
        raw = dict(id='c', transcript_segments=segments)

        async def persist(fn, *args, **kwargs):
            return args[2]

        processor = _flush_processor(
            SimpleNamespace(
                request=SimpleNamespace(uid='u'),
                state=SimpleNamespace(active=True, speaker_map_dirty=True),
                persistence=SimpleNamespace(call=persist),
                speakers=SimpleNamespace(
                    speaker_to_person={}, segment_assignments={'s7': 'new'}, segment_identity_status={}
                ),
            )
        )
        processor.cache = SimpleNamespace(
            get=AsyncMock(return_value=raw), protection_level='standard', update_segments=lambda items: None
        )
        processor._deliver_segments = AsyncMock()
        with patch.object(
            transcripts,
            'deserialize_conversation',
            lambda data: SimpleNamespace(
                id='c', transcript_segments=[TranscriptSegment(**s) for s in data['transcript_segments']]
            ),
        ):
            await processor.flush_speaker_assignments('c')
        delivered = processor._deliver_segments.call_args.args[0]
        assert len(delivered) <= 2
        assert any(item['id'] == 's7' and item['person_id'] == 'new' for item in delivered)

    asyncio.run(exercise())


def test_socket_cannot_teach_without_persisted_manual_receipt(world):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from routers.listen.receiver import ListenReceiver

    async def exercise():
        receiver = object.__new__(ListenReceiver)
        sent = []

        async def spawn_task(coro, **kwargs):
            await coro

        tasks = []

        def spawn(coro, **kwargs):
            tasks.append(asyncio.create_task(coro))

        receiver.host = SimpleNamespace(
            state=SimpleNamespace(current_conversation_id='c', speaker_map_dirty=False),
            speakers=SimpleNamespace(segment_assignments={}),
            transcripts=SimpleNamespace(cache=SimpleNamespace(get=AsyncMock(return_value=read(world)))),
            private_cloud_sync_enabled=True,
            send_speaker_sample_request=AsyncMock(side_effect=lambda **kwargs: sent.append(kwargs)),
            spawn=spawn,
        )
        payload = dict(person_id='new', segment_ids=['s1'])
        await receiver._handle_speaker_assigned(payload)
        assert not tasks
        raw, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
        receiver.host.transcripts.cache.get.return_value = raw
        await receiver._handle_speaker_assigned(payload)
        await asyncio.gather(*tasks)
        assert sent == [dict(person_id='new', conv_id='c', segment_ids=['s1'])]
        assert receiver.host.state.speaker_map_dirty

    asyncio.run(exercise())


def test_legacy_wire_id_targets_the_same_stored_segment(world):
    from datetime import datetime, timezone
    from models.conversation import Conversation

    raw = world[0].rows[world[1]]
    raw['transcript_segments'][0].pop('id')
    wire = Conversation(
        id='c',
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        structured={},
        transcript_segments=raw['transcript_segments'],
    )
    target = wire.transcript_segments[0].id
    saved, ids, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=[target])
    assert ids == [target]
    assert saved['transcript_segments'][0]['id'] == target
    assert saved['transcript_segments'][0]['person_id'] == 'new'


def test_locked_conversation_and_all_selectors_invalidate_through_real_owner(world):
    store, path, _ = world
    store.rows[path]['is_locked'] = True
    with pytest.raises(PermissionError):
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['s1'])
    store.rows[path]['is_locked'] = False
    for kwargs in (
        dict(segment_index=0),
        dict(segment_ids=['s1']),
        dict(speaker_id=4),
    ):
        store.rows[path]['client_processing'] = {'structure': {'title': 'old'}}
        db.assign_conversation_speaker('u', 'c', person_id='new', **kwargs)
        assert store.rows[path]['client_processing'] is db.firestore.DELETE_FIELD


def test_apply_returns_input_when_receipt_has_no_decisions():
    segments = [{'id': 's0', 'person_id': None, 'speaker_id': 0}]
    assert apply_manual_assignments(segments, {}) is segments
    assert apply_manual_assignments(segments, {'generation': 1}) is segments


def test_apply_copies_only_segments_whose_identity_changes():
    labeled = {
        'id': 's0',
        'speaker_id': 0,
        'person_id': 'new',
        'is_user': False,
        'speaker_identity_status': 'not_user',
    }
    unlabeled = {'id': 's1', 'speaker_id': 0, 'person_id': None, 'is_user': False}
    receipt = {'speakers': {'0': {'generation': 1, 'person_id': 'new', 'is_user': False}}}
    result = apply_manual_assignments([labeled, unlabeled], receipt)
    assert result[0] is labeled
    assert result[1] is not unlabeled
    assert result[1]['person_id'] == 'new'


def test_whole_speaker_receipt_stays_constant_size_for_thousands_of_segments(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [
        dict(
            id=f's{i}',
            speaker='SPEAKER_00',
            speaker_id=4,
            text='Synthetic speech',
            start=i,
            end=i + 1,
            is_user=False,
            person_id=None,
        )
        for i in range(3000)
    ]
    raw, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', speaker_id=4)
    receipt = raw['manual_speaker_assignments']
    blob = json.dumps(receipt, separators=(',', ':'))
    assert len(blob) < 256
    assert not receipt.get('segments')
    assert receipt['speakers']['4']['person_id'] == 'new'
    stored = store.rows[path]['manual_speaker_assignments']
    stored_size = len(stored) if isinstance(stored, (bytes, str)) else len(json.dumps(stored))
    assert stored_size < 2048


def test_enhanced_receipt_has_no_plaintext_person_id(world):
    store, path, _ = world
    store.rows[path]['data_protection_level'] = 'enhanced'
    raw, *_ = db.assign_conversation_speaker('u', 'c', person_id='new', speaker_id=4)
    assert raw['manual_speaker_assignments']['speakers']['4']['person_id'] == 'new'
    stored = store.rows[path]['manual_speaker_assignments']
    assert isinstance(stored, str)
    assert 'new' not in stored
    assert 'person_id' not in stored
    decoded = read(world)
    assert decoded['manual_speaker_assignments']['speakers']['4']['person_id'] == 'new'
    assert acknowledged_teaching(decoded, 'new', ['s0', 's1'])


def test_speaker_wide_teaching_candidates_are_longest_first_and_bounded():
    durations = [1.0, 9.0, 3.0, 7.0, 2.0, 4.0]
    segments = [
        dict(
            id=f's{i}',
            speaker='SPEAKER_00',
            speaker_id=4,
            text='Synthetic speech',
            start=0,
            end=duration,
            is_user=False,
            person_id='new',
        )
        for i, duration in enumerate(durations)
    ]
    resolved = [segment['id'] for segment in segments]
    assert resolved == [f's{i}' for i in range(6)]
    assert teaching_segment_ids(segments, resolved) == ['s1', 's3', 's5']
