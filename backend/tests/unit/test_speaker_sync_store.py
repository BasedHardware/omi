"""A sync-timed window is proven on the sync store alone when the live store overlaps it."""

from types import SimpleNamespace

import pytest

from models.conversation import Conversation
from tests.unit.test_conversation_speaker_resolution_stage import (
    STARTED,
    FakeAudio,
    _conversation,
    _span_manifest,
    env,  # noqa: F401
    stage,
)
from utils.conversations import speaker_sync_store as store
from utils.conversations.audio_placement import AudioPlacement, prepare_audio_coverage

SR = stage.SAMPLE_RATE
ORIGIN = STARTED.timestamp()
PLAN = [0, 1] * 4


def _chunk(path, start, seconds, *, is_batch=False):
    span = {'start': start, 'samples': int(seconds * SR), 'sample_rate': SR}
    return {'path': path, 'generation': 1, 'timestamp': start, 'span': span, 'is_batch': is_batch}


def _session_class(chunks, pcm, reads):
    class Session:
        def __init__(self, *args):
            self.deadline = float('inf')
            self.chunks = chunks
            self.limit_hit = False
            self.reason = 'none'
            self.cache = {}
            self.max_downloads = None
            self.max_pcm_bytes = None

        def in_budget(self):
            return True

        def release_pcm(self):
            self.cache.clear()

        def fetch(self, path):
            reads.append(path)
            self.cache[path] = (pcm[path], 'none')
            return pcm[path]

    return Session


@pytest.fixture
def two_stores(monkeypatch):
    """Sync store carries the voices; the live store overlaps it with one wrong voice."""
    audio = FakeAudio(PLAN)
    sync = [(f'{i}.opus.enc', start, bytes_) for i, (start, bytes_) in enumerate(audio.chunks)]
    live_pcm = b"\x70\x17" * int(32 * SR)  # 6000: FakeDiarizer reads this as voice 5.
    chunks = [_chunk(path, start, len(data) / 2 / SR) for path, start, data in sync]
    chunks.append(_chunk('0.batch.enc', ORIGIN + 1.0, 32, is_batch=True))
    pcm = {path: data for path, _, data in sync} | {'0.batch.enc': live_pcm}
    reads = []
    session = _session_class(chunks, pcm, reads)
    monkeypatch.setattr(stage, 'AudioChunkReadSession', session)
    monkeypatch.setattr(store, 'AudioChunkReadSession', session)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT', '100')
    monkeypatch.delenv(store.SPEAKER_SYNC_STORE_ENV, raising=False)
    files = [
        _span_manifest(
            ORIGIN, [(c['span']['start'], c['span']['start'] + c['span']['samples'] / SR) for c in chunks[:-1]]
        ),
        _span_manifest(ORIGIN, [(ORIGIN + 1.0, ORIGIN + 33.0)], file_id='af2'),
    ]
    return files, reads


def _resolve(files, **kwargs):
    conversation = _conversation(PLAN, **kwargs)
    conversation.audio_files = files
    stage.resolve_speakers_for_processing('u1', conversation)
    return conversation


def test_voices_come_from_the_sync_store_and_live_audio_is_never_read(env, two_stores):  # noqa: F811
    _, diarizer = env
    files, reads = two_stores
    conversation = _resolve(files)
    assert diarizer.calls == len(PLAN)
    assert reads and all(path.endswith('.opus.enc') for path in reads)
    assert conversation.speaker_resolution.status == 'resolved'
    ids = [s.speaker_id for s in conversation.transcript_segments]
    assert len(set(ids)) == 2 and ids[:2] == ids[2:4] and ids[0] != ids[1]


def test_kill_switch_restores_the_refusal(env, two_stores, monkeypatch):  # noqa: F811
    _, diarizer = env
    monkeypatch.setenv(store.SPEAKER_SYNC_STORE_ENV, 'false')
    conversation = _resolve(two_stores[0])
    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_outside_the_cohort_the_recording_still_refuses(env, two_stores, monkeypatch):  # noqa: F811
    _, diarizer = env
    monkeypatch.delenv('SPEAKER_EVIDENCE_MODE')
    monkeypatch.delenv('SPEAKER_EVIDENCE_MODE_SERVE_PERCENT')
    monkeypatch.setattr('utils.conversations.speaker_window_cohort.client_seen_cached', lambda uid: False)
    conversation = _resolve(two_stores[0])
    assert diarizer.calls == 0
    assert conversation.speaker_resolution.status == 'unavailable'


def test_final_batch_segments_stay_refused_because_their_store_is_unknown(env, two_stores):  # noqa: F811
    _, diarizer = env
    files, reads = two_stores
    conversation = _resolve(files, scopes=['final:batch:unit'] * len(PLAN))
    assert diarizer.calls == 0 and reads == []
    assert conversation.speaker_resolution.status == 'unavailable'


def test_a_rerun_reuses_only_vectors_cut_from_the_sync_store(env, two_stores):  # noqa: F811
    _, diarizer = env
    files, _ = two_stores
    conversation = _resolve(files)
    calls = diarizer.calls
    stage.resolve_speakers_for_processing('u1', Conversation(**conversation.model_dump(mode='python')))
    assert diarizer.calls == calls


