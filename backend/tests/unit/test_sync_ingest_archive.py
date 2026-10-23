import asyncio
from contextlib import nullcontext
import ctypes.util
import importlib
import hashlib
import io
import struct
import threading
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import PreconditionFailed
from google.cloud.exceptions import NotFound

from config import audio_archive
from utils.other import storage
from utils.other.audio_singleflight import coalesce_rebuild
from utils.other.live_audio_archive import LiveAudioArchive
from utils.other.raw_audio import CapturePack, WAL_FORMAT, decode_capture, provenance, wal_packets
from utils.other.raw_audio_read import read_pack, verified_pcm_paths
from utils.other.audio_opus import _get_opuslib
from utils.other import audio_opus
from utils import cloud_tasks
from utils.other import audio_singleflight
from utils.other import live_audio_archive


class Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.metadata = {}
        self.data = None
        self.generation = 1
        self.metageneration = 1
        self.server_metadata = None

    @property
    def size(self):
        return len(self.data or b'')

    def upload_from_string(self, data, **kwargs):
        if self.data is not None and kwargs.get('if_generation_match') == 0:
            raise PreconditionFailed('exists')
        self.data = data
        self.server_metadata = dict(self.metadata)

    def reload(self, **kwargs):
        if self.data is None:
            raise NotFound('missing')
        if self.server_metadata is not None:
            self.metadata = dict(self.server_metadata)
        return None

    def download_as_bytes(self, **kwargs):
        if self.data is None:
            raise NotFound('missing')
        return self.data

    def delete(self):
        self.bucket.blobs.pop(self.name)

    def patch(self, **kwargs):
        assert kwargs['if_metageneration_match'] == self.metageneration
        self.server_metadata = dict(self.metadata)
        self.metageneration += 1

    def exists(self):
        return self.data is not None

    def open(self, *args, **kwargs):
        blob = self

        class Upload(io.BytesIO):
            def close(self):
                blob.data = self.getvalue()
                blob.server_metadata = dict(blob.metadata)
                super().close()

        return Upload()


class Bucket:
    def __init__(self, name):
        self.name, self.blobs = name, {}

    def blob(self, name):
        return self.blobs.setdefault(name, Blob(self, name))

    def list_blobs(self, prefix, **kwargs):
        return [blob for name, blob in self.blobs.items() if name.startswith(prefix) and blob.data is not None]


@pytest.fixture
def buckets(monkeypatch):
    result = {'canonical': Bucket('canonical'), 'regional': Bucket('regional'), 'staging': Bucket('staging')}
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: result[name]))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'canonical')
    monkeypatch.setattr(storage, 'syncing_local_bucket', 'staging')
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    return result


def enable(monkeypatch, phase):
    monkeypatch.setenv(f'AUDIO_ARCHIVE_{phase}_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_UID_ALLOWLIST', 'owner')


@pytest.fixture
def native_opus(monkeypatch):
    # macOS protected Git/bash processes strip DYLD_* before hooks run. Resolve
    # the actually installed library in Python rather than skipping real replay.
    if audio_opus.opuslib is None and sys.platform == 'darwin':
        candidates = (Path('/opt/homebrew/lib/libopus.dylib'), Path('/usr/local/lib/libopus.dylib'))
        installed = next((path for path in candidates if path.is_file()), None)
        if installed is not None:
            original = ctypes.util.find_library
            monkeypatch.setattr(
                ctypes.util, 'find_library', lambda name: str(installed) if name == 'opus' else original(name)
            )
            monkeypatch.setattr(audio_opus, 'opuslib', importlib.import_module('opuslib'))
    return _get_opuslib()


@pytest.mark.parametrize('percent', ['nan', 'inf', '-1', '101', 'garbage'])
def test_invalid_cohort_fails_closed(monkeypatch, percent):
    enable(monkeypatch, 'SYNC')
    monkeypatch.setenv('AUDIO_ARCHIVE_PERCENT', percent)
    assert not audio_archive.admitted('owner', 'SYNC')
    enable(monkeypatch, 'STOP_PCM')
    monkeypatch.setenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', percent)
    assert not audio_archive.admitted('owner', 'STOP_PCM')


