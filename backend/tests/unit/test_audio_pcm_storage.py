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
    # Only the codec admission clock is frozen; subprocesses and async harnesses
    # retain their real clocks. Budget tests below advance their own fake clock.
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: 100.0))


@pytest.fixture
def real_codec_budget(monkeypatch):
    # A real ffmpeg round trip proves codec correctness, not runner speed. Keep
    # a generous child watchdog; deterministic deadline tests cover the 0.4 s
    # production policy independently, without sleeping or running a codec.
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 60.0)
    monkeypatch.setattr(audio_pcm_storage, '_TIMEOUT_SECONDS', 60.0)


def _live_stage_children():
    """Pre-created stage children with their per-process observation counts."""
    counts = {}
    for metric in (audio_pcm_storage.STAGE_SECONDS, audio_pcm_storage.STAGE_TIMEOUT_OVERSHOOT_SECONDS):
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith('_count'):
                    counts[tuple(sorted(sample.labels.items()))] = sample.value
    return counts


def test_stage_children_exist_before_any_observation():
    # Ran first in this module: the eight children are pre-created with zero
    # observations. A lazy child would not exist yet, and observe(0) would
    # fabricate a sample here.
    children = _live_stage_children()
    assert len(children) == 8
    assert set(children.values()) == {0}


@pytest.mark.parametrize('kind', ['silence', 'quiet', 'mixed'])
def test_real_encoder_preserves_every_sample_and_is_deterministic(kind, real_codec_budget):
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


def test_incompressible_pcm_does_not_grow(real_codec_budget):
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
    clock = [100.0]
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.2)

    def run(*args, **kwargs):
        # Deterministic: 0.2 s budget less the 0.08 s decode reserve.
        assert kwargs['timeout'] == pytest.approx(0.12)
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


def _fallback_meter(monkeypatch):
    seen = []
    monkeypatch.setattr(audio_pcm_storage, 'record_fallback', lambda **kwargs: seen.append(kwargs))
    return seen


def test_deadline_records_one_shared_fallback_and_keeps_the_domain_counter(monkeypatch):
    decisions = _decision_meter(monkeypatch)
    fallbacks = _fallback_meter(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.2)

    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert fallbacks == [
        {
            'component': 'audio_custody',
            'from_mode': 'flac',
            'to_mode': 'pcm16',
            'reason': 'timeout',
            'outcome': 'degraded',
        }
    ]
    assert ('deadline', 1) in decisions


def test_verified_flac_and_disabled_switch_record_no_fallback(monkeypatch):
    fallbacks = _fallback_meter(monkeypatch)
    pcm = bytes(64000)
    encoded = b'x' * 1000
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs['input'])
        return SimpleNamespace(stdout=encoded if kwargs['input'] == pcm else pcm)

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (encoded, 'flac')
    monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'false')
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert fallbacks == []


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
def test_compressed_receipt_and_existing_raw_reader_preserve_gapped_frames(
    remote, monkeypatch, protection, real_codec_budget
):
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
async def test_listen_writer_compresses_only_new_pcm_and_keeps_native_packets(remote, real_codec_budget):
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
async def test_pusher_commits_compressed_pcm_before_receipt_and_projection(remote, monkeypatch, real_codec_budget):
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    captured = [bytes(32000), struct.pack('<h', 5) * 16000]
    sock = Socket(_audio_frames('conversation', captured, step=3))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = _sent_receipts(sock)
    assert len(receipts) == 1
    assert remote.blob(receipts[0].path).metadata['codec'] == 'flac'
    assert audio_outbox.read_pcm('owner', receipts[0]) == b''.join(captured)


def _stage_meter(monkeypatch):
    """Record stage observations without touching the process-wide histograms."""
    seen = []

    class _Child:
        def __init__(self, record):
            self.record = record

        def observe(self, value):
            seen.append(self.record + (value,))

    monkeypatch.setattr(
        audio_pcm_storage,
        'STAGE_SECONDS',
        SimpleNamespace(labels=lambda **kw: _Child(('stage', kw['stage'], kw['child_result']))),
    )
    monkeypatch.setattr(
        audio_pcm_storage,
        'STAGE_TIMEOUT_OVERSHOOT_SECONDS',
        SimpleNamespace(labels=lambda **kw: _Child(('overshoot', kw['stage']))),
    )
    return seen


def _codec_clock(monkeypatch, start=100.0):
    clock = [start]
    monkeypatch.setattr(audio_pcm_storage, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(audio_pcm_storage, '_TOTAL_BUDGET_SECONDS', 0.4)
    monkeypatch.setattr(audio_pcm_storage, '_DECODE_RESERVE_SECONDS', 0.08)
    return clock


def test_verified_round_trip_records_each_child_once_as_success(monkeypatch):
    seen = _stage_meter(monkeypatch)
    decisions = _decision_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)
    pcm, encoded = bytes(64000), b'x' * 1000

    def run(*args, **kwargs):
        clock[0] += 0.10 if kwargs['input'] == pcm else 0.05
        return SimpleNamespace(stdout=encoded if kwargs['input'] == pcm else pcm)

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (encoded, 'flac')
    assert seen == [
        ('stage', 'encode', 'success', pytest.approx(0.10)),
        ('stage', 'decode', 'success', pytest.approx(0.05)),
    ]
    assert ('flac', 1) in decisions
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    audio_pcm_storage._ENCODERS.release()


