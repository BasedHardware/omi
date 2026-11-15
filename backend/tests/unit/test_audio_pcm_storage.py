"""Storage savings must never change PCM, frame clocks or receipt durability."""

import hashlib
import json
import math
import random
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from utils.other import audio_outbox, audio_pcm_storage, raw_audio_read
from utils.other.audio_frame_table import FRAME_SCHEMA
from utils.other.live_audio_archive import LiveAudioArchive
from utils.other.raw_audio import CapturePack, decode_capture
from tests.unit.test_audio_durable_outbox import remote, host
from tests.unit.test_audio_custody_frames import frame, _sent_receipts
from tests.unit.test_audio_durable_outbox import _window_harness, _audio_frames, Socket, pusher


@pytest.fixture(autouse=True)
def compression_enabled(monkeypatch):
    monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'true')


@pytest.mark.parametrize('kind', ['silence', 'quiet', 'mixed'])
def test_real_encoder_preserves_every_sample_and_is_deterministic(kind):
    samples = [
        0 if kind == 'silence' or (kind == 'mixed' and i < 16000) else round(20 * math.sin(i * 0.13))
        for i in range(32000)
    ]
    pcm = struct.pack(f'<{len(samples)}h', *samples)
    pack = CapturePack('pcm16', 16000)
    pack.append(pcm, 'conversation', 1000, len(samples))
    encoded, metadata = pack.encoded(preserve_pcm=True, compact_custody_pcm=True)
    assert metadata['codec'] == metadata['format'] == 'flac'
    assert len(encoded) <= len(pcm) * 0.95
    assert decode_capture(encoded, metadata) == pcm
    assert metadata['pcm_sha256'] == hashlib.sha256(pcm).hexdigest()
    assert pack.encoded(preserve_pcm=True, compact_custody_pcm=True) == (encoded, metadata)
    assert pack.encoded(preserve_pcm=True)[0] == pcm


def test_incompressible_pcm_does_not_grow():
    pcm = random.Random(42).randbytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')


@pytest.mark.parametrize('outcome', ['disabled', 'ineligible', 'busy', 'timeout', 'flac', 'retry'])
def test_attempt_byte_metrics_follow_encoder_admission_and_verified_savings(monkeypatch, outcome):
    amounts = {'input': 0, 'saved': 0}

    def meter(name):
        def inc(amount):
            amounts[name] += amount

        return SimpleNamespace(inc=inc)

    monkeypatch.setattr(audio_pcm_storage, 'INPUT_BYTES', meter('input'))
    monkeypatch.setattr(audio_pcm_storage, 'SAVED_BYTES', meter('saved'))
    pcm = bytes(2 if outcome == 'ineligible' else 64000)
    encoded = b'compressed'
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs['input'])
        assert amounts['input'] >= len(pcm)  # counted before invoking the child
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired('ffmpeg', 2)
        return SimpleNamespace(stdout=encoded if kwargs['input'] == pcm else pcm)

    monkeypatch.setattr(subprocess, 'run', run)
    if outcome == 'disabled':
        monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'false')
    if outcome == 'busy':
        monkeypatch.setattr(audio_pcm_storage, '_ENCODERS', SimpleNamespace(acquire=lambda **k: False))
    attempts = 2 if outcome == 'retry' else 1
    for _ in range(attempts):
        result = audio_pcm_storage.compact_pcm(pcm, 16000, 1)
        assert result == ((encoded, 'flac') if outcome in {'flac', 'retry'} else (pcm, 'pcm16'))
    admitted = outcome in {'timeout', 'flac', 'retry'}
    assert amounts['input'] == (len(pcm) * attempts if admitted else 0)
    verified = outcome in {'flac', 'retry'}
    assert amounts['saved'] == ((len(pcm) - len(encoded)) * attempts if verified else 0)
    assert len(calls) == (2 * attempts if verified else 1 if admitted else 0)