def test_fleet_phases_ignore_the_shared_cohort_percent(monkeypatch):
    enable(monkeypatch, 'LIVE')
    enable(monkeypatch, 'READ')
    monkeypatch.setenv('AUDIO_ARCHIVE_PERCENT', 'garbage')
    # LIVE/READ are flag-only fleet phases: an invalid shared cohort percent
    # must not disable the as-captured dual-write anywhere.
    assert audio_archive.admitted('owner', 'LIVE')
    assert audio_archive.admitted('owner', 'READ')


def test_flags_default_on_for_fleet_phases_and_off_for_staged(monkeypatch):
    for var in ('AUDIO_ARCHIVE_LIVE_ENABLED', 'AUDIO_ARCHIVE_READ_ENABLED', 'AUDIO_ARCHIVE_STOP_PCM_ENABLED'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv('AUDIO_ARCHIVE_UID_ALLOWLIST', raising=False)
    monkeypatch.delenv('AUDIO_ARCHIVE_PERCENT', raising=False)
    monkeypatch.delenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', raising=False)
    # P71 2026-10-22 ruling: the raw Opus dual-write and read preference are
    # default-on for everyone, without a percent cohort.
    assert audio_archive.admitted('owner', 'LIVE')
    assert audio_archive.admitted('other', 'READ')
    # Staged phases stay default-off.
    for phase in ('STOP_PCM', 'SYNC', 'REGIONAL_CACHE', 'COALESCE'):
        monkeypatch.delenv(f'AUDIO_ARCHIVE_{phase}_ENABLED', raising=False)
        assert not audio_archive.admitted('owner', phase)
    # Kill switches.
    monkeypatch.setenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'false')
    monkeypatch.setenv('AUDIO_ARCHIVE_READ_ENABLED', 'false')
    assert not audio_archive.admitted('owner', 'LIVE')
    assert not audio_archive.admitted('owner', 'READ')


def test_stop_pcm_ramps_on_its_own_percent_not_the_shared_one(monkeypatch):
    enable(monkeypatch, 'STOP_PCM')
    monkeypatch.delenv('AUDIO_ARCHIVE_UID_ALLOWLIST', raising=False)
    # The shared percent is pinned at 100 fleet-wide for COALESCE; that must
    # never expose STOP_PCM while its own ramp percent is 0.
    monkeypatch.setenv('AUDIO_ARCHIVE_PERCENT', '100')
    monkeypatch.setenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', '0')
    assert not audio_archive.admitted('owner', 'STOP_PCM')
    assert not audio_archive.admitted('other', 'STOP_PCM')
    monkeypatch.setenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', '100')
    assert audio_archive.admitted('owner', 'STOP_PCM')
    assert audio_archive.admitted('other', 'STOP_PCM')
    # Cohort stability: the same uid keeps its admission across calls.
    monkeypatch.setenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', '50')
    first = audio_archive.admitted('owner', 'STOP_PCM')
    assert audio_archive.admitted('owner', 'STOP_PCM') == first


@pytest.mark.parametrize('encrypted', [False, True])
def test_shared_writer_byte_exact_and_immutable(monkeypatch, buckets, encrypted):
    raw = struct.pack('<I', 3) + b'abc'
    monkeypatch.setattr(
        storage.users_db, 'get_data_protection_level', lambda uid: 'enhanced' if encrypted else 'standard'
    )
    monkeypatch.setattr(storage.encryption, 'encrypt_audio_chunk', lambda raw, uid: b'encrypted:' + raw)
    path = storage.archive_capture_bytes(
        'owner', raw, 'raw-live', 'conversation/1', {'codec': 'opus', 'format': WAL_FORMAT}
    )
    blob = buckets['canonical'].blob(path)
    assert blob.data == (b'encrypted:' + raw if encrypted else raw)
    assert blob.metadata['sha256'] == hashlib.sha256(raw).hexdigest()
    assert set(provenance(raw, {})) <= set(blob.metadata)
    original = blob.data
    storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/1', {'codec': 'opus', 'format': WAL_FORMAT})
    assert blob.data == original
    assert not buckets['regional'].blobs


