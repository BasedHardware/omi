"""Gapped, unframed raw-live packs: listing, decode, proof spans, kill switch.

The fixtures reproduce the production object shape the writer emits when
``AUDIO_CUSTODY_FRAMED_PERCENT`` is off: an omi-wal opus pack with a nonzero
``gap_count``, no ``frame_schema``, and a custody manifest beside the media.
No real audio is used; every frame is a synthetic tone.
"""

import ctypes
import ctypes.util
import hashlib
import importlib
import json
import struct
import sys
import wave
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from utils.batch_pipeline import live, source_audio
from utils.batch_pipeline.artifacts import ArtifactStore, ProtectionContext
from utils.other import audio_frame_table, audio_opus, raw_audio_read, storage
from utils.other.audio_frame_table import FRAME_SCHEMA
from utils.other.audio_outbox import commit_capture, commit_pcm_window
from utils.other.raw_audio import CapturePack, _get_opuslib
from utils.batch_pipeline import record_orphan_repair as repair
from tests.unit.test_batch_pipeline_invalid_manifest_hold import serve
from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from tests.unit.test_audio_durable_outbox import remote  # noqa: F401

UID, CID = 'owner', 'conversation'
RATE = 16000
NAME = f'{CID}/0/0/session/0'


@pytest.fixture
def native_opus(monkeypatch):
    # macOS protected Git/bash processes strip DYLD_* before hooks run. Resolve
    # the actually installed library in Python rather than skipping real decode.
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


def tone(samples, value):
    return struct.pack(f'<{samples}h', *([value] * samples))


