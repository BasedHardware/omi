import json
import time
import zlib
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from database import conversations as db
from database.read_boundary import MalformedDocError
from models.conversation import Conversation
from models.conversation_photo import ConversationPhoto
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreTransaction,
)
from tests.unit.test_audio_timeline_round3 import _processor, _seed_row, _v2_segment, UID, T0
from tests.unit.test_manual_speaker_assignments import read, world
from utils.stt.streaming import sort_segments_by_start

RECEIPT_COMMIT_LIMIT = 2
RECEIPT_BATCH_LIMIT = 128
RECEIPT_TOTAL_LIMIT = RECEIPT_COMMIT_LIMIT * RECEIPT_BATCH_LIMIT


def speech(
    sid: str, text: str, start: float, end: float, speaker_id: Any = 0, speaker: Any = None, **fields: Any
) -> dict:
    return dict(
        id=sid,
        text=text,
        start=start,
        end=end,
        speaker_id=speaker_id,
        speaker=speaker or f'SPEAKER_{speaker_id:02}',
        is_user=False,
        person_id=None,
        **fields,
    )


def replay_receipt_commits(row, uid):
    raw = row.get('live_transcript_replay_receipt')
    if raw is None:
        return None
    return db._reveal_json_value(raw, uid, True)['commits']


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('labeled', [False, True])
def test_committed_batch_replay_is_exactly_once(world, labeled, level):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    row['data_protection_level'] = level
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    fresh = [speech('b', 'have', 0.2, 0.4, **common), speech('c', 'to', 0.4, 0.6, **common)]
    assert 'live_transcript_replay_receipt' not in row
    first_merge = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    first = read(world)['transcript_segments']
    assert set(first_merge.absorbed_into) == {'b', 'c'}
    assert replay_receipt_commits(row, 'u') == [['b', 'c']]
    blob = row['live_transcript_replay_receipt']
    replayed_merge = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    replayed = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in replayed) == ' '.join(s['text'] for s in first) == 'I have to', replayed
    assert replayed == first
    assert replayed_merge.updated_ids == set()
    assert replayed_merge.removed_ids == []
    assert replayed_merge.absorbed_into == {}
    assert row['live_transcript_replay_receipt'] == blob
    assert replay_receipt_commits(row, 'u') == [['b', 'c']]
    prepared = db.prepare_conversation_for_read(row, 'u')
    assert prepared is not None
    assert 'live_transcript_replay_receipt' not in prepared
    assert 'live_transcript_replay_receipt' not in Conversation.model_fields
    wire = Conversation(
        id='c',
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        structured={},
        transcript_segments=prepared['transcript_segments'],
    )
    assert 'live_transcript_replay_receipt' not in wire.model_dump()
    assert 'live_transcript_replay_receipt' not in wire.model_dump_json()


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('labeled', [False, True])
@pytest.mark.asyncio
async def test_real_v2_retry_commit_with_lost_ack(monkeypatch, labeled, level):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = _seed_row(
        store,
        'conv-replay',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )
    row['audio_timeline'] = {'version': 2}
    row['data_protection_level'] = level
    processor, sent = _processor(monkeypatch, store, current='conv-replay')
    processor.host.state.capture_timeline_v2 = True
    if labeled:
        db.assign_conversation_speaker(UID, 'conv-replay', is_user=True, speaker_id=0)
    for field in db.PROJECTION_FAMILY_FIELDS:
        row.pop(field, None)
    raw = dict(_v2_segment('b', T0 + 0.2, T0 + 0.4, 'conv-replay', text='have'), **common)
    original_call = processor.host.persistence.call
    first = True

    async def lose_ack(fn, *args, **kwargs):
        nonlocal first
        accepted = await original_call(fn, *args, **kwargs)
        if fn is db.update_conversation_segments and first:
            first = False
            raise RuntimeError('ack lost after commit')
        return accepted

    processor.host.persistence.call = lose_ack
    with pytest.raises(RuntimeError, match='ack lost'):
        await processor._process_v2_batches([deepcopy(raw)], [], {})
    assert processor._v2_committed_ids == set()
    processor._queue_v2_retry([deepcopy(raw)])
    await processor._process_v2_batches(list(processor.segment_buffer), [], {})
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert ' '.join(s['text'] for s in stored) == 'I have', stored
    assert replay_receipt_commits(row, UID) == [['b']]
    sent.clear()
    raw_to = dict(_v2_segment('c', T0 + 0.4, T0 + 0.6, 'conv-replay', text='to'), **common)
    await processor._process_v2_batches([raw_to], [], {})
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert ' '.join(s['text'] for s in stored) == 'I have to', stored
    assert replay_receipt_commits(row, UID) == [['b'], ['c']]
    assert sent
    for payload in sent:
        assert 'live_transcript_replay_receipt' not in json.dumps(payload, default=str)
    prepared = db.prepare_conversation_for_read(row, UID)
    assert prepared is not None
    assert 'live_transcript_replay_receipt' not in prepared
    wire = Conversation(
        id=prepared['id'],
        created_at=prepared['created_at'],
        started_at=prepared['started_at'],
        finished_at=prepared['finished_at'],
        structured=prepared['structured'],
        transcript_segments=prepared['transcript_segments'],
    )
    assert 'live_transcript_replay_receipt' not in wire.model_dump()


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('labeled', [False, True])
@pytest.mark.asyncio
async def test_consecutive_v2_lost_acks_with_new_text_stay_once(monkeypatch, labeled, level):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = _seed_row(
        store,
        'conv-replay',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )
    row['audio_timeline'] = {'version': 2}
    row['data_protection_level'] = level
    processor, _sent = _processor(monkeypatch, store, current='conv-replay')
    processor.host.state.capture_timeline_v2 = True
    if labeled:
        db.assign_conversation_speaker(UID, 'conv-replay', is_user=True, speaker_id=0)
    for field in db.PROJECTION_FAMILY_FIELDS:
        row.pop(field, None)
    raws = {
        sid: dict(_v2_segment(sid, T0 + start, T0 + end, 'conv-replay', text=text), **common)
        for sid, text, start, end in [
            ('b', 'have', 0.2, 0.4),
            ('c', 'to', 0.4, 0.6),
            ('d', 'go', 0.6, 0.8),
        ]
    }
    original_call = processor.host.persistence.call
    lost = 0

    async def lose_ack(fn, *args, **kwargs):
        nonlocal lost
        accepted = await original_call(fn, *args, **kwargs)
        if fn is db.update_conversation_segments and lost < 2:
            lost += 1
            raise RuntimeError('ack lost after commit')
        return accepted

    processor.host.persistence.call = lose_ack

    async def drain():
        pending = sort_segments_by_start(list(processor.segment_buffer))
        processor.segment_buffer.clear()
        processor._v2_committed_ids.clear()
        await processor._process_v2_batches(pending, [], {})

    processor.segment_buffer.append(deepcopy(raws['b']))
    with pytest.raises(RuntimeError, match='ack lost'):
        await drain()
    assert processor._v2_committed_ids == set()
    first_blob = row['live_transcript_replay_receipt']
    assert replay_receipt_commits(row, UID) == [['b']]

    processor._queue_v2_retry([deepcopy(raws['b']), deepcopy(raws['c'])])
    with pytest.raises(RuntimeError, match='ack lost'):
        await drain()
    assert processor._v2_committed_ids == set()
    assert row['live_transcript_replay_receipt'] == first_blob

    processor._queue_v2_retry([deepcopy(raws['b']), deepcopy(raws['c']), deepcopy(raws['d'])])
    await drain()
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I have'), ('c', 'to'), ('d', 'go')], stored
    assert row['live_transcript_replay_receipt'] == first_blob
    assert replay_receipt_commits(row, UID) == [['b']]

    await processor._process_v2_batches([deepcopy(raws['b']), deepcopy(raws['c']), deepcopy(raws['d'])], [], {})
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I have'), ('c', 'to'), ('d', 'go')], stored
    assert row['live_transcript_replay_receipt'] == first_blob