def test_offline_original_archived_before_decode(monkeypatch, buckets, tmp_path):
    enable(monkeypatch, 'SYNC')
    audio = tmp_path / 'audio_omi_opus_16000_1_fs160_1000.bin'
    # Even undecodable intake is preserved; archival never decodes or drops silence.
    audio.write_bytes(b'original-invalid-encoded-file')
    storage.archive_mobile_batch_raw_files('owner', [str(audio)])
    blob = next(iter(buckets['canonical'].blobs.values()))
    assert blob.data == audio.read_bytes()
    assert blob.name.startswith('raw-sync/owner/')
    assert blob.metadata['frame_size'] == '160'


def test_sync_off_does_not_gain_persistent_archive(monkeypatch, buckets, tmp_path):
    enable(monkeypatch, 'SYNC')
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    storage.archive_mobile_batch_raw_files('owner', [str(tmp_path / 'audio_omi_opus_16000_1_fs160_1000.bin')])
    assert not buckets['canonical'].blobs


def test_mobile_filename_cannot_claim_storage_consent(monkeypatch, buckets, tmp_path):
    monkeypatch.setattr(storage.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    path = tmp_path / 'audio_omimobilebatch001_opus_16000_1_fs160_1000.bin'
    assert storage.archive_mobile_batch_raw_files('owner', [str(path)]) == []
    assert not buckets['canonical'].blobs


def test_completed_job_links_archived_original_without_rewrite(monkeypatch, buckets, tmp_path):
    enable(monkeypatch, 'SYNC')
    audio = tmp_path / 'audio_omi_opus_16000_1_fs160_1000.bin'
    audio.write_bytes(b'original')
    paths = storage.archive_mobile_batch_raw_files('owner', [str(audio)])
    blob = buckets['canonical'].blob(paths[0])
    original = blob.data
    storage.link_archive_captures('owner', paths, ['conversation-one'])
    storage.link_archive_captures('owner', paths, ['conversation-two'])
    assert blob.metadata['conversation_id'] == 'multiple'
    assert blob.data == original
    assert blob.metadata['sha256'] == hashlib.sha256(original).hexdigest()
    # A byte-identical archive retry never erases completed linkage.
    storage.archive_mobile_batch_raw_files('owner', [str(audio)])
    assert 'conversation-two' in blob.metadata['conversation_ids']
    with pytest.raises(ValueError, match='owner'):
        storage.link_archive_captures('other', paths, ['conversation-one'])


@pytest.mark.parametrize('raw', [b'\x01', struct.pack('<I', 0), struct.pack('<I', 9) + b'x'])
def test_bad_wal_is_rejected_by_reader(raw):
    with pytest.raises(ValueError):
        list(wal_packets(raw))


def test_hour_conversation_and_size_boundaries_preserve_packets():
    pack = CapturePack('opus', 16000)
    pack.append(b'packet-one', 'conversation', 3599.99, 160)
    assert pack.boundary('conversation', 3600, 10)
    assert pack.boundary('other', 3599.995, 10)
    raw, metadata = pack.encoded()
    assert list(wal_packets(raw)) == [b'packet-one']
    assert metadata['sequence_count'] == 1
    assert metadata['gap_count'] == 0


def test_flac_round_trip_preserves_pcm_samples():
    pcm = struct.pack('<h', 1234) * 160
    pack = CapturePack('pcm16', 16000)
    pack.append(pcm, 'conversation', 1000, 160)
    raw, metadata = pack.encoded()
    assert raw.startswith(b'fLaC')
    assert decode_capture(raw, {key: str(value) for key, value in metadata.items()}) == pcm


def test_opus_replay_is_packet_exact_and_sample_exact(buckets, native_opus):
    opus = native_opus
    encoder = opus.Encoder(16000, 1, opus.APPLICATION_VOIP)
    decoder = opus.Decoder(16000, 1)
    pack = CapturePack('opus', 16000)
    packets, decoded = [], []
    cursor = 1000.0
    for samples in (160, 320, 640):
        packet = encoder.encode(struct.pack('<h', 1234) * samples, samples)
        packets.append(packet)
        decoded.append(decoder.decode(packet, 1920))
        pack.append(packet, 'conversation', cursor, samples)
        cursor += samples / 16000
    raw, metadata = pack.encoded()
    path = storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/0/0', metadata)
    assert list(wal_packets(buckets['canonical'].blob(path).data)) == packets
    assert read_pack(buckets['canonical'], path, 'owner') == b''.join(decoded)


def test_stateful_opus_boundary_retirement_uses_capture_identity(buckets, native_opus):
    opus = native_opus
    encoder = opus.Encoder(16000, 1, opus.APPLICATION_VOIP)
    decoder = opus.Decoder(16000, 1)
    first = encoder.encode(struct.pack('<h', 1234) * 160, 160)
    decoder.decode(first, 1920)
    second = encoder.encode(struct.pack('<h', 4321) * 160, 160)
    pcm = decoder.decode(second, 1920)
    pack = CapturePack('opus', 16000)
    pack.append(second, 'conversation', 1000, 160, decoded=pcm)
    raw, metadata = pack.encoded()
    path = storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/0/0/1000', metadata)
    chunk = {'timestamp': 1000, 'data': pcm, 'span': {'sample_rate': 16000, 'samples': 160}}
    assert verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [chunk], 16000) == [path]
    wrong = {**chunk, 'data': b'\x00\x00' * 160}
    assert verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [wrong], 16000) is None