def test_unproven_zero_sample_payload_keeps_original_container(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('unproven PCM must not invoke encoder'))
    pack = CapturePack('pcm16', 16000)
    pcm = bytes(64000)
    pack.append(pcm, 'conversation', 1000, len(pcm) // 2)
    # Even alignment alone cannot make an undecodable retained frame PCM.
    pack.append(b'\xff\xff', 'conversation', 1002, 0)
    assert not pack.pcm_proven
    encoded, metadata = pack.encoded(preserve_pcm=True, compact_custody_pcm=True)
    assert encoded == pcm + b'\xff\xff'
    assert metadata['codec'] == 'pcm16' and metadata['pcm_sha256'] is None


@pytest.mark.parametrize('value', ['false', '', 'bad'])
def test_kill_switch_preserves_pcm_without_launching_encoder(monkeypatch, value):
    monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', value)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('encoder must not run'))
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'corrupt'])
def test_optional_encoder_failure_keeps_original_pcm_and_releases_capacity(monkeypatch, failure):
    def run(*args, **kwargs):
        assert 0 < kwargs['timeout'] <= 2
        if failure == 'missing':
            raise FileNotFoundError('ffmpeg')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])
        return SimpleNamespace(stdout=b'invalid')

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    audio_pcm_storage._ENCODERS.release()


def test_busy_encoder_keeps_pcm(monkeypatch):
    monkeypatch.setattr(audio_pcm_storage, '_ENCODERS', SimpleNamespace(acquire=lambda **k: False))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('encoder must not run'))
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')


def _decision_meter(monkeypatch):
    seen = []

    class _Child:
        def __init__(self, label):
            self.label = label

        def inc(self, amount=1):
            seen.append((self.label, amount))

    monkeypatch.setattr(audio_pcm_storage, 'DECISIONS', SimpleNamespace(labels=lambda label: _Child(label)))
    return seen


def test_one_codec_child_per_process():
    # One vCPU pods cannot hide two concurrent encoders; the second call must stay PCM as busy.
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    try:
        assert not audio_pcm_storage._ENCODERS.acquire(blocking=False)
    finally:
        audio_pcm_storage._ENCODERS.release()


def test_exhausted_total_budget_keeps_pcm_without_launching_encoder(monkeypatch):
    seen = _decision_meter(monkeypatch)
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.0)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('encoder must not run'))
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert ('deadline', 1) in seen


def test_budget_limited_child_timeout_is_a_deadline_not_a_codec_error(monkeypatch):
    seen = _decision_meter(monkeypatch)
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.2)

    def run(*args, **kwargs):
        assert kwargs['timeout'] < audio_pcm_storage._TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert ('deadline', 1) in seen


def test_full_child_timeout_cap_still_labels_encoder_error(monkeypatch):
    seen = _decision_meter(monkeypatch)
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 10.0)

    def run(*args, **kwargs):
        assert kwargs['timeout'] == audio_pcm_storage._TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert ('encoder_error', 1) in seen


def test_decode_stage_uses_only_the_remaining_shared_budget(monkeypatch):
    seen = _decision_meter(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.4)
    monkeypatch.setattr(audio_pcm_storage, '_DECODE_RESERVE_SECONDS', 0.08)
    pcm = bytes(64000)
    encoded = b'x' * 1000
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs['timeout'])
        if len(calls) == 1:
            clock[0] += 0.30  # encode consumed most of the shared budget
            return SimpleNamespace(stdout=encoded)
        return SimpleNamespace(stdout=pcm)

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (encoded, 'flac')
    assert calls[0] == pytest.approx(0.32)
    assert calls[1] == pytest.approx(0.10)
    assert ('flac', 1) in seen


def test_decode_without_remaining_budget_keeps_pcm(monkeypatch):
    seen = _decision_meter(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.4)
    monkeypatch.setattr(audio_pcm_storage, '_DECODE_RESERVE_SECONDS', 0.08)
    pcm = bytes(64000)
    encoded = b'x' * 1000
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0] += 0.40  # encode alone spent the whole budget
        return SimpleNamespace(stdout=encoded)

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert len(calls) == 1
    assert ('deadline', 1) in seen


def test_real_subprocess_timeout_still_commits_original_custody(remote, monkeypatch):
    real_run = subprocess.run

    def hung_encoder(*args, **kwargs):
        return real_run([sys.executable, '-c', 'import time; time.sleep(10)'], **kwargs)

    monkeypatch.setattr(subprocess, 'run', hung_encoder)
    pcm = bytes(64000)
    started = time.monotonic()
    receipt = audio_outbox.commit_pcm('owner', pcm, 'conversation', 1000, 16000, 'root', 0)
    assert time.monotonic() - started < 5
    assert remote.blob(receipt.path).data == pcm
    assert audio_outbox.read_pcm('owner', receipt) == pcm