def encode(pcm):
    encoder = _get_opuslib().Encoder(RATE, 1, _get_opuslib().APPLICATION_VOIP)
    return encoder.encode(pcm, len(pcm) // 2)


def build_pack(remote, frames, *, protection='standard'):
    """Commit one pack exactly as the live writer does without a frame schema."""
    pack = CapturePack('opus', RATE, 1)
    table = []
    for index, (start, pcm) in enumerate(frames):
        packet = encode(pcm) if pcm else b'\xff\xff\xff'
        previous_end = pack.end
        offset = len(pack.data)
        pack.append(packet, CID, start, len(pcm) // 2, pcm or None)
        table.append(
            {
                'sequence': index,
                'byte_offset': offset,
                'bytes': len(pack.data) - offset,
                'start': start,
                'samples': len(pcm) // 2,
                'gap_before': previous_end is not None and abs(start - previous_end) > 0.002,
                'sha256': hashlib.sha256(packet).hexdigest(),
            }
        )
    raw, metadata = pack.encoded(preserve_pcm=True)
    metadata.update(
        firmware='synthetic',
        frame_size='variable',
        capture_sha256=hashlib.sha256(bytes(pack.data)).hexdigest(),
        app_version='synthetic',
        device_model='synthetic',
        consent_state='private_cloud_sync_enabled',
        consent_version='1',
        consent_scope='cloud_audio_storage',
        training_consent_state='unknown',
        channel_index=0,
        capture_session_id='session',
        clock_source='server_projected',
        gap_domain='server_projected_sample_clock',
        source_layout='mono',
    )
    receipt = commit_capture(UID, raw, NAME, metadata, table, data_protection_level=protection)
    return receipt, table, raw, [encode(pcm) if pcm else b'\xff\xff\xff' for _, pcm in frames]


def decode_packets(packets):
    """The decoder's own rendition of the captured packets, in capture order."""
    decoder = _get_opuslib().Decoder(RATE, 1)
    return b''.join(decoder.decode(packet, RATE * 120 // 1000) for packet in packets if packet != b'\xff\xff\xff')


def client(remote):
    return SimpleNamespace(bucket=lambda name: remote)


def wire(remote, monkeypatch):
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', remote.name)
    monkeypatch.setattr(live, 'private_cloud_sync_bucket', remote.name)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.delenv('RAW_LIVE_GAPPED_PACKS_ENABLED', raising=False)


def gapped_frames():
    """Two contiguous 20 ms frames, a 3 s capture gap, then one more frame."""
    return [(1000.0, tone(320, 1)), (1000.02, tone(320, 2)), (1003.02, tone(160, 3))]


def test_gapped_unframed_pack_matches_the_production_object_shape(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, table, _, packets = build_pack(remote, gapped_frames())
    metadata = remote.blob(receipt.path).metadata
    assert metadata['codec'] == 'opus'
    assert metadata['format'] == 'omi-wal-uint32le-opus-v1'
    assert metadata['custody_schema'] == 'audio_custody_v1'
    assert metadata['gap_count'] == '1'
    assert 'frame_schema' not in metadata
    assert 'custody_manifest_path' not in metadata
    assert metadata['capture_start'] == '1000.0'
    assert metadata['capture_end'] == '1003.03'
    assert metadata['pcm_sha256'] == hashlib.sha256(tone(320, 1) + tone(320, 2) + tone(160, 3)).hexdigest()
    assert [row['gap_before'] for row in table] == [False, False, True]


def test_listing_keeps_every_real_gap_and_its_true_position(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, packets = build_pack(remote, gapped_frames())
    packs = raw_audio_read.list_packs(remote, UID, CID)
    assert [(p['timestamp'], p['span']['samples'], p['raw_offset_samples']) for p in packs] == [
        (1000.0, 640, 0),
        (1003.02, 160, 640),
    ]
    assert {p['path'] for p in packs} == {receipt.path}
    assert [p['raw_end'] for p in packs] == [1000.04, 1003.03]


@pytest.mark.parametrize('change', ['unchanged', 'generation', 'metadata', 'unversioned', 'deleted', 'media_changed'])
@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_inventory_manifest_body_reuse_checks_the_current_object(remote, monkeypatch, native_opus, change, protection):
    wire(remote, monkeypatch)
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', remote.name)
    monkeypatch.delenv('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED', raising=False)
    monkeypatch.delenv('PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED', raising=False)
    monkeypatch.setattr(audio_frame_table, '_inventory_bodies', {})
    receipt, _, _, _ = build_pack(remote, gapped_frames(), protection=protection)
    manifest = remote.blob(receipt.manifest_path)
    decrypt = Mock(wraps=audio_frame_table.encryption.decrypt_audio_file)
    monkeypatch.setattr(audio_frame_table.encryption, 'decrypt_audio_file', decrypt)
    manifest.metageneration = None if change == 'unversioned' else 1
    manifest.reload = Mock(wraps=manifest.reload)
    manifest.download_as_bytes = Mock(wraps=manifest.download_as_bytes)

    def inventory(**kwargs):
        raw_audio_read.invalidate_pack_index(remote, UID, CID)
        return raw_audio_read.list_packs(remote, UID, CID, reuse_manifest_bodies=True, **kwargs)

    first = inventory()
    assert len(first) == 2
    if change == 'generation':
        manifest.generation += 1
    elif change == 'metadata':
        manifest.metageneration += 1
    elif change == 'deleted':
        manifest.reload.side_effect = NotFound('deleted after listing')
    elif change == 'media_changed':
        remote.blob(receipt.path).generation += 1

    assert inventory() == ([] if change in {'deleted', 'media_changed'} else first)
    warm = change in {'unchanged', 'deleted', 'media_changed'}
    assert manifest.reload.call_count == (2 if change == 'unversioned' else int(warm))
    if warm:
        assert manifest.reload.call_args.kwargs['if_generation_match'] == manifest.generation
        assert manifest.reload.call_args.kwargs['if_metageneration_match'] == manifest.metageneration
    expected_reads = 1 if change in {'unchanged', 'deleted', 'media_changed'} else 2
    assert manifest.download_as_bytes.call_count == expected_reads
    if change == 'unchanged' and protection == 'enhanced':
        assert manifest.metadata['encrypted'] == 'true'
        assert b'"schema"' not in manifest.data
        assert decrypt.call_count == 2
    if change == 'unversioned':
        assert 'if_metageneration_match' not in manifest.download_as_bytes.call_args.kwargs
    else:
        assert manifest.download_as_bytes.call_args.kwargs['if_metageneration_match'] == manifest.metageneration


@pytest.mark.parametrize(
    'mode', ['fresh', 'strict', 'disabled', 'not_inventory', 'listed_disabled', 'cold_race', 'warm_race']
)
def test_gapped_manifest_body_bypass_and_version_race(remote, monkeypatch, native_opus, mode):
    wire(remote, monkeypatch)
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', remote.name)
    monkeypatch.delenv('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED', raising=False)
    monkeypatch.delenv('PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED', raising=False)
    monkeypatch.setattr(audio_frame_table, '_inventory_bodies', {})
    receipt, _, _, _ = build_pack(remote, gapped_frames())
    manifest = remote.blob(receipt.manifest_path)
    manifest.metageneration = 1
    manifest.download_as_bytes = Mock(wraps=manifest.download_as_bytes)
    expected = raw_audio_read.list_packs(remote, UID, CID, reuse_manifest_bodies=True)
    assert len(expected) == 2
    raw_audio_read.invalidate_pack_index(remote, UID, CID)
    if mode == 'disabled':
        monkeypatch.setenv('PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED', 'false')
    if mode == 'listed_disabled':
        monkeypatch.setenv('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED', 'false')
    if mode == 'cold_race':
        manifest.metageneration = 2
        manifest.download_as_bytes.side_effect = [PreconditionFailed('metadata changed'), manifest.data]
    if mode == 'warm_race':
        manifest.reload = Mock(side_effect=[PreconditionFailed('metadata changed'), None])
    actual = raw_audio_read.list_packs(
        remote, UID, CID, reuse_manifest_bodies=mode != 'not_inventory', fresh=mode == 'fresh', strict=mode == 'strict'
    )
    assert actual == expected
    assert manifest.download_as_bytes.call_count == (3 if mode == 'cold_race' else 2)
    assert ('if_metageneration_match' in manifest.download_as_bytes.call_args.kwargs) == (
        mode not in {'listed_disabled', 'cold_race', 'warm_race'}
    )


def test_decode_returns_captured_samples_without_shifting_the_clock(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, packets = build_pack(remote, gapped_frames())
    captured = decode_packets(packets)
    pcm = raw_audio_read.read_pack(remote, receipt.path, UID)
    assert pcm == captured
    packs = raw_audio_read.list_packs(remote, UID, CID)
    assert [raw_audio_read.select_raw_pcm(pcm, pack, RATE) for pack in packs] == [
        captured[: 640 * 2],
        captured[640 * 2 :],
    ]


def test_retained_proof_counts_audio_seconds_without_gap_time(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    build_pack(remote, gapped_frames())
    monkeypatch.setattr(repair, 'privacy_read', lambda *args, **kwargs: None)
    store = SimpleNamespace(run=lambda fn: fn(None))
    artifacts = SimpleNamespace(key_for_owner=lambda uid: b'x' * 32)
    proof = repair.retained_proof(store, UID, CID, 1, client(remote), artifacts)
    # 800 captured samples = 0.05 s of audio; the 3 s gap is not audio.
    assert proof['audio_seconds'] == pytest.approx(0.05)
    # The unit still spans the gap, because that silence is what STT is billed.
    assert proof['stt_seconds'] == pytest.approx(3.03)
    assert proof['start'] == pytest.approx(1000.0)
    assert proof['end'] == pytest.approx(1003.03)


def test_materialized_unit_places_audio_at_its_capture_position(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, packets = build_pack(remote, gapped_frames())
    chunks = storage.list_audio_chunks(UID, CID, include_raw=True, require_archive=True, client=client(remote))
    units = list(live.retained_record_units(UID, CID, chunks, client(remote), b'x' * 32))
    assert len(units) == 1
    start, duration, references = units[0]
    assert (start, duration) == (pytest.approx(1000.0), pytest.approx(3.03))
    manifest = {
        'owner_id': UID,
        'conversation_id': CID,
        'capture_at': start,
        'context': {'synthetic': True},
        'references': references,
    }
    body = source_audio.MAGIC + json.dumps(manifest).encode()
    item = SimpleNamespace(owner_id=UID, conversation_id=CID, capture_at=start, duration_seconds=duration)
    wav = source_audio.materialize(body, item, lambda ref: raw_audio_read.read_pack(remote, ref['path'], UID))
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        pcm = stream.readframes(stream.getnframes())
    assert len(pcm) == round(duration * RATE) * 2
    captured = decode_packets(packets)
    gap = round((1003.02 - 1000.04) * RATE)
    assert pcm[: 640 * 2] == captured[: 640 * 2]
    assert pcm[640 * 2 : (640 + gap) * 2] == b'\x00' * (gap * 2)
    assert pcm[(640 + gap) * 2 :] == captured[640 * 2 :]


def test_pinned_gapped_unframed_pack_recovers_without_digest_refusal(remote, monkeypatch, native_opus, setup):
    """Recovery must decode the pinned WAL pack with admission's frame-table semantics."""
    wire(remote, monkeypatch)
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', remote.name)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.setattr(sys.modules[__name__], 'UID', 'synthetic-owner')
    monkeypatch.setattr(sys.modules[__name__], 'CID', 'c')
    monkeypatch.setattr(sys.modules[__name__], 'NAME', 'c/0/0/session/0')

    receipt, _, _, packets = build_pack(remote, gapped_frames())
    storage_client = client(remote)
    chunks = storage.list_audio_chunks(
        UID, CID, include_raw=True, require_archive=True, client=storage_client, source_metadata=True
    )
    units = list(live.retained_record_units(UID, CID, chunks, storage_client, b'0' * 32))
    assert len(units) == 1
    start, duration, references = units[0]
    assert {ref['generation'] for ref in references} == {int(receipt.generation)}
    body = (
        source_audio.MAGIC
        + json.dumps(
            {
                'owner_id': UID,
                'conversation_id': CID,
                'capture_at': start,
                'context': {},
                'references': references,
            }
        ).encode()
    )

    db_client, _, _, artifacts, stt, _ = setup
    row(db_client).update(conversation_id=CID, capture_at=start, duration_seconds=duration)
    source = ArtifactStore(
        storage_client,
        bucket='synthetic',
        namespace='batch_pipeline_prod',
        authorize=lambda _: ProtectionContext('standard', 0),
        key_for_owner=lambda _: b'0' * 32,
        register_artifact=lambda *args: None,
    )
    source._read = Mock(return_value=body)
    artifacts.fetch_audio.side_effect = source.fetch_audio

    media = remote.blob(receipt.path)
    media.download_as_bytes = Mock(wraps=media.download_as_bytes)
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )

    assert response.status_code == 200 and response.json() == {'status': 'recovered'}
    assert row(db_client)['recovery_state'] == 'recovered'
    assert 'refusal' not in row(db_client)['recovery']
    stt.assert_called_once()
    assert media.download_as_bytes.call_count == 1
    assert media.download_as_bytes.call_args.kwargs['if_generation_match'] == int(receipt.generation)
    audio = stt.call_args.args[2]
    with wave.open(io.BytesIO(audio), 'rb') as stream:
        recovered = stream.readframes(stream.getnframes())
    captured = decode_packets(packets)
    gap = round((1003.02 - 1000.04) * RATE)
    assert recovered == captured[: 640 * 2] + b'\x00' * (gap * 2) + captured[640 * 2 :]


def test_retained_zero_sample_frame_is_kept_but_contributes_no_audio(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    frames = [(1000.0, tone(320, 1)), (1000.02, b''), (1000.04, tone(320, 2))]
    receipt, table, _, packets = build_pack(remote, frames)
    metadata = remote.blob(receipt.path).metadata
    # The writer counts a retained zero-sample frame as a gap and cannot prove PCM.
    assert metadata['gap_count'] == '2'
    assert 'pcm_sha256' not in metadata
    assert [row['samples'] for row in table] == [320, 0, 320]
    packs = raw_audio_read.list_packs(remote, UID, CID)
    # The retained zero-sample frame is a real discontinuity, so the two audio
    # runs stay separate rather than being closed into one continuous span.
    assert [(p['timestamp'], p['span']['samples']) for p in packs] == [(1000.0, 320), (1000.04, 320)]
    assert raw_audio_read.read_pack(remote, receipt.path, UID) == decode_packets(packets)


def test_retained_proof_reads_a_pack_with_a_zero_sample_frame(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    frames = [(1000.0, tone(320, 1)), (1000.02, b''), (1000.04, tone(320, 2))]
    build_pack(remote, frames)
    monkeypatch.setattr(repair, 'privacy_read', lambda *args, **kwargs: None)
    store = SimpleNamespace(run=lambda fn: fn(None))
    artifacts = SimpleNamespace(key_for_owner=lambda uid: b'x' * 32)
    # The proof reads through read_reference, not read_pack: the retained
    # zero-sample packet is not decodable, so the manifest frames must drive it.
    proof = repair.retained_proof(store, UID, CID, 1, client(remote), artifacts)
    assert proof['audio_seconds'] == pytest.approx(0.04)
    # The unit still spans the 20 ms gap between the two captured runs.
    assert proof['stt_seconds'] == pytest.approx(0.06)
    assert proof['start'] == pytest.approx(1000.0)
    assert proof['end'] == pytest.approx(1000.06)


def test_kill_switch_restores_the_previous_skip(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, packets = build_pack(remote, gapped_frames())
    monkeypatch.setenv('RAW_LIVE_GAPPED_PACKS_ENABLED', 'false')
    assert raw_audio_read.list_packs(remote, UID, CID) == []
    with pytest.raises(raw_audio_read.CoverageMismatch):
        raw_audio_read.read_pack(remote, receipt.path, UID)


def test_missing_manifest_stays_excluded(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    receipt, _, _, packets = build_pack(remote, gapped_frames())
    for name in [name for name in remote.blobs if name.startswith('audio-outbox/')]:
        remote.blobs[name].data = None
    assert raw_audio_read.list_packs(remote, UID, CID) == []
    with pytest.raises(ValueError):
        raw_audio_read.read_pack(remote, receipt.path, UID)


def test_continuous_unframed_pack_is_unchanged(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    frames = [(1000.0, tone(320, 1)), (1000.02, tone(320, 2))]
    receipt, _, _, packets = build_pack(remote, frames)
    metadata = remote.blob(receipt.path).metadata
    assert metadata['gap_count'] == '0'
    assert 'frame_schema' not in metadata
    packs = raw_audio_read.list_packs(remote, UID, CID)
    assert [(p['timestamp'], p['span']['samples']) for p in packs] == [(1000.0, 640)]
    assert raw_audio_read.read_pack(remote, receipt.path, UID) == decode_packets(packets)


def test_framed_pack_still_uses_its_declared_frame_schema(remote, monkeypatch, native_opus):
    wire(remote, monkeypatch)
    first, second = tone(320, 1), tone(160, 2)
    frames = [
        {
            'sequence': 0,
            'start': 1000.0,
            'samples': 320,
            'sha256': hashlib.sha256(first).hexdigest(),
            'gap_before': False,
        },
        {
            'sequence': 1,
            'start': 1003.02,
            'samples': 160,
            'sha256': hashlib.sha256(second).hexdigest(),
            'gap_before': True,
        },
    ]
    receipt = commit_pcm_window(UID, first + second, CID, 1000.0, RATE, 'session', 0, frames, framed=True)
    assert remote.blob(receipt.path).metadata['frame_schema'] == FRAME_SCHEMA
    packs = raw_audio_read.list_packs(remote, UID, CID)
    assert [(p['timestamp'], p['span']['samples']) for p in packs] == [(1000.0, 320), (1003.02, 160)]
    assert raw_audio_read.read_pack(remote, receipt.path, UID) == first + second


@pytest.mark.parametrize('mode', ['on', 'off', 'stale', 'missing_metageneration', 'deleted', 'corrupt'])
@pytest.mark.parametrize('per_pack', [False, True])
def test_gapped_manifest_can_use_versioned_listing_without_skipping_payload_proof(monkeypatch, mode, per_pack):
    from unittest.mock import Mock

    from google.api_core.exceptions import NotFound, PreconditionFailed

    from utils.other.audio_frame_table import gapped_frames, unframed_frames

    path = 'audio-outbox/owner/pack/manifest'
    media = SimpleNamespace(name='raw-live/owner/pack/object', generation=9, metadata={'sha256': 'media-digest'})
    table = [
        {'sequence': 0, 'start': 1.0, 'samples': 16, 'gap_before': False},
    ]
    manifest = json.dumps(
        {
            'schema': 'audio_custody_v1',
            'capture': {'sample_rate': RATE},
            'frames': table,
            'media': {'bucket': 'private-synthetic', 'path': media.name, 'generation': '9', 'sha256': 'media-digest'},
        }
    ).encode()
    properties = {
        'encrypted': 'false',
        'sha256': hashlib.sha256(manifest).hexdigest(),
        'format': 'audio-custody-manifest-v1',
    }
    listed = SimpleNamespace(
        name=path,
        generation=3,
        metageneration=None if mode == 'missing_metageneration' else 2,
        size=len(manifest),
        metadata=properties,
    )
    loaded = SimpleNamespace(
        name=path,
        generation=4,
        size=len(manifest),
        metadata=properties,
        reload=Mock(),
        download_as_bytes=Mock(return_value=manifest),
    )
    bucket = SimpleNamespace(
        name='private-synthetic', blob=Mock(return_value=loaded), list_blobs=Mock(return_value=[listed])
    )
    if mode == 'stale':
        loaded.download_as_bytes.side_effect = [PreconditionFailed('synthetic stale listing'), manifest]
    if mode == 'deleted':
        loaded.download_as_bytes.side_effect = NotFound('synthetic deletion')
    if mode == 'corrupt':
        loaded.download_as_bytes.return_value = b'wrong hash'
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', bucket.name)
    monkeypatch.setenv('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED', 'false' if mode == 'off' else 'true')

    def resolve():
        if per_pack:
            return gapped_frames(bucket, media, UID)
        return unframed_frames(bucket, media, UID, path, listed_manifest=listed)

    if mode == 'deleted':
        with pytest.raises(NotFound):
            resolve()
    elif mode == 'corrupt':
        with pytest.raises(ValueError, match='checksum mismatch'):
            resolve()
    else:
        assert resolve() == (table, RATE)
    if per_pack:
        assert bucket.list_blobs.call_args.kwargs['prefix'] == 'audio-outbox/owner/pack/'
    bucket.blob.assert_called_once_with(path)
    conditions = [
        {key: value for key, value in call.kwargs.items() if key.startswith('if_')}
        for call in loaded.download_as_bytes.call_args_list
    ]
    fast = {'if_generation_match': 3, 'if_metageneration_match': 2}
    legacy = {'if_generation_match': 4}
    if mode == 'stale':
        loaded.reload.assert_called_once()
        assert conditions == [fast, legacy]
    elif mode in ('off', 'missing_metageneration'):
        loaded.reload.assert_called_once()
        assert conditions == [legacy]
    else:
        loaded.reload.assert_not_called()
        assert conditions == [fast]