@pytest.mark.asyncio
async def test_retirement_parts_commit_before_minute_pcm_flush(monkeypatch, buckets):
    for phase in ('LIVE', 'READ', 'STOP_PCM'):
        enable(monkeypatch, phase)
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}),
        ),
    )
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    # Collector seam: the decoder has already supplied each run's PCM.
    await archive.append(b'first-run', 'conversation', 1000, 480000, decoded=b'\x00\x00' * 480000)
    assert not buckets['canonical'].blobs
    await archive.append(b'second-run', 'conversation', 1030, 480000, decoded=b'\x00\x00' * 480000)
    assert archive.inflight  # no GCS wait in the receive loop
    await archive.close()
    blob = next(iter(buckets['canonical'].blobs.values()))
    assert blob.metadata['pcm_sha256'] == hashlib.sha256(b'\x00\x00' * 960000).hexdigest()
    assert not archive.packs


async def test_live_admission_is_session_stable_across_cohort_cache_expiry(monkeypatch):
    """A TTL miss mid-connection must not drop archive packets (Codex P2)."""
    calls = {'LIVE': 0}

    def flapping(uid, phase):
        if phase != 'LIVE':
            return False
        # First evaluation admits; later evaluations would consult an expired
        # cache entry and miss until the refresh completes.
        calls['LIVE'] += 1
        return calls['LIVE'] == 1

    monkeypatch.setattr('utils.other.live_audio_archive.admitted', flapping)
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}),
        ),
    )
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    await archive.append(b'run', 'conversation', 1000, 480000, decoded=b'\x00\x00' * 480000)
    await archive.append(b'run', 'conversation', 1030, 480000, decoded=b'\x00\x00' * 480000)
    await archive.close()
    # Exactly one LIVE evaluation per connection, taken while warm.
    assert calls['LIVE'] == 1
    assert not archive.packs