def test_busy_encoder_still_commits_original_custody(remote, monkeypatch):
    monkeypatch.setattr(audio_pcm_storage, '_ENCODERS', SimpleNamespace(acquire=lambda **k: False))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('encoder must not run'))
    pcm = bytes(64000)
    receipt = audio_outbox.commit_pcm('owner', pcm, 'conversation', 1000, 16000, 'root', 0)
    assert remote.blob(receipt.path).data == pcm
    assert audio_outbox.read_pcm('owner', receipt) == pcm


@pytest.mark.parametrize('size,channels', [(2, 1), (16 * 1024 * 1024 + 2, 1), (64000, 2), (64001, 1)])
def test_ineligible_input_never_invokes_encoder(monkeypatch, size, channels):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('encoder must not run'))
    pcm = bytes(size)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, channels) == (pcm, 'pcm16')


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_compressed_receipt_and_existing_raw_reader_preserve_gapped_frames(remote, monkeypatch, protection):
    first, second = bytes(32000), struct.pack('<h', 7) * 16000
    pcm = first + second
    frames = [frame(first, 1000), frame(second, 1005, sequence=1, offset=len(first), gap=True)]
    receipt = audio_outbox.commit_pcm_window(
        'owner',
        pcm,
        'conversation',
        1000,
        16000,
        'root',
        0,
        frames,
        framed=True,
        data_protection_level=protection,
    )
    blob = remote.blob(receipt.path)
    assert blob.metadata['codec'] == 'flac'
    assert blob.metadata['frame_schema'] == FRAME_SCHEMA
    assert len(blob.data) < len(pcm)
    assert audio_outbox.read_pcm('owner', receipt) == pcm
    assert raw_audio_read.read_pack(remote, receipt.path, 'owner') == pcm
    packs = raw_audio_read.list_packs(remote, 'owner', 'conversation')
    assert [raw_audio_read.select_raw_pcm(pcm, pack, 16000) for pack in packs] == [first, second]
    # A retry reuses immutable generations, without another media or manifest.
    again = audio_outbox.commit_pcm_window(
        'owner',
        pcm,
        'conversation',
        1000,
        16000,
        'root',
        0,
        frames,
        framed=True,
        data_protection_level=protection,
    )
    assert again == receipt
    assert len(remote.list_blobs('raw-live/')) == len(remote.list_blobs('audio-outbox/')) == 1
    # Writer rollback does not prevent receipt recovery of already compressed data.
    monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'false')
    assert audio_outbox.read_pcm('owner', receipt) == pcm


@pytest.mark.asyncio
async def test_listen_writer_compresses_only_new_pcm_and_keeps_native_packets(remote):
    h = host()
    archive = LiveAudioArchive(h)
    pcm = bytes(64000)
    await archive.append(pcm, 'conversation', 1000, len(pcm) // 2)
    await archive.close()
    blobs = remote.list_blobs('raw-live/')
    assert len(blobs) == 1 and blobs[0].metadata['codec'] == 'flac'
    manifests = remote.list_blobs('audio-outbox/')
    receipt_data = json.loads(manifests[0].data)
    assert receipt_data['frames'][0]['sha256'] == hashlib.sha256(pcm).hexdigest()
    assert raw_audio_read.read_pack(remote, blobs[0].name, 'owner') == pcm
    for codec in ['opus', 'pcm8', 'unknown']:
        pack = CapturePack(codec, 16000)
        pack.append(b'original', 'conversation', 1000, 0)
        assert pack.encoded(preserve_pcm=True, compact_custody_pcm=True) == pack.encoded(preserve_pcm=True)


@pytest.mark.asyncio
async def test_pusher_commits_compressed_pcm_before_receipt_and_projection(remote, monkeypatch):
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    captured = [bytes(32000), struct.pack('<h', 5) * 16000]
    sock = Socket(_audio_frames('conversation', captured, step=3))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = _sent_receipts(sock)
    assert len(receipts) == 1
    assert remote.blob(receipts[0].path).metadata['codec'] == 'flac'
    assert audio_outbox.read_pcm('owner', receipts[0]) == b''.join(captured)