@pytest.mark.parametrize('labeled', [False, True])
def test_consecutive_lost_ack_transaction_attempts_keep_first_receipt(world, labeled):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    chain = [speech('b', 'have', 0.2, 0.4, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(chain))
    first_blob = row['live_transcript_replay_receipt']
    assert replay_receipt_commits(row, 'u') == [['b']]
    for sid, text, start, end in [
        ('c', 'to', 0.4, 0.6),
        ('d', 'go', 0.6, 0.8),
        ('e', 'now', 0.8, 1.0),
        ('f', 'then', 1.0, 1.2),
    ]:
        chain.append(speech(sid, text, start, end, **common))
        merged = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(chain))
        assert merged.absorbed_into == {}
        assert row['live_transcript_replay_receipt'] == first_blob
    stored = read(world)['transcript_segments']
    assert [(s['id'], s['text']) for s in stored] == [
        ('a', 'I have'),
        ('c', 'to'),
        ('d', 'go'),
        ('e', 'now'),
        ('f', 'then'),
    ]
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(chain))
    assert read(world)['transcript_segments'] == stored
    assert row['live_transcript_replay_receipt'] == first_blob
    assert replay_receipt_commits(row, 'u') == [['b']]


@pytest.mark.parametrize('labeled', [False, True])
def test_replayed_batch_stores_new_ids_without_absorbing(world, labeled):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    fresh = [speech('b', 'have', 0.2, 0.4, **common), speech('c', 'to', 0.4, 0.6, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    blob = row['live_transcript_replay_receipt']
    merged = db.update_conversation_segments(
        'u', 'c', [], live_segments=[deepcopy(fresh[0]), speech('d', 'go', 0.6, 0.8, **common)]
    )
    assert merged.absorbed_into == {}
    stored = read(world)['transcript_segments']
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I have to'), ('d', 'go')], stored
    assert replay_receipt_commits(row, 'u') == [['b', 'c']]
    assert row['live_transcript_replay_receipt'] == blob
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == stored
    assert row['live_transcript_replay_receipt'] == blob


@pytest.mark.parametrize('labeled', [False, True])
def test_duplicate_ids_within_one_batch_commit_once(world, labeled):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    store.rows[path]['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    b = speech('b', 'have', 0.2, 0.4, **common)
    fresh = [b, deepcopy(b), speech('c', 'to', 0.4, 0.6, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    stored = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in stored) == 'I have to', stored
    assert replay_receipt_commits(store.rows[path], 'u') == [['b', 'c']]


@pytest.mark.parametrize('labeled', [False, True])
def test_forward_absorption_receipt_blocks_full_batch_replay(world, labeled):
    store, path, _ = world
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'hi', 0, 1)]
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    fresh = [
        speech('b', 'this is a longer unfinished phrase', 1, 2, speaker_id=1),
        speech('c', 'this is an even much longer unfinished phrase that wins', 2, 3, speaker_id=2),
    ]
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    if labeled:
        assert merged.absorbed_into == {'b': 'c'}
        expected_ids, expected_receipt = ['a', 'c'], [['b']]
    else:
        assert merged.absorbed_into == {'a': 'b', 'b': 'c'}
        expected_ids, expected_receipt = ['c'], [['a', 'b']]
    first = read(world)['transcript_segments']
    assert [s['id'] for s in first] == expected_ids
    assert replay_receipt_commits(row, 'u') == expected_receipt
    replayed = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert replayed.absorbed_into == {}
    assert read(world)['transcript_segments'] == first
    db.update_conversation_segments('u', 'c', [], live_segments=[speech('a', 'hi', 0, 1), *deepcopy(fresh)])
    assert read(world)['transcript_segments'] == first


def test_replay_receipt_eviction_keeps_newest_commits(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    oldest = [f'old-{i}' for i in range(RECEIPT_BATCH_LIMIT)]
    middle = [f'mid-{i}' for i in range(RECEIPT_BATCH_LIMIT)]
    row['live_transcript_replay_receipt'] = db._protect_json_value({'commits': [oldest, middle]}, 'u', 'enhanced')
    fresh = [speech(f'new-{i}', 'word', 0.2 + 0.2 * i, 0.4 + 0.2 * i, **common) for i in range(3)]
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    new_ids = [s['id'] for s in fresh]
    assert set(merged.absorbed_into) == set(new_ids)
    assert replay_receipt_commits(row, 'u') == [middle, new_ids]
    first = read(world)['transcript_segments']
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == first
    assert replay_receipt_commits(row, 'u') == [middle, new_ids]


def test_replay_receipt_holds_two_full_batches(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    batches = []
    start = 0.2
    for batch_index in range(RECEIPT_COMMIT_LIMIT):
        fresh = []
        for _ in range(RECEIPT_BATCH_LIMIT):
            fresh.append(speech(f'b{batch_index}-{len(fresh)}', 'w', start, start + 0.2, **common))
            start += 0.2
        merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
        assert set(merged.absorbed_into) == {s['id'] for s in fresh}
        batches.append(fresh)
    commits = replay_receipt_commits(row, 'u')
    assert commits == [[s['id'] for s in batch] for batch in batches]
    assert sum(len(commit) for commit in commits) == RECEIPT_TOTAL_LIMIT
    blob = row['live_transcript_replay_receipt']
    first = read(world)['transcript_segments']
    for batch in batches:
        replayed = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(batch))
        assert replayed.absorbed_into == {}
        assert read(world)['transcript_segments'] == first
        assert row['live_transcript_replay_receipt'] == blob


def test_oversized_batch_absorbs_nothing_and_stays_replay_safe(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    fresh = [speech(f'x{i}', 'w', 0.2 + 0.2 * i, 0.4 + 0.2 * i, **common) for i in range(1000)]
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert merged.absorbed_into == {}
    assert merged.removed_ids == []
    stored = read(world)['transcript_segments']
    assert [s['id'] for s in stored] == ['a'] + [s['id'] for s in fresh]
    assert 'live_transcript_replay_receipt' not in row
    replayed = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert replayed.absorbed_into == {}
    assert read(world)['transcript_segments'] == stored
    assert 'live_transcript_replay_receipt' not in row
    tail = next(s for s in stored if s['id'] == 'x999')
    followup = db.update_conversation_segments(
        'u', 'c', [], live_segments=[speech('n1', 'w', tail['end'], tail['end'] + 0.2, **common)]
    )
    assert followup.absorbed_into == {'n1': 'x999'}
    assert replay_receipt_commits(row, 'u') == [['n1']]


def test_forward_absorption_of_tail_stays_within_batch_cap(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'hi', 0, 1, **common)]
    fresh = [speech('b0', 'this is a longer unfinished phrase', 1, 2, speaker_id=1, **common)]
    fresh += [
        speech(f'b{i}', 'w', 2 + 0.2 * (i - 1), 2.2 + 0.2 * (i - 1), speaker_id=1, **common)
        for i in range(1, RECEIPT_BATCH_LIMIT)
    ]
    assert len(fresh) == RECEIPT_BATCH_LIMIT
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert set(merged.absorbed_into) == {'a'} | {s['id'] for s in fresh[1:]}
    commits = replay_receipt_commits(row, 'u')
    assert commits == [['a'] + [s['id'] for s in fresh[1:]]]
    blob = row['live_transcript_replay_receipt']
    first = read(world)['transcript_segments']
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == first
    assert row['live_transcript_replay_receipt'] == blob


def test_nonabsorbing_write_leaves_receipt_byte_identical(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=[speech('b', 'have', 0.2, 0.4, **common)])
    blob = row['live_transcript_replay_receipt']
    other_provider = speech('z', 'Done. A complete reply.', 0.4, 0.6, speaker_id=1)
    merged = db.update_conversation_segments('u', 'c', [], live_segments=[other_provider])
    assert merged.absorbed_into == {}
    assert row['live_transcript_replay_receipt'] == blob
    assert replay_receipt_commits(row, 'u') == [['b']]


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('labeled', [False, True])
def test_long_session_receipt_stays_bounded(world, labeled, level):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    row['data_protection_level'] = level
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    batches = []
    clock = 0.2
    index = 0
    for tick in range(5000):
        fresh = []
        for _ in range(1 + tick % 3):
            index += 1
            fresh.append(speech(f'w{index}', 'w', clock, clock + 0.2, **common))
            clock += 0.2
        batches.append([s['id'] for s in fresh])
        merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
        assert set(merged.absorbed_into) == set(batches[-1])
        commits = replay_receipt_commits(row, 'u')
        assert len(commits) <= RECEIPT_COMMIT_LIMIT
        assert all(len(commit) <= RECEIPT_BATCH_LIMIT for commit in commits)
        assert sum(len(commit) for commit in commits) <= RECEIPT_TOTAL_LIMIT
    assert replay_receipt_commits(row, 'u') == batches[-RECEIPT_COMMIT_LIMIT:]
    blob = row['live_transcript_replay_receipt']
    transcript = read(world)['transcript_segments']
    for ids in batches[-RECEIPT_COMMIT_LIMIT:]:
        replay = [speech(sid, 'w', 0, 0.2, **common) for sid in ids]
        db.update_conversation_segments('u', 'c', [], live_segments=replay)
        assert read(world)['transcript_segments'] == transcript
        assert row['live_transcript_replay_receipt'] == blob
    assert sum(len(commit) for commit in replay_receipt_commits(row, 'u')) < index


@pytest.mark.asyncio
async def test_same_owner_fallback_defers_absorbing_commits_until_drained(monkeypatch):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = _seed_row(
        store,
        'conv-a',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )
    row['audio_timeline'] = {'version': 2}
    other = _seed_row(
        store,
        'conv-b',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('o', 'see', 0, 0.2, **common)],
    )
    other['audio_timeline'] = {'version': 2}
    processor, _sent = _processor(monkeypatch, store, current='conv-a')
    processor.host.state.capture_timeline_v2 = True
    raw_b = dict(_v2_segment('b', T0 + 0.2, T0 + 0.4, 'conv-a', text='have'), **common)
    original_call = processor.host.persistence.call
    first = True

    async def lose_ack(fn, *args, **kwargs):
        nonlocal first
        accepted = await original_call(fn, *args, **kwargs)
        if fn is db.update_conversation_segments and first:
            first = False
            raise RuntimeError('ack lost after commit')
        return accepted

    processor.host.persistence.call = lose_ack
    with pytest.raises(RuntimeError, match='ack lost'):
        await processor._process_v2_batches([dict(raw_b)], [], {})
    first_blob = row['live_transcript_replay_receipt']
    assert replay_receipt_commits(row, UID) == [['b']]

    processor.segment_buffer.extend(
        _v2_segment(f'fill-{i}', T0 + 10 + i, T0 + 10 + i + 0.1, 'conv-a', text='f') for i in range(1000)
    )
    processor._queue_v2_retry([dict(raw_b)])
    assert 'b' in processor._v2_legacy_fallback_ids
    processor.segment_buffer.clear()
    processor._v2_fallback_retry_until['b'] = time.monotonic() + 600.0

    async def drain(extra=(), photos=()):
        pending = list(processor.segment_buffer) + [dict(raw) for raw in extra]
        processor.segment_buffer.clear()
        await processor._process_v2_batches(pending, list(photos), {})

    photo = ConversationPhoto(id='ph1', base64='ZmFrZQ==', description='a photo', discarded=False)
    raw_c = dict(_v2_segment('c', T0 + 0.4, T0 + 0.6, 'conv-a', text='to'), **common)
    raw_x = dict(_v2_segment('x', T0 + 0.4, T0 + 0.6, 'conv-b', text='unrelated'), **common)
    processor.enqueue([dict(raw_c)])
    for _ in range(4):
        await drain()
        assert [item['id'] for item in processor.segment_buffer] == ['c']
        deferred = processor.segment_buffer[0]
        assert deferred['start'] == T0 + 0.4 and deferred['end'] == T0 + 0.6
        assert 'c' not in processor._v2_retry_counts
        stored = db._decode_transcript_segments_strict(
            UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
        )
        assert [(s['id'], s['text']) for s in stored] == [('a', 'I have')]
        assert row['live_transcript_replay_receipt'] == first_blob
    await drain(extra=[raw_x], photos=[photo])
    assert [item['id'] for item in processor.segment_buffer] == ['c']
    other_stored = db._decode_transcript_segments_strict(
        UID, other['transcript_segments'], bool(other.get('transcript_segments_compressed'))
    )
    assert ' '.join(s['text'] for s in other_stored) == 'see unrelated'
    assert replay_receipt_commits(other, UID) == [['x']]
    assert row.get('photos') and row['photos'][0]['id'] == 'ph1'

    processor._v2_fallback_retry_until.pop('b', None)
    await processor._persist_v1_unplaced(processor._v2_legacy_fallback[0])
    processor._v2_legacy_fallback.popleft()
    processor._v2_legacy_fallback_ids.discard('b')
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I have')]
    assert row['live_transcript_replay_receipt'] == first_blob
    await drain()
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I have to')]
    assert replay_receipt_commits(row, UID) == [['b'], ['c']]


@pytest.mark.asyncio
async def test_retry_exhaustion_fallback_also_defers_same_owner_group(monkeypatch):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = _seed_row(
        store,
        'conv-a',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )
    row['audio_timeline'] = {'version': 2}
    processor, _sent = _processor(monkeypatch, store, current='conv-a')
    processor.host.state.capture_timeline_v2 = True
    raw_f = dict(_v2_segment('f', T0 + 0.2, T0 + 0.4, 'conv-a', text='kept'), **common)
    for _ in range(6):
        processor._queue_v2_retry([dict(raw_f)])
        processor.segment_buffer.clear()
    assert 'f' in processor._v2_legacy_fallback_ids
    assert 'f' not in processor._v2_retry_counts

    raw_g = dict(_v2_segment('g', T0 + 0.4, T0 + 0.6, 'conv-a', text='next'), **common)
    processor.enqueue([dict(raw_g)])
    pending = list(processor.segment_buffer)
    processor.segment_buffer.clear()
    await processor._process_v2_batches(pending, [], {})
    assert [item['id'] for item in processor.segment_buffer] == ['g']
    assert 'g' not in processor._v2_retry_counts
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('a', 'I')]
    assert 'live_transcript_replay_receipt' not in row

    await processor._persist_v1_unplaced(processor._v2_legacy_fallback[0])
    processor._v2_legacy_fallback.popleft()
    processor._v2_legacy_fallback_ids.discard('f')
    pending = list(processor.segment_buffer)
    processor.segment_buffer.clear()
    await processor._process_v2_batches(pending, [], {})
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert [(s['id'], s['text']) for s in stored] == [('f', 'kept'), ('a', 'I next')], stored
    assert replay_receipt_commits(row, UID) == [['g']]


@pytest.mark.asyncio
async def test_process_loop_requeue_dedupes_deferred_same_owner_group(monkeypatch):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = _seed_row(
        store,
        'conv-a',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )
    row['audio_timeline'] = {'version': 2}
    other = _seed_row(
        store,
        'conv-b',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('o', 'see', 0, 0.2, **common)],
    )
    other['audio_timeline'] = {'version': 2}
    processor, _sent = _processor(monkeypatch, store, current='conv-a')
    processor.host.state.capture_timeline_v2 = True
    raw_b = dict(_v2_segment('b', T0 + 0.2, T0 + 0.4, 'conv-a', text='have'), **common)
    original_call = processor.host.persistence.call
    first = True

    async def lose_ack(fn, *args, **kwargs):
        nonlocal first
        accepted = await original_call(fn, *args, **kwargs)
        if fn is db.update_conversation_segments and first:
            first = False
            raise RuntimeError('ack lost after commit')
        return accepted

    processor.host.persistence.call = lose_ack
    with pytest.raises(RuntimeError, match='ack lost'):
        await processor._process_v2_batches([dict(raw_b)], [], {})
    assert replay_receipt_commits(row, UID) == [['b']]

    processor.segment_buffer.extend(
        _v2_segment(f'fill-{i}', T0 + 10 + i, T0 + 10 + i + 0.1, 'conv-a', text='f') for i in range(1000)
    )
    processor._queue_v2_retry([dict(raw_b)])
    assert 'b' in processor._v2_legacy_fallback_ids
    processor.segment_buffer.clear()

    raw_c = dict(_v2_segment('c', T0 + 0.4, T0 + 0.6, 'conv-a', text='to'), **common)
    raw_x = dict(_v2_segment('x', T0 + 0.4, T0 + 0.6, 'conv-b', text='boom'), **common)

    async def fail_other(fn, *args, **kwargs):
        if fn is db.update_conversation_segments and args[1] == 'conv-b':
            raise RuntimeError('conv-b write failed')
        return await original_call(fn, *args, **kwargs)

    processor.host.persistence.call = fail_other
    drain = [dict(raw_c), dict(raw_x)]
    with pytest.raises(RuntimeError, match='conv-b write failed'):
        await processor._process_v2_batches(drain, [], {})
    assert [item['id'] for item in processor.segment_buffer] == ['c']

    processor._queue_v2_retry([raw for raw in drain if str(raw.get('id')) not in processor._v2_committed_ids])
    buffered = [item['id'] for item in processor.segment_buffer]
    assert buffered.count('c') == 1
    assert buffered.count('x') == 1
    assert 'c' not in processor._v2_retry_counts
    assert processor._v2_retry_counts['x'] == 1