def test_merge_worker_cohort_and_rollback_keep_pending_audience(monkeypatch):
    enable(monkeypatch, 'SEPARATE_MERGE')
    monkeypatch.setenv('AUDIO_MERGE_HANDLER_URL', 'https://sync.example/v2/audio-merge-jobs/run')
    monkeypatch.setenv('AUDIO_MERGE_WORKER_URL', 'https://merge.example/v2/audio-merge-jobs/run')
    assert cloud_tasks._audio_merge_handler_url('owner').startswith('https://merge.example')
    assert cloud_tasks._audio_merge_handler_url('other').startswith('https://sync.example')
    monkeypatch.setenv('AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED', 'false')
    assert cloud_tasks._audio_merge_handler_url('owner').startswith('https://sync.example')
    observed = []
    monkeypatch.setattr(
        cloud_tasks, 'verify_configured_cloud_tasks_oidc', lambda request, **kwargs: observed.append(kwargs) or 0
    )
    cloud_tasks.verify_audio_merge_cloud_tasks_oidc(SimpleNamespace())
    assert observed[0]['audience'] == [
        'https://sync.example/v2/audio-merge-jobs/run',
        'https://merge.example/v2/audio-merge-jobs/run',
    ]


@pytest.mark.asyncio
async def test_live_pack_tail_and_metadata(monkeypatch, buckets):
    enable(monkeypatch, 'LIVE')
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=SimpleNamespace(app_version='1.2'),
            websocket=SimpleNamespace(headers={'x-omi-firmware-version': '2.0'}),
        ),
    )
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    await archive.append(b'unchanged-packet', 'conversation', 1000, 160)
    await archive.close()
    blob = next(iter(buckets['canonical'].blobs.values()))
    assert list(wal_packets(blob.data)) == [b'unchanged-packet']
    assert blob.metadata['firmware'] == '2.0'
    assert blob.metadata['app_version'] == '1.2'
    assert not archive.packs


@pytest.mark.asyncio
async def test_live_kill_switch_writes_nothing_despite_consent(monkeypatch, buckets):
    monkeypatch.setenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'false')
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}),
        ),
    )
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    await archive.append(b'unchanged-packet', 'conversation', 1000, 160)
    await archive.close()
    assert not buckets['canonical'].blobs
    assert not archive.packs


@pytest.mark.asyncio
async def test_identical_silence_at_different_times_is_not_deduplicated(monkeypatch, buckets):
    enable(monkeypatch, 'LIVE')
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}),
        ),
    )
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    for timestamp in (1000, 1060):
        await archive.append(b'identical-silence', 'conversation', timestamp, 160)
        await archive.close()
    blobs = list(buckets['canonical'].blobs.values())
    assert len(blobs) == 2
    assert blobs[0].data == blobs[1].data
    assert blobs[0].metadata['capture_start'] != blobs[1].metadata['capture_start']


def test_enhanced_capture_read_verifies_plaintext(monkeypatch, buckets):
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'enhanced')
    pack = CapturePack('pcm16', 16000)
    pcm = b'\x01\x00' * 160
    pack.append(pcm, 'conversation', 1000, 160)
    raw, metadata = pack.encoded()
    path = storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/0/0/1000', metadata)
    assert buckets['canonical'].blob(path).data != raw
    assert read_pack(buckets['canonical'], path, 'owner') == pcm


