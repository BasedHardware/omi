"""Speaker windows are proven and cut on their own store when the other store overlaps."""

from types import SimpleNamespace

import pytest

from models.conversation import Conversation
from tests.unit.test_conversation_speaker_resolution_stage import (
    STARTED,
    FakeAudio,
    VOICES,
    _conversation,
    _span_manifest,
    env,  # noqa: F401
    stage,
)
from utils.conversations import speaker_sync_store as store
from utils.conversations.audio_placement import AudioPlacement, prepare_audio_coverage
from utils.speakers import processing as speaker_evidence

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
    monkeypatch.setattr(speaker_evidence, '_roster', lambda *_: [])
    monkeypatch.setattr(speaker_evidence.storage, 'store_evidence', lambda *a, **kw: None)
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


def test_unstamped_final_batch_segments_keep_the_refusal(env, two_stores):  # noqa: F811
    _, diarizer = env
    files, reads = two_stores
    conversation = _resolve(files, scopes=['final:batch:unit'] * len(PLAN))
    assert diarizer.calls == 0
    assert reads == []
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
    return store.single_store_placements('u1', 'c1', segments, placements, index, 100.0, float('inf'), max_spans=100)


TWO_STORES = [_chunk('a.opus.enc', 100.0, 20), _chunk('b.batch.enc', 100.0, 20, is_batch=True)]


def test_promotes_a_window_only_its_own_store_covers(monkeypatch):
    proven = _run(monkeypatch, TWO_STORES, [_segment('s', 2.0, 6.0)], _placements(('s', 'untrusted_clock')))
    assert proven == {'s': AudioPlacement((102.0, 106.0), 'sync', store=store.SYNC_STORE)}