def test_encode_timeout_records_one_stage_and_its_overshoot_without_a_decode(monkeypatch):
    seen = _stage_meter(monkeypatch)
    fallbacks = _fallback_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)

    def run(*args, **kwargs):
        assert kwargs['timeout'] == pytest.approx(0.32)  # budget less the decode reserve
        clock[0] += 0.40
        raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert seen == [
        ('stage', 'encode', 'timeout', pytest.approx(0.40)),
        ('overshoot', 'encode', pytest.approx(0.08)),
    ]
    assert len(fallbacks) == 1
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    audio_pcm_storage._ENCODERS.release()


def test_decode_timeout_records_encode_success_and_decode_timeout(monkeypatch):
    seen = _stage_meter(monkeypatch)
    fallbacks = _fallback_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)
    pcm, encoded = bytes(64000), b'x' * 1000
    grants = []

    def run(*args, **kwargs):
        grants.append(kwargs['timeout'])
        if kwargs['input'] == pcm:
            clock[0] += 0.30  # encode leaves only the remainder for verification
            return SimpleNamespace(stdout=encoded)
        clock[0] += 0.12
        raise subprocess.TimeoutExpired('ffmpeg', kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert grants == [pytest.approx(0.32), pytest.approx(0.10)]
    assert seen == [
        ('stage', 'encode', 'success', pytest.approx(0.30)),
        ('stage', 'decode', 'timeout', pytest.approx(0.12)),
        ('overshoot', 'decode', pytest.approx(0.02)),
    ]
    assert len(fallbacks) == 1
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    audio_pcm_storage._ENCODERS.release()


def test_handled_child_error_records_error_without_an_overshoot(monkeypatch):
    seen = _stage_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)

    def run(*args, **kwargs):
        clock[0] += 0.01
        raise FileNotFoundError('ffmpeg')

    monkeypatch.setattr(subprocess, 'run', run)
    pcm = bytes(64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert seen == [('stage', 'encode', 'error', pytest.approx(0.01))]
    assert audio_pcm_storage._ENCODERS.acquire(blocking=False)
    audio_pcm_storage._ENCODERS.release()


def test_insufficient_saving_records_only_the_successful_encode(monkeypatch):
    seen = _stage_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)
    pcm = bytes(64000)

    def run(*args, **kwargs):
        clock[0] += 0.06
        return SimpleNamespace(stdout=pcm)  # no saving, so verification is skipped

    monkeypatch.setattr(subprocess, 'run', run)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert seen == [('stage', 'encode', 'success', pytest.approx(0.06))]


@pytest.mark.parametrize('path', ['disabled', 'ineligible', 'busy'])
def test_non_admitted_paths_record_no_stage_samples(monkeypatch, path):
    seen = _stage_meter(monkeypatch)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('no codec child may run'))
    if path == 'disabled':
        monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'false')
    if path == 'busy':
        monkeypatch.setattr(audio_pcm_storage, '_ENCODERS', SimpleNamespace(acquire=lambda **k: False))
    pcm = bytes(2 if path == 'ineligible' else 64000)
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (pcm, 'pcm16')
    assert seen == []


def test_non_admitted_path_leaves_the_live_stage_counters_untouched(monkeypatch):
    monkeypatch.setenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'false')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('no codec child may run'))
    before = _live_stage_children()
    assert audio_pcm_storage.compact_pcm(bytes(64000), 16000, 1) == (bytes(64000), 'pcm16')
    assert _live_stage_children() == before


class _SlowComparison(bytes):
    """Byte comparison that costs injected clock time, standing in for real work."""

    def __eq__(self, other):
        _SlowComparison.clock[0] += 0.30
        return bytes.__eq__(self, other)


def test_decode_stage_clock_stops_before_the_byte_comparison_and_saving(monkeypatch):
    # The decode stage times the child, not the verification that follows it. A
    # meta-clock that advances during comparison and saved-byte accounting would
    # inflate the sample if the end timestamp were taken after either of them.
    seen = _stage_meter(monkeypatch)
    clock = _codec_clock(monkeypatch)
    pcm, encoded = bytes(64000), b'x' * 1000
    saved = []
    _SlowComparison.clock = clock

    def run(*args, **kwargs):
        if kwargs['input'] == pcm:
            clock[0] += 0.10
            return SimpleNamespace(stdout=encoded)
        clock[0] += 0.05
        return SimpleNamespace(stdout=_SlowComparison(pcm))

    def metered_saved(amount):
        clock[0] += 0.20  # accounting work after the child returned
        saved.append(amount)

    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(audio_pcm_storage, 'SAVED_BYTES', SimpleNamespace(inc=metered_saved))
    assert audio_pcm_storage.compact_pcm(pcm, 16000, 1) == (encoded, 'flac')
    assert seen == [
        ('stage', 'encode', 'success', pytest.approx(0.10)),
        ('stage', 'decode', 'success', pytest.approx(0.05)),
    ]
    assert saved == [len(pcm) - len(encoded)]