@pytest.mark.asyncio
async def test_archive_failure_retains_pcm_path(monkeypatch, buckets):
    for phase in ('LIVE', 'READ', 'STOP_PCM'):
        enable(monkeypatch, phase)
    host = SimpleNamespace(
        private_cloud_sync_enabled=True,
        request=SimpleNamespace(
            uid='owner',
            codec='opus',
            sample_rate=16000,
            source='omi',
            client_device_context=None,
            websocket=SimpleNamespace(headers={}),
        ),
    )

    def unavailable(*args, **kwargs):
        raise OSError('archive unavailable')

    monkeypatch.setattr(live_audio_archive, 'archive_capture_bytes', unavailable)
    host.spawn = lambda coroutine, **kwargs: asyncio.create_task(coroutine)
    archive = LiveAudioArchive(host)
    await archive.append(b'unchanged-packet', 'conversation', 1000, 160)
    await archive.close()
    assert archive.failed and not archive.packs
    chunk = {'timestamp': 1000, 'data': b'\x01\x00' * 160, 'span': {'sample_rate': 16000, 'samples': 160}}
    paths = storage.upload_audio_chunks_batch([chunk], 'owner', 'conversation', sample_rate=16000)
    assert paths[0].startswith('chunks/owner/conversation/')
    assert buckets['canonical'].blob(paths[0]).data == chunk['data']


def test_pcm_retirement_requires_whole_byte_identical_coverage(monkeypatch, buckets):
    pcm = b'\x00\x01' * 160
    pack = CapturePack('pcm16', 16000)
    pack.append(pcm, 'conversation', 1000, 160)
    raw, metadata = pack.encoded()
    path = storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/0/0', metadata)
    chunk = {'timestamp': 1000, 'data': pcm, 'span': {'sample_rate': 16000, 'samples': 160}}
    assert verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [chunk], 16000) == [path]
    assert (
        verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [{**chunk, 'data': b'\x01\x01' * 160}], 16000)
        is None
    )
    assert (
        verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [{**chunk, 'timestamp': 999}], 16000) is None
    )
    assert verified_pcm_paths(buckets['canonical'], 'owner', 'conversation', [chunk], 8000) is None
    enable(monkeypatch, 'STOP_PCM')
    enable(monkeypatch, 'READ')
    assert storage.upload_audio_chunks_batch([chunk], 'owner', 'conversation', sample_rate=16000) == [path]
    assert not any(name.startswith('chunks/') for name in buckets['canonical'].blobs)
    # Rolling writes back preserves committed raw reads; READ stays on after phase C.
    monkeypatch.setenv('AUDIO_ARCHIVE_STOP_PCM_ENABLED', 'false')
    chunks = storage.list_audio_chunks('owner', 'conversation')
    assert len(chunks) == 1
    assert storage.download_audio_chunks_and_merge('owner', 'conversation', [1000]) == pcm
    blob = buckets['canonical'].blob(path)
    blob.data = b'corrupt'
    with pytest.raises(ValueError, match='checksum'):
        read_pack(buckets['canonical'], path, 'owner')


def test_sync_rendition_uses_regional_and_remains_readable_after_rollback(monkeypatch, buckets):
    enable(monkeypatch, 'SYNC')
    enable(monkeypatch, 'REGIONAL_CACHE')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'regional')
    monkeypatch.setattr(storage, 'encode_pcm_to_opus', lambda data: b'derived-opus')
    monkeypatch.setattr(storage, 'decode_opus_to_pcm', lambda data, **kwargs: b'\x01\x00' * 160)
    path = storage.upload_audio_chunk(b'\x01\x00' * 160, 'owner', 'conversation', 1000, 'standard')
    assert not buckets['canonical'].blobs
    assert buckets['regional'].blob(path).metadata['canonical'] == 'false'
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'false')
    chunks = storage.list_audio_chunks('owner', 'conversation')
    assert chunks[0]['bucket'] == 'regional'
    assert storage.download_audio_chunks_and_merge('owner', 'conversation', [1000]) == b'\x01\x00' * 160


def test_purge_enumerates_noncurrent_generations(monkeypatch):
    generations = {1, 2}
    listing = []

    class Generation:
        def __init__(self, value):
            self.value = value

        def delete(self):
            generations.remove(self.value)

    def list_blobs(**kwargs):
        listing.append(kwargs)
        assert kwargs['versions'] is True
        return [Generation(value) for value in generations]

    monkeypatch.setattr(storage, '_uses_real_gcs_bucket', lambda bucket: True)
    assert storage._delete_owner_bucket_prefix(SimpleNamespace(list_blobs=list_blobs), 'raw-live/owner/') == 2
    assert not generations
    assert len(listing) == 2


