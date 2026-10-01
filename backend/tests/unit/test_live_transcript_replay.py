import json
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
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreTransaction,
)
from tests.unit.test_audio_timeline_round3 import _processor, _seed_row, _v2_segment, UID, T0
from tests.unit.test_manual_speaker_assignments import read, world
from utils.manual_speaker_assignments import LIVE_TRANSCRIPT_REPLAY_RECEIPT_LIMIT


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


def replay_receipt_ids(row, uid):
    raw = row.get('live_transcript_replay_receipt')
    if raw is None:
        return None
    return db._reveal_json_value(raw, uid, True)['absorbed_ids']


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
    assert replay_receipt_ids(row, 'u') == ['b', 'c']
    replayed_merge = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    replayed = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in replayed) == ' '.join(s['text'] for s in first) == 'I have to', replayed
    assert replayed == first
    assert replayed_merge.updated_ids == set()
    assert replayed_merge.removed_ids == []
    assert replayed_merge.absorbed_into == {}
    assert replay_receipt_ids(row, 'u') == ['b', 'c']
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
    assert replay_receipt_ids(row, UID) == ['b']
    sent.clear()
    raw_to = dict(_v2_segment('c', T0 + 0.4, T0 + 0.6, 'conv-replay', text='to'), **common)
    await processor._process_v2_batches([raw_to], [], {})
    stored = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))
    )
    assert ' '.join(s['text'] for s in stored) == 'I have to', stored
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


@pytest.mark.parametrize('labeled', [False, True])
def test_partially_replayed_batch_accepts_only_new_ids(world, labeled):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    if labeled:
        db.assign_conversation_speaker('u', 'c', is_user=True, speaker_id=0)
    fresh = [speech('b', 'have', 0.2, 0.4, **common), speech('c', 'to', 0.4, 0.6, **common)]
    db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    merged = db.update_conversation_segments(
        'u', 'c', [], live_segments=[deepcopy(fresh[0]), speech('d', 'go', 0.6, 0.8, **common)]
    )
    assert merged.absorbed_into == {'d': 'a'}
    stored = read(world)['transcript_segments']
    assert ' '.join(s['text'] for s in stored) == 'I have to go', stored
    assert replay_receipt_ids(row, 'u') == ['b', 'c', 'd']
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == stored


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
    assert replay_receipt_ids(store.rows[path], 'u') == ['b', 'c']


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
        expected_ids, expected_receipt = ['a', 'c'], ['b']
    else:
        assert merged.absorbed_into == {'a': 'b', 'b': 'c'}
        expected_ids, expected_receipt = ['c'], ['a', 'b']
    first = read(world)['transcript_segments']
    assert [s['id'] for s in first] == expected_ids
    assert replay_receipt_ids(row, 'u') == expected_receipt
    replayed = db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert replayed.absorbed_into == {}
    assert read(world)['transcript_segments'] == first
    db.update_conversation_segments('u', 'c', [], live_segments=[speech('a', 'hi', 0, 1), *deepcopy(fresh)])
    assert read(world)['transcript_segments'] == first


def test_replay_receipt_eviction_keeps_newest_ids(world):
    store, path, _ = world
    common = dict(stt_provider='soniox', speaker_id_scope='epoch:0', audio_capture_run=0)
    row = store.rows[path]
    row['transcript_segments'] = [speech('a', 'I', 0, 0.2, **common)]
    seeded = [f'seeded-{i:04}' for i in range(LIVE_TRANSCRIPT_REPLAY_RECEIPT_LIMIT)]
    row['live_transcript_replay_receipt'] = db._protect_json_value({'absorbed_ids': seeded}, 'u', 'enhanced')
    fresh = [speech(f'batch-{i}', 'word', 0.2 + 0.2 * i, 0.4 + 0.2 * i, **common) for i in range(1000)]
    merged = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    new_ids = [s['id'] for s in fresh]
    assert set(merged.absorbed_into) == set(new_ids)
    assert replay_receipt_ids(row, 'u') == seeded[1000:] + new_ids
    first = read(world)['transcript_segments']
    db.update_conversation_segments('u', 'c', [], live_segments=deepcopy(fresh))
    assert read(world)['transcript_segments'] == first
    assert replay_receipt_ids(row, 'u') == seeded[1000:] + new_ids


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
    assert replay_receipt_ids(row, 'u') == ['b', 'c']


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
        {'absorbed_ids': ['b'], 'unknown': True},
        {'absorbed_ids': {'b': 'a'}},
        {'absorbed_ids': ['b', 7]},
        {'absorbed_ids': [f'id-{i}' for i in range(LIVE_TRANSCRIPT_REPLAY_RECEIPT_LIMIT + 1)]},
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