@pytest.mark.asyncio
async def test_deferred_group_overflows_to_bounded_fallback(monkeypatch):
    store = StrictFirestore()
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    _seed_row(
        store,
        'conv-a',
        started_at=datetime.fromtimestamp(T0, tz=timezone.utc),
        segments=[speech('a', 'I', 0, 0.2, **common)],
    )['audio_timeline'] = {'version': 2}
    processor, _sent = _processor(monkeypatch, store, current='conv-a')
    processor.host.state.capture_timeline_v2 = True
    parked = dict(_v2_segment('b', T0 + 0.2, T0 + 0.4, 'conv-a', text='have'), **common)
    processor._v2_legacy_fallback.append(parked)
    processor._v2_legacy_fallback_ids.add('b')
    fillers = [
        dict(_v2_segment(f'f-{i}', T0 + 10 + i, T0 + 10 + i + 0.1, 'conv-a', text='f'), **common) for i in range(1000)
    ]
    processor.segment_buffer.extend(fillers)
    raw_c = dict(_v2_segment('c', T0 + 0.4, T0 + 0.6, 'conv-a', text='to'), **common)
    await processor._process_v2_batches([raw_c], [], {})
    assert 'c' in processor._v2_legacy_fallback_ids
    queued = next(raw for raw in processor._v2_legacy_fallback if raw.get('id') == 'c')
    assert queued['start'] == T0 + 0.4 and queued['end'] == T0 + 0.6
    assert [item['id'] for item in processor.segment_buffer] == [item['id'] for item in fillers]
    assert 'c' not in processor._v2_retry_counts

    processor._v2_legacy_fallback.extend(
        dict(_v2_segment(f'fb-{i}', T0 + 20 + i, T0 + 20 + i + 0.1, 'conv-a', text='x'), **common) for i in range(998)
    )
    fallback_ids = set(processor._v2_legacy_fallback_ids)
    fallback_len = len(processor._v2_legacy_fallback)
    raw_d = dict(_v2_segment('d', T0 + 0.6, T0 + 0.8, 'conv-a', text='go'), **common)
    with pytest.raises(RuntimeError, match='capacity exhausted'):
        await processor._process_v2_batches([raw_d], [], {})
    assert len(processor._v2_legacy_fallback) == fallback_len
    assert processor._v2_legacy_fallback_ids == fallback_ids
    assert [item['id'] for item in processor.segment_buffer] == [item['id'] for item in fillers]