def test_regional_route_is_explicit_and_purge_covers_both_buckets(monkeypatch, buckets):
    enable(monkeypatch, 'REGIONAL_CACHE')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    assert audio_archive.regional_bucket('owner', 'canonical') == 'canonical'
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'regional')
    assert audio_archive.regional_bucket('owner', 'canonical') == 'regional'
    assert audio_archive.regional_bucket('other', 'canonical') == 'canonical'
    for prefix in ('raw-live', 'raw-sync', 'raw-mobile-batch'):
        buckets['canonical'].blob(f'{prefix}/owner/a').data = b'raw'
    for prefix in ('playback', 'merged', 'syncing', 'chunks'):
        buckets['regional'].blob(f'{prefix}/owner/a').data = b'derived'
    buckets['regional'].blob('playback/other/keep').data = b'keep'
    monkeypatch.setattr(storage, 'speech_profiles_bucket', None)
    monkeypatch.setattr(storage, 'chat_files_bucket', None)
    monkeypatch.setenv('OMI_ENV_STAGE', 'test')
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    assert storage.delete_all_user_storage_objects('owner') == 7
    assert not buckets['canonical'].blobs
    assert set(buckets['regional'].blobs) == {'playback/other/keep'}


def test_rebuild_singleflight_shares_result_and_retries_failure(monkeypatch):
    enable(monkeypatch, 'COALESCE')
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    calls = []

    class ObservedFuture(audio_singleflight.Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout)

    monkeypatch.setattr(audio_singleflight, 'Future', ObservedFuture)

    @coalesce_rebuild
    def rebuild(uid, conversation_id):
        calls.append(conversation_id)
        entered.set()
        assert release.wait(2)
        return b'playback'

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(rebuild, 'owner', 'conversation')
        assert entered.wait(2)
        second = pool.submit(rebuild, 'owner', 'conversation')
        assert waiting.wait(2)
        release.set()
        assert first.result() == second.result() == b'playback'
    assert len(calls) == 1

    @coalesce_rebuild
    def failed(uid, conversation_id):
        raise OSError('retryable')

    for _ in range(2):
        with pytest.raises(OSError):
            failed('owner', 'conversation')


def test_flags_off_listing_matches_main_and_never_lists_raw(monkeypatch, buckets):
    monkeypatch.setenv('AUDIO_ARCHIVE_READ_ENABLED', 'false')
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    path = 'chunks/owner/conversation/1000.000.opus'
    buckets['canonical'].blob(path).data = b'pcm'

    def forbidden(*args):
        raise AssertionError('flags-off must not list raw')

    monkeypatch.setattr(storage, 'list_packs', forbidden)
    expected = [{'timestamp': 1000.0, 'path': path, 'size': 3, 'is_batch': False, 'generation': 1}]
    assert storage.list_audio_chunks('owner', 'conversation') == expected
    enable(monkeypatch, 'READ')
    assert storage.list_audio_chunks('owner', 'conversation') == expected


def test_raw_playback_requires_read_phase(monkeypatch, buckets):
    monkeypatch.setenv('AUDIO_ARCHIVE_READ_ENABLED', 'false')

    def forbidden(*args):
        raise AssertionError('flags-off must not decode raw')

    monkeypatch.setattr(storage, 'read_pack', forbidden)
    assert storage.download_and_decode_chunk_blob(buckets['canonical'], 'raw-live/owner/c/a', 'owner', 16000) is None


def test_missing_merge_worker_retains_current_handler(monkeypatch):
    enable(monkeypatch, 'SEPARATE_MERGE')
    monkeypatch.delenv('AUDIO_MERGE_WORKER_URL', raising=False)
    monkeypatch.setenv('AUDIO_MERGE_HANDLER_URL', 'https://legacy/run')
    assert cloud_tasks._audio_merge_handler_url('owner') == 'https://legacy/run'


