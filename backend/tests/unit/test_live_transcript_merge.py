"""#15247 regressions: the committing receipt owns live speech boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as db
from models.transcript_segment import TranscriptSegment
from routers.listen import transcripts
from tests.unit.test_manual_speaker_assignments import world, read
from utils.manual_speaker_assignments import LiveTranscriptMerge, merge_live_segments


def speech(sid, text='Hello', speaker=0, start=0, end=1):
    return dict(
        id=sid,
        text=text,
        speaker=f'SPEAKER_{speaker:02}',
        speaker_id=speaker,
        start=start,
        end=end,
        is_user=False,
        person_id=None,
    )


@pytest.mark.parametrize(
    'a_text,b_text,speaker',
    [
        ('Hello', 'long fresh continuation.', 0),
        ('a' * 130, 'lowercase continuation', 0),
        ('hi', 'a much longer continuation.', 1),
        ('Done. hi', 'a much longer continuation.', 1),
        ('A long unfinished phrase', 'yes. Another sentence.', 1),
        ('A long unfinished phrase', 'yes', 1),
    ],
)
@pytest.mark.parametrize(
    'decision',
    [
        {'person_id': 'new'},
        {'is_user': True},
        {'person_id': None},
        {'person_id': 'new', 'use_for_speech_training': False},
    ],
)
def test_transaction_protects_saved_tail_despite_stale_caller(world, a_text, b_text, speaker, decision):
    store, path, _ = world
    tail = speech('a', a_text)
    fresh = [speech('b', b_text, speaker, 1, 21)]
    store.rows[path]['transcript_segments'] = [tail]
    # Caller planned its inference updates before the user saved a decision.
    stale = deepcopy([tail, *fresh])
    db.assign_conversation_speaker('u', 'c', segment_ids=['a'], **decision)
    before = deepcopy(fresh)
    result = db.update_conversation_segments('u', 'c', stale, live_segments=fresh)
    assert isinstance(result, LiveTranscriptMerge)
    assert result.removed_ids == [] and result.absorbed_into == {}
    assert [s['id'] for s in result.segments] == ['a', 'b']
    assert [(s['text'], s['start'], s['end']) for s in result.segments] == [(a_text, 0, 1), (b_text, 1, 21)]
    assert fresh == before
    assert read(world)['transcript_segments'] == result.segments


def test_speaker_default_protects_fresh_batch_and_selected_clear(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [speech('a')]
    db.assign_conversation_speaker('u', 'c', person_id='new', speaker_id=0)
    db.assign_conversation_speaker('u', 'c', person_id=None, segment_ids=['a'], use_for_speech_training=False)
    fresh = [speech('b', 'hello', 0, 1, 2), speech('c', 'world', 0, 2, 3)]
    result = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert [s['id'] for s in result.segments] == ['a', 'b', 'c']
    assert [s['person_id'] for s in result.segments] == [None, 'new', 'new']
    assert result.removed_ids == []


def test_legacy_receipt_and_incoming_selected_id_are_covered():
    a, b = speech('a'), speech('b', 'world.', 0, 1, 2)
    receipt = {'segments': {'b': {'person_id': None, 'is_user': False}}}
    result = merge_live_segments([a], [b], receipt)
    assert [s['id'] for s in result.segments] == ['a', 'b']
    assert not result.removed_ids


@pytest.mark.parametrize('persisted', [True, False])
def test_forward_absorption_reports_all_retired_ids_once(persisted):
    a = speech('a', 'hi')
    b = speech('b', 'this is a longer unfinished phrase', 1, 1, 2)
    c = speech('c', 'this is an even much longer unfinished phrase that wins', 2, 2, 3)
    result = merge_live_segments([a] if persisted else [], [b, c] if persisted else [a, b, c], {})
    assert [s['id'] for s in result.segments] == ['c']
    assert result.removed_ids == ['a', 'b']
    assert result.absorbed_into == {'a': 'b', 'b': 'c'}


def test_retry_replans_from_new_receipt_without_mutating_input(world, monkeypatch):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [speech('a')]
    fresh = [speech('b', 'world.', 0, 1, 2)]
    attempts = []
    original = db.merge_live_segments

    def plan(persisted, incoming, receipt):
        result = original(persisted, incoming, receipt)
        attempts.append(result)
        return result

    monkeypatch.setattr(db, 'merge_live_segments', plan)

    def retry(client, call):
        # Explicit attempt replay seam; not an emulation of SDK contention.
        baseline = deepcopy(store.rows)
        call(client.transaction())
        store.rows = baseline
        db.assign_conversation_speaker('u', 'c', person_id='new', segment_ids=['a'], firestore_client=store)
        return call(client.transaction())

    original_run = db.run_transactional

    def once_then_retry(client, call):
        monkeypatch.setattr(db, 'run_transactional', original_run)
        return retry(client, call)

    monkeypatch.setattr(db, 'run_transactional', once_then_retry)
    result = db.update_conversation_segments('u', 'c', [], live_segments=fresh)
    assert attempts[0].removed_ids == ['b']
    assert result.removed_ids == []
    assert [s['id'] for s in result.segments] == ['a', 'b']
    assert fresh[0]['text'] == 'world.'


@pytest.mark.asyncio
async def test_live_adapter_uses_transaction_result_for_client_ids(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [speech('a', 'hi')]
    calls = []

    async def persist(fn, *args, **kwargs):
        calls.append((fn, kwargs))
        if fn is db.update_conversation_segments:
            return fn(*args, **kwargs)
        return True

    host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(speaker_map_dirty=False),
        persistence=SimpleNamespace(call=persist),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(None)
    processor.cache.data = deepcopy(store.rows[path])
    current = SimpleNamespace(id='c', transcript_segments=[TranscriptSegment(**speech('a', 'hi'))])
    result = await processor._update_live_conversation(
        current,
        [TranscriptSegment(**speech('b', 'a long continuation.', 1, 1, 21))],
        [],
        datetime.now(timezone.utc),
        None,
    )
    accepted, updated, removed = result
    assert removed == ['a']
    assert [s.id for s in accepted.transcript_segments] == [s.id for s in updated] == ['b']
    assert [s['id'] for s in read(world)['transcript_segments']] == ['b']
    assert [s['id'] for s in processor.cache.data['transcript_segments']] == ['b']
    assert calls[0][1]['live_segments'][0]['text'] == 'a long continuation.'


@pytest.fixture
def full_live_batch():
    # Runtime's buffer cap is 1000; 10k retained segments stresses a long session.
    persisted = [speech(f'old-{i}', 'A complete sentence.', i % 2, i * 4, i * 4 + 3) for i in range(10000)]
    fresh = [speech(f'new-{i}', 'A complete sentence.', i % 2, 40000 + i * 4, 40003 + i * 4) for i in range(1000)]
    return persisted, fresh


def test_full_live_buffer_preserves_speech_under_existing_cpu_budget(full_live_batch):
    persisted, fresh = full_live_batch
    result = merge_live_segments(persisted, fresh, {'speakers': {'0': {'is_user': False, 'person_id': None}}})
    assert len(result.segments) == 11000
    assert not result.removed_ids
    assert result.segments[0] is persisted[0]  # Historical models need not be rebuilt each retry.
    assert len(result.updated_ids) == 1001