def test_transaction_attempt_retry_replans_from_committed_receipt(world, monkeypatch):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    fresh = [speech('b', 'have', 0.2, 0.4, **common), speech('c', 'to', 0.4, 0.6, **common)]

    def twice(client, call):
        call(client.transaction())
        return call(client.transaction())

    monkeypatch.setattr(db, 'run_transactional', twice)
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    stored = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in stored) == 'I have to', stored
    assert replay_receipt_commits(row, 'u') == [['b', 'c']]


@pytest.mark.parametrize('stored', ['undecodable-blob', 0, '', None])
def test_undecodable_receipt_fails_closed(world, stored):
    store, path, _ = world
    row = store.rows[path]
    original = [speech('a', 'I', 0, 0.2)]
    row['transcript_segments'] = deepcopy(original)
    row['live_transcript_replay_receipt'] = stored
    with pytest.raises((MalformedDocError, ValueError, zlib.error)):
        db.update_conversation_segments('u', 'c', [], live_segments=[speech('b', 'have', 0.2, 0.4)])
    assert read(world)['transcript_segments'] == original


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'other': ['b']},
        {'commits': [['b']], 'unknown': True},
        {'commits': {'b': 'a'}},
        {'commits': [['b', 7]]},
        {'commits': ['b', 'c']},
        {'commits': [[f'id-{i}' for i in range(RECEIPT_BATCH_LIMIT + 1)]]},
        {'commits': [['a'], ['b'], ['c']]},
        {'absorbed_ids': ['b', 'c']},
        ['b'],
        'not-a-mapping',
    ],
)
def test_malformed_receipt_payload_fails_closed(world, payload):
    store, path, _ = world
    row = store.rows[path]
    original = [speech('a', 'I', 0, 0.2)]
    row['transcript_segments'] = deepcopy(original)
    row['live_transcript_replay_receipt'] = db._protect_json_value(payload, 'u', 'enhanced')
    with pytest.raises(MalformedDocError):
        db.update_conversation_segments('u', 'c', [], live_segments=[speech('b', 'have', 0.2, 0.4)])
    assert read(world)['transcript_segments'] == original