def test_a_vector_saved_under_the_bare_segment_id_is_not_trusted(env, two_stores, monkeypatch):  # noqa: F811
    store_cache, diarizer = env
    files, _ = two_stores
    conversation = _conversation(PLAN)
    conversation.audio_files = files
    keys = {}
    original = stage.encode_cache

    def spy(cache, *args, **kwargs):
        keys.update(cache)
        return original(cache, *args, **kwargs)

    monkeypatch.setattr(stage, 'encode_cache', spy)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert keys and all(key.startswith(stage.CAPTURE_SPAN_KEY_PREFIX) for key in keys)


def _placements(*pairs):
    return {sid: AudioPlacement(None, reason) for sid, reason in pairs}


def _segment(sid, start, end, scope='sync:file'):
    return SimpleNamespace(id=sid, start=start, end=end, speaker_id_scope=scope)


def _run(monkeypatch, chunks, segments, placements, *, limit_hit=False):
    session = _session_class(chunks, {}, [])
    if limit_hit:

        class Limited(session):
            def __init__(self, *args):
                super().__init__(*args)
                self.limit_hit = True

        session = Limited
    monkeypatch.setattr(store, 'AudioChunkReadSession', session)
    monkeypatch.setattr(store, 'per_window_evidence', lambda uid, segments: True)
    monkeypatch.delenv(store.SPEAKER_SYNC_STORE_ENV, raising=False)
    index = prepare_audio_coverage(
        [
            {
                'chunk_timestamps': [c['timestamp'] for c in chunks],
                'chunk_spans': [
                    {'start': c['span']['start'], 'end': c['span']['start'] + c['span']['samples'] / SR} for c in chunks
                ],
            }
        ]
    )
    return store.sync_store_placements('u1', 'c1', segments, placements, index, 100.0, float('inf'), max_spans=100)


TWO_STORES = [_chunk('a.opus.enc', 100.0, 20), _chunk('b.batch.enc', 100.0, 20, is_batch=True)]


def test_promotes_a_window_only_its_own_store_covers(monkeypatch):
    proven = _run(monkeypatch, TWO_STORES, [_segment('s', 2.0, 6.0)], _placements(('s', 'untrusted_clock')))
    assert proven == {'s': AudioPlacement((102.0, 106.0), 'sync', store=store.SYNC_STORE)}


@pytest.mark.parametrize(
    'label,chunks,segment,reason',
    [
        ('live scope', TWO_STORES, _segment('s', 2.0, 6.0, 'soniox:1'), 'untrusted_clock'),
        ('batch scope', TWO_STORES, _segment('s', 2.0, 6.0, 'final:batch:u'), 'untrusted_clock'),
        ('bare scope', TWO_STORES, _segment('s', 2.0, 6.0, 'sync:'), 'untrusted_clock'),
        ('other refusal', TWO_STORES, _segment('s', 2.0, 6.0), 'unplaced'),
        ('already placed', TWO_STORES, _segment('s', 2.0, 6.0), 'sync'),
        (
            'sync store hole',
            [_chunk('a.opus.enc', 100.0, 3), _chunk('b.batch.enc', 100.0, 20, is_batch=True)],
            _segment('s', 2.0, 6.0),
            'untrusted_clock',
        ),
        (
            'sync store overlaps itself',
            [*TWO_STORES, _chunk('c.opus.enc', 101.0, 10)],
            _segment('s', 2.0, 6.0),
            'untrusted_clock',
        ),
        (
            'no overlap to resolve',
            [_chunk('a.opus.enc', 100.0, 20)],
            _segment('s', 2.0, 6.0),
            'untrusted_clock',
        ),
    ],
)
def test_keeps_the_refusal(monkeypatch, label, chunks, segment, reason):
    assert _run(monkeypatch, chunks, [segment], _placements((segment.id, reason))) == {}


def test_listing_budget_keeps_the_refusal(monkeypatch):
    proven = _run(
        monkeypatch, TWO_STORES, [_segment('s', 2.0, 6.0)], _placements(('s', 'untrusted_clock')), limit_hit=True
    )
    assert proven == {}


def test_a_spanless_sync_object_invalidates_the_store():
    spanless = {'path': 'x.opus.enc', 'timestamp': 100.0, 'generation': 1}
    assert not store.sync_store_coverage([TWO_STORES[0], spanless], max_spans=100).validated
    assert not store.sync_store_coverage([TWO_STORES[1]], max_spans=100).validated
    assert store.sync_store_coverage(TWO_STORES, max_spans=100).covers(101.0, 119.0)


def test_proof_stops_early_enough_to_embed_what_it_proved(monkeypatch, two_stores):
    monkeypatch.setattr(stage.time, 'monotonic', lambda: 1000.0)
    files, _ = two_stores
    conversation = _conversation(PLAN)
    pending = conversation.transcript_segments[:3]
    placements = {
        s.id: AudioPlacement((ORIGIN + s.start, ORIGIN + s.end), 'sync', store=store.SYNC_STORE) for s in pending
    }
    session = stage._verified_read_session(
        'u1', conversation, [f.model_dump(mode='python') for f in files], pending, placements, 1040.0
    )
    assert session.verified_segment_ids == {s.id for s in pending}
    assert session.deadline == 1040.0 - 3 * stage.PER_WINDOW_EMBED_RESERVE_SECONDS
