"""Exercise background relocation with synthetic PCM and fake provider/storage."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from config.speaker_clip_location import text_anchored_clips_enabled
from utils import speaker_clip_relocation as relocation

PHRASE = 'amber bronze coral denim emerald fuchsia gold hazel indigo jade khaki lilac'


def entries(start=0):
    return [
        {'text': token, 'timestamp': [start + i, start + i + 0.9], 'speaker': 'SPEAKER_00'}
        for i, token in enumerate(PHRASE.split())
    ]


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(
        chunks=[
            {
                'path': 'chunks/account/conv/1000.bin',
                'timestamp': 1000.0,
                'generation': 1,
                'size': 60 * 16000 * 2,
                'is_batch': False,
            }
        ],
        index={},
        downloads=[],
        calls=[],
        writes=[],
        charges=[],
        outcomes=[],
        released=[],
        pcm=b'\x01\x00' * (60 * 16000),
        reserve=True,
        locked=True,
    )
    monkeypatch.setenv('SPEAKER_TEXT_ANCHORED_CLIPS_ENABLED', 'true')
    monkeypatch.setattr(relocation, 'record_location', state.outcomes.append)
    monkeypatch.setattr(relocation, 'record_fallback', lambda **kw: None)
    monkeypatch.setattr(relocation, 'index_key', lambda *args: 'synthetic-index')
    monkeypatch.setattr(relocation.storage, 'list_audio_chunks', lambda *args, **kwargs: deepcopy(state.chunks))
    monkeypatch.setattr(relocation.cache, 'acquire', lambda *args: state.locked)
    monkeypatch.setattr(relocation.cache, 'release', lambda *args: state.released.append(args))
    monkeypatch.setattr(relocation.cache, 'read_index', lambda *args: deepcopy(state.index))

    def write(uid, key, index):
        state.index = deepcopy(index)
        state.writes.append(deepcopy(index))

    monkeypatch.setattr(relocation.cache, 'write_index', write)

    def reserve(*args, **kwargs):
        state.charges.append(kwargs)
        return state.reserve

    monkeypatch.setattr(relocation.cache, 'reserve', reserve)

    def read(uid, chunk):
        state.downloads.append(chunk)
        return state.pcm

    monkeypatch.setattr(relocation, 'read_source_pcm', read)

    def transcribe(*args):
        state.calls.append(args)
        return entries()

    monkeypatch.setattr(relocation, 'transcribe_source', transcribe)
    monkeypatch.setattr(relocation, 'verify_and_transcribe_sample_in_worker', lambda *args: (PHRASE, True, 'ok'))
    return state


def run():
    return asyncio.run(
        relocation.relocate_person_sample('account', 'conv', [{'id': 'authorized', 'text': PHRASE}], 'en')
    )


def test_flag_defaults_off_and_accepts_only_explicit_true(monkeypatch):
    monkeypatch.delenv('SPEAKER_TEXT_ANCHORED_CLIPS_ENABLED', raising=False)
    assert not text_anchored_clips_enabled()
    monkeypatch.setenv('SPEAKER_TEXT_ANCHORED_CLIPS_ENABLED', '1')
    assert not text_anchored_clips_enabled()
    monkeypatch.setenv('SPEAKER_TEXT_ANCHORED_CLIPS_ENABLED', 'true')
    assert text_anchored_clips_enabled()


def test_relocates_only_after_complete_index_and_verification(world):
    sample = run()
    assert sample.transcript == PHRASE and sample.segment_ids == ['authorized']
    assert len(sample.pcm) >= 10 * 16000 * 2
    assert world.outcomes == ['relocated']
    assert sum(c.get('seconds', 0) for c in world.charges) <= relocation.MAX_LABEL_SECONDS
    assert len(world.calls) == 1 and len(world.downloads) == 1


def test_reuses_index_across_manual_labels_without_retranscription(world):
    assert run() is not None
    assert run() is not None
    assert len(world.calls) == 1 and len(world.downloads) == 2


def test_partial_index_is_retained_but_never_authorizes_a_clip(world):
    world.chunks *= 12
    assert run() is None
    assert world.outcomes == ['budget_exhausted']
    assert world.writes and len(world.index) < len(world.chunks)


def test_index_competitor_in_another_blob_declines(world):
    world.chunks *= 2
    assert run() is None
    assert world.outcomes == ['ambiguous']


def test_quota_rejection_happens_before_download(world):
    world.reserve = False
    assert run() is None and not world.downloads
    assert world.outcomes == ['budget_exhausted']


def test_redis_failure_happens_before_download(world, monkeypatch):
    def unavailable(*args):
        raise ConnectionError()

    monkeypatch.setattr(relocation.cache, 'acquire', unavailable)
    assert run() is None and not world.downloads
    assert world.outcomes == ['cache_unavailable']


def test_batch_is_not_silently_omitted_from_competing_inventory(world):
    world.chunks.append({**world.chunks[0], 'is_batch': True})
    assert run() is None and not world.downloads
    assert world.outcomes == ['unsupported_source']


def test_busy_conversation_does_not_duplicate_work(world):
    world.locked = False
    assert run() is None and not world.downloads
    assert world.outcomes == ['busy'] and not world.released


@pytest.mark.parametrize('reason', ['text_mismatch: containment=0.20', 'multi_speaker: ratio=0.5'])
def test_relocated_clip_keeps_existing_quality_gates(world, monkeypatch, reason):
    monkeypatch.setattr(relocation, 'verify_and_transcribe_sample_in_worker', lambda *args: (PHRASE, False, reason))
    assert run() is None and world.outcomes == ['verification_rejected']


def test_cancellation_releases_lock_and_never_publishes(world, monkeypatch):
    async def cancelled(*args, **kwargs):
        if args[1] is relocation.read_source_pcm:
            raise asyncio.CancelledError()
        return args[1](*args[2:], **kwargs)

    monkeypatch.setattr(relocation, 'run_blocking', cancelled)
    with pytest.raises(asyncio.CancelledError):
        run()
    assert world.outcomes == ['timeout'] and world.released


def test_source_reader_fences_generation_size_timeout_and_pcm_duration(monkeypatch):
    calls = []
    pcm = b'\x01\x00' * (12 * 16000)
    blob = SimpleNamespace(download_as_bytes=lambda **kwargs: calls.append(kwargs) or pcm)
    monkeypatch.setattr(
        relocation.storage, 'get_private_cloud_sync_bucket', lambda: SimpleNamespace(blob=lambda path: blob)
    )
    chunk = {'path': 'synthetic.bin', 'generation': 7, 'size': len(pcm), 'is_batch': False}
    assert relocation.read_source_pcm('account', chunk) == pcm
    assert calls == [{'timeout': 5, 'retry': None, 'if_generation_match': 7}]
    with pytest.raises(ValueError):
        relocation.read_source_pcm('account', {**chunk, 'size': relocation.MAX_SOURCE_BYTES + 1})
    assert len(calls) == 1


@pytest.mark.parametrize('names,limit', [(['1000.bin', 'invalid.bin', '2000.bin'], 129), (['1000.bin', '2000.bin'], 2)])
def test_strict_inventory_never_claims_filtered_or_truncated_listing(monkeypatch, names, limit):
    blobs = [SimpleNamespace(name='chunks/account/conv/' + name, size=20, generation=1, metadata={}) for name in names]
    bucket = SimpleNamespace(list_blobs=lambda **kwargs: iter(blobs[: kwargs['max_results']]))
    monkeypatch.setattr(relocation.storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    with pytest.raises(ValueError):
        relocation.storage.list_audio_chunks('account', 'conv', max_results=limit, timeout=5, require_complete=True)