@pytest.mark.parametrize('source,target', [('standard', 'enhanced'), ('enhanced', 'standard')])
def test_receipt_survives_protection_level_migration(world, monkeypatch, source, target):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    row['data_protection_level'] = source
    fresh = [speech('b', 'have', 0.2, 0.4, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    blob = row['live_transcript_replay_receipt']

    def get_all(refs, field_paths):
        for ref in refs:
            snap = ref.get()
            snap.reference = ref
            snap.id = 'c'
            yield snap

    monkeypatch.setattr(store, 'get_all', get_all, raising=False)
    monkeypatch.setattr(store, 'batch', MagicMock, raising=False)
    monkeypatch.setattr(
        StrictFirestoreCollection, 'select', lambda self, fields: SimpleNamespace(stream=lambda: []), raising=False
    )
    monkeypatch.setattr(db, 'db', store)
    db.migrate_conversations_level_batch('u', ['c'], target)
    assert row['data_protection_level'] == target
    assert row['live_transcript_replay_receipt'] == blob
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    stored = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in stored) == 'I have', stored
    assert row['live_transcript_replay_receipt'] == blob


@pytest.mark.parametrize('writer', ['upsert_conversation_with_lifecycle', 'persist_processing_result_with_lifecycle'])
def test_lifecycle_writers_preserve_replay_receipt(world, monkeypatch, writer):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    fresh = [speech('b', 'have', 0.2, 0.4, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    blob = row['live_transcript_replay_receipt']
    snapshot = dict(
        id='c',
        transcript_segments=read(world)['transcript_segments'],
        data_protection_level='standard',
        structured={'title': 'Generated', 'overview': 'Old names remain until explicit refresh.'},
    )
    monkeypatch.setattr(db, 'db', store)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    original_set = StrictFirestoreTransaction.set

    def set_with_merge(transaction, ref, data, merge=False):
        if merge:
            transaction.update(ref, data)
        else:
            original_set(transaction, ref, data)

    monkeypatch.setattr(StrictFirestoreTransaction, 'set', set_with_merge)
    encoded = db._prepare_conversation_for_write(snapshot, 'u', 'standard')
    getattr(db, writer).__wrapped__.__wrapped__('u', encoded)
    assert row['live_transcript_replay_receipt'] == blob
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    stored = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in stored) == 'I have', stored
    assert row['live_transcript_replay_receipt'] == blob


def test_non_live_writes_preserve_receipt(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    fresh = [speech('b', 'have', 0.2, 0.4, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    blob = row['live_transcript_replay_receipt']
    db.update_conversation_segments(
        'u',
        'c',
        [{'id': 'a', 'translations': [{'lang': 'fr', 'text': 'Bonjour'}]}],
        segment_update_fields=('translations',),
    )
    assert row['live_transcript_replay_receipt'] == blob
    db.update_conversation_segments(
        'u', 'c', [speech('a', 'I have', 0, 0.4, **common), speech('z', 'snapshot tail', 0.4, 0.6, **common)]
    )
    assert row['live_transcript_replay_receipt'] == blob
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    stored = read(world)['transcript_segments']
    assert [s['id'] for s in stored] == ['a', 'z']
    assert 'have have' not in ' '.join(s['text'] for s in stored)


def test_unplaced_segments_keep_ids_without_receipt(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    fresh = [speech('u1', 'have', 0.2, 0.4, audio_alignment='unplaced', **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    stored = read(world)['transcript_segments']
    assert [s['id'] for s in stored] == ['a', 'u1']
    assert 'live_transcript_replay_receipt' not in row
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == stored