@pytest.mark.parametrize(
    'label,chunks,segment,reason',
    [
        ('live scope', TWO_STORES, _segment('s', 2.0, 6.0, 'soniox:1'), 'untrusted_clock'),
        ('bare batch scope', TWO_STORES, _segment('s', 2.0, 6.0, 'final:batch:'), 'untrusted_clock'),
        ('conversation scope', TWO_STORES, _segment('s', 2.0, 6.0, 'final:batch:conversation:c1'), 'untrusted_clock'),
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


@pytest.fixture
def batch_stores(monkeypatch):
    """Live PCM carries two voices; overlapping sync PCM carries the wrong voice."""
    live = FakeAudio(PLAN)
    chunks = [
        _chunk(f'{i}.batch.enc', start, len(data) / 2 / SR, is_batch=True)
        for i, (start, data) in enumerate(live.chunks)
    ]
    chunks.append(_chunk('wrong.opus.enc', ORIGIN + 1.0, 32))
    pcm = {f'{i}.batch.enc': data for i, (_, data) in enumerate(live.chunks)}
    pcm['wrong.opus.enc'] = b'\x70\x17' * int(32 * SR)
    reads = []
    session = _session_class(chunks, pcm, reads)
    monkeypatch.setattr(stage, 'AudioChunkReadSession', session)
    monkeypatch.setattr(store, 'AudioChunkReadSession', session)
    monkeypatch.delenv('SPEAKER_BATCH_STORE_ENABLED', raising=False)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')  # Batch authority supplies the cohort.
    monkeypatch.setattr(
        stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': VOICES[0], 'person': VOICES[1]}
    )
    files = [
        _span_manifest(
            ORIGIN, [(c['span']['start'], c['span']['start'] + c['span']['samples'] / SR) for c in chunks[:-1]]
        ),
        _span_manifest(ORIGIN, [(ORIGIN + 1.0, ORIGIN + 33.0)], file_id='af2'),
    ]
    return files, reads, chunks


def _batch_conversation(files, *, resolved_scopes=False, timing_store='batch'):
    conversation = _conversation(PLAN, scopes=[f'final:batch:unit{i // 2}' for i in range(len(PLAN))])
    conversation.audio_files = files
    for segment in conversation.transcript_segments:
        segment.speaker_match_source = 'batch_pyannote'
        segment.speaker_identity_status = 'no_match'
        segment.provider_speaker = {
            'id': segment.speaker_id,
            'scope': segment.speaker_id_scope,
            'provider': 'parakeet',
            'timing_store': timing_store,
        }
        if resolved_scopes:
            segment.assign_resolved_speaker(segment.speaker_id, 'final:batch:conversation:c1')
    return conversation


def _assert_batch_voices(conversation, reads):
    assert reads and all(path.endswith('.batch.enc') for path in reads)
    assert conversation.speaker_resolution.status == 'resolved'
    ids = [s.speaker_id for s in conversation.transcript_segments]
    assert len(set(ids)) == 2 and ids[:2] == ids[2:4] == ids[4:6] == ids[6:8] and ids[0] != ids[1]
    for segment, voice in zip(conversation.transcript_segments, PLAN):
        assert segment.is_user == (voice == 0)
        assert segment.person_id == ('person' if voice == 1 else None)


def test_final_batch_windows_resolve_on_live_store_alone(env, batch_stores, caplog):  # noqa: F811
    files, reads, _ = batch_stores
    conversation = _batch_conversation(files)
    with caplog.at_level('INFO', logger=store.__name__):
        stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == len(PLAN)
    _assert_batch_voices(conversation, reads)
    assert 'event=conversation_speaker_store candidates=8 proven=8 batch_proven=8 sync_proven=0' in caplog.text


@pytest.mark.parametrize('resolved_scopes', [False, True])
def test_batch_sync_v1_wal_windows_use_only_the_stamped_sync_store(
    env, two_stores, resolved_scopes, monkeypatch
):  # noqa: F811
    monkeypatch.setattr(
        stage, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': VOICES[0], 'person': VOICES[1]}
    )
    files, reads = two_stores
    conversation = _batch_conversation(files, timing_store='sync', resolved_scopes=resolved_scopes)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == len(PLAN)
    assert reads and all(path.endswith('.opus.enc') for path in reads)
    assert conversation.speaker_resolution.status == 'resolved'
    for segment, voice in zip(conversation.transcript_segments, PLAN):
        assert segment.is_user == (voice == 0)
        assert segment.person_id == ('person' if voice == 1 else None)
        assert segment.provider_speaker['timing_store'] == 'sync'
        assert segment.speaker_id_scope.startswith('final:batch:conversation:')


@pytest.mark.parametrize('stamp', [None, '', 'unknown', ['batch']])
def test_missing_or_unknown_batch_timing_store_cannot_choose_live_pcm(env, batch_stores, stamp):  # noqa: F811
    files, reads, _ = batch_stores
    conversation = _batch_conversation(files, timing_store=stamp)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == 0 and reads == []
    assert conversation.speaker_resolution.status == 'unavailable'


def test_stamped_sync_batch_windows_obey_the_batch_switch(env, two_stores, monkeypatch):  # noqa: F811
    monkeypatch.setenv('SPEAKER_BATCH_STORE_ENABLED', 'false')
    files, reads = two_stores
    conversation = _batch_conversation(files, timing_store='sync')
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == 0 and reads == []


def test_batch_kill_switch_restores_untrusted_clock(env, batch_stores, monkeypatch):  # noqa: F811
    files, reads, _ = batch_stores
    enabled = _batch_conversation(files)
    stage.resolve_speakers_for_processing('u1', enabled)
    _assert_batch_voices(enabled, reads)
    env[0].clear()
    reads.clear()
    calls = env[1].calls
    monkeypatch.setenv('SPEAKER_BATCH_STORE_ENABLED', 'false')
    disabled = _batch_conversation(files)
    refusals = []
    locate = stage.locate

    def spy(*args, **kwargs):
        placement = locate(*args, **kwargs)
        refusals.append(placement.reason)
        return placement

    monkeypatch.setattr(stage, 'locate', spy)
    stage.resolve_speakers_for_processing('u1', disabled)
    assert refusals == ['untrusted_clock'] * len(PLAN)
    assert env[1].calls == calls and reads == []
    assert disabled.speaker_resolution.status == 'unavailable'


def test_live_store_hole_abstains_only_affected_windows_without_sync_fallback(env, batch_stores):  # noqa: F811
    files, reads, chunks = batch_stores
    chunks.pop(1)  # Live coverage ends at 20s; sync still covers the entire tail.
    conversation = _batch_conversation(files)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == 5
    assert reads == ['0.batch.enc']
    assert conversation.speaker_resolution.status == 'unavailable'
    assert conversation.transcript_segments[0].is_user
    assert conversation.transcript_segments[1].person_id == 'person'
    for segment in conversation.transcript_segments[5:]:
        assert segment.speaker_id_scope.startswith('final:batch:unit')
        assert not segment.is_user and segment.person_id is None


def test_resolved_batch_scopes_use_the_retained_provider_unit(env, batch_stores):  # noqa: F811
    files, reads, _ = batch_stores
    conversation = _batch_conversation(files, resolved_scopes=True)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == len(PLAN)
    _assert_batch_voices(conversation, reads)


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('resolved_scopes', [False, True])
def test_long_batch_timing_stamps_survive_persistence_and_prove_only_their_store(monkeypatch, level, resolved_scopes):
    from database import conversations as db
    from utils.batch_pipeline.contracts import Priority, WorkItem
    from utils.batch_pipeline.projection_parts import stamp_speaker
    from utils.conversations import speaker_grouping_storage as grouping

    # Three units and 300 segments exceed the 256-entry sidecar limit.
    count = 300
    conversation = _conversation([0] * count, seconds=1)
    for i, segment in enumerate(conversation.transcript_segments):
        unit = i // 100
        item = WorkItem(
            f'unit{unit}',
            'u1',
            ORIGIN + unit * 100,
            'gs://synthetic/staged',
            100,
            Priority.FRESH,
            timing_store='batch' if unit % 2 == 0 else 'sync',
        )
        stamp_speaker(segment, item, {'words_provider': 'parakeet'}, True, item.segment_id)
        segment.speaker_grouping_shadow = {'owner_link': 'user'}
        if resolved_scopes:
            segment.assign_resolved_speaker(7, 'final:batch:conversation:c1')
    expected = {s.id: dict(s.provider_speaker) for s in conversation.transcript_segments}

    stored = db.encode_conversation_for_write('u1', conversation.model_dump(), level)
    # Rewriting opaque encrypted sidecars must also survive the original capacity limit.
    opaque = db._reveal_json_value(stored['transcript_segments'], 'u1', True)
    assert sum(grouping.FIELD in row for row in opaque) == 3
    assert all('provider_speaker' not in row for row in opaque)
    assert all('timing_store' not in str(row) for row in opaque)
    stored = db.encode_conversation_for_write('u1', {**conversation.model_dump(), 'transcript_segments': opaque}, level)
    stored['data_protection_level'] = level
    restored = Conversation(**db.prepare_conversation_for_read(stored, 'u1'))
    # Also cover a decoded read/write, as in reprocessing or protection migration.
    stored = db.encode_conversation_for_write('u1', restored.model_dump(), level)
    stored['data_protection_level'] = level
    restored = Conversation(**db.prepare_conversation_for_read(stored, 'u1'))
    assert {s.id: s.provider_speaker for s in restored.transcript_segments} == expected
    assert all(s.speaker_grouping_shadow is None for s in restored.transcript_segments)
    assert all('provider_speaker' not in s for s in restored.model_dump(mode='json')['transcript_segments'])

    chunks = [_chunk('a.opus.enc', 100, count), _chunk('b.batch.enc', 100, count, is_batch=True)]
    refused = {s.id: AudioPlacement(None, 'untrusted_clock') for s in restored.transcript_segments}
    proven = _run(monkeypatch, chunks, restored.transcript_segments, refused)
    assert len(proven) == count
    for segment in restored.transcript_segments:
        selected = expected[segment.id]['timing_store']
        assert proven[segment.id] == AudioPlacement((100 + segment.start, 100 + segment.end), selected, store=selected)
    # Full coverage in the other store must never rescue a missing selected store.
    sync_only = _run(monkeypatch, chunks[:1], restored.transcript_segments, refused)
    assert not sync_only  # Without overlapping clocks this helper cannot override refusal.
    chunks[1] = _chunk('b.batch.enc', 100, 1, is_batch=True)
    partial = _run(monkeypatch, chunks, restored.transcript_segments, refused)
    assert all(p.store == 'sync' or p.window[1] <= 101 for p in partial.values())
    assert restored.transcript_segments[-1].id not in partial  # Last unit is stamped batch.


def test_manual_receipt_wins_after_batch_store_resolution(env, batch_stores, monkeypatch):  # noqa: F811
    files, reads, _ = batch_stores
    monkeypatch.setattr(
        stage.conversations_db,
        'get_manual_speaker_receipt',
        lambda *_: {'segments': {'s1': {'is_user': False, 'person_id': 'manual-person'}}},
    )
    conversation = _batch_conversation(files)
    stage.resolve_speakers_for_processing('u1', conversation)
    assert env[1].calls == len(PLAN)
    assert reads and all(path.endswith('.batch.enc') for path in reads)
    assert conversation.speaker_resolution.status == 'resolved'
    assert conversation.transcript_segments[0].is_user
    assert conversation.transcript_segments[3].person_id == 'person'
    manual = conversation.transcript_segments[1]
    assert manual.person_id == 'manual-person' and not manual.is_user
    assert manual.speaker_label_source == 'manual'