def test_conversation_purge_covers_raw_links_and_regional_objects(monkeypatch, buckets):
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'regional')
    for name in ('canonical', 'regional'):
        for prefix in ('chunks', 'audio', 'merged', 'playback', 'raw-live'):
            buckets[name].blob(f'{prefix}/owner/conversation/a').data = b'audio'
            buckets[name].blob(f'{prefix}/owner/other/a').data = b'keep'
    for prefix in ('raw-sync', 'raw-mobile-batch'):
        blob = buckets['canonical'].blob(f'{prefix}/owner/original')
        blob.data = b'original'
        blob.metadata = {'conversation_ids': '["conversation", "shared"]'}
        keep = buckets['canonical'].blob(f'{prefix}/owner/keep')
        keep.data = b'keep'
        keep.metadata = {'conversation_ids': '["other"]'}
    storage.delete_conversation_audio_files('owner', 'conversation')
    for bucket in buckets.values():
        assert all('/conversation/' not in path and not path.endswith('/original') for path in bucket.blobs)
    assert len(buckets['canonical'].blobs) == 7
    assert len(buckets['regional'].blobs) == 5


@pytest.mark.parametrize('link_fails', [False, True])
def test_merged_into_links_owner_packs_before_raw_and_derived_cleanup(monkeypatch, buckets, link_fails):
    monkeypatch.setenv('BUCKET_CANONICAL_AUDIO', 'forward')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'regional')
    forward = object()
    monkeypatch.setattr(storage, 'get_canonical_audio_bucket', lambda: forward)
    monkeypatch.setattr(storage, 'destructive_operation_gate', lambda *args, **kwargs: nullcontext())
    raw = buckets['canonical'].blob('raw-live/owner/source/a')
    raw.data = b'original'
    cache = buckets['regional'].blob('playback/owner/source/a')
    cache.data = b'rendition'

    def link(bucket, uid, sources, target):
        assert (bucket, uid, sources, target) == (forward, 'owner', ['source'], 'target')
        assert raw.data == b'original' and cache.data == b'rendition'
        if link_fails:
            raise RuntimeError('link unavailable')

    monkeypatch.setattr(storage.audio_packs, 'link_conversations', link)
    if link_fails:
        with pytest.raises(RuntimeError, match='link unavailable'):
            storage.delete_conversation_audio_files('owner', 'source', merged_into='target')
        assert raw.name in buckets['canonical'].blobs and cache.name in buckets['regional'].blobs
    else:
        storage.delete_conversation_audio_files('owner', 'source', merged_into='target')
        assert not buckets['canonical'].blobs and not buckets['regional'].blobs


def test_retired_pcm_still_reaches_optional_owner_pack_archive(monkeypatch, buckets):
    pcm = b'\x01\x00' * 160
    pack = CapturePack('pcm16', 16000)
    pack.append(pcm, 'conversation', 1000, 160)
    raw, metadata = pack.encoded()
    path = storage.archive_capture_bytes('owner', raw, 'raw-live', 'conversation/0/a', metadata)
    enable(monkeypatch, 'READ')
    enable(monkeypatch, 'STOP_PCM')
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    monkeypatch.setattr(storage.conversation_tombstones, 'is_deleted', lambda *args: False)
    forward = object()
    monkeypatch.setattr(storage, 'get_canonical_audio_bucket', lambda: forward)
    seen = []
    monkeypatch.setattr(storage.audio_packs, 'archive_capture', lambda *args, **kwargs: seen.append(args))
    chunk = {'timestamp': 1000, 'data': pcm, 'span': {'sample_rate': 16000, 'samples': 160}}
    assert storage.upload_audio_chunks_batch([chunk], 'owner', 'conversation', sample_rate=16000) == [path]
    assert seen == [(forward, 'owner', pcm)]
    assert not any(name.startswith('chunks/') for name in buckets['canonical'].blobs)
