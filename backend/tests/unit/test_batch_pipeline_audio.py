"""Canonical intake preserves every frame and real capture-clock boundaries."""

import struct
from pathlib import Path
import wave
import io

import pytest

from utils.batch_pipeline import audio, capture_decode


def pcm(tmp_path, capture, samples=160, rate=16000):
    path = tmp_path / f'audio_omi_pcm16_{rate}_{capture}.bin'
    body = b'\x01\x00' * samples
    path.write_bytes(struct.pack('<I', len(body)) + body)
    return str(path)


def test_contiguous_upload_files_become_one_conversation_unit(tmp_path):
    paths = [pcm(tmp_path, 1750000100, 16000), pcm(tmp_path, 1750000101, 16000)]
    units = list(capture_decode.decode_units(paths))
    assert len(units) == 1
    assert units[0].capture_at == 1750000100 and units[0].duration_seconds == 2
    with wave.open(io.BytesIO(units[0].wav)) as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) == (
            1,
            2,
            16000,
            32000,
        )
    assert not list(tmp_path.iterdir())


def test_gaps_and_overlap_never_fabricate_contiguous_clock(tmp_path):
    units = list(capture_decode.decode_units([pcm(tmp_path, 1750000100, 16000), pcm(tmp_path, 1750000200, 16000)]))
    assert [u.capture_at for u in units] == [1750000100, 1750000200]
    assert [u.duration_seconds for u in units] == [1, 1]


def test_short_gap_is_silence_with_capture_clock_preserved(tmp_path):
    units = list(capture_decode.decode_units([pcm(tmp_path, 1750000100, 16000), pcm(tmp_path, 1750000102, 16000)]))
    assert len(units) == 1 and units[0].duration_seconds == 3
    with wave.open(io.BytesIO(units[0].wav)) as stream:
        data = stream.readframes(stream.getnframes())
    assert data[32000:64000] == b'\0' * 32000


def test_unit_boundary_splits_without_losing_a_sample(tmp_path, monkeypatch):
    assert capture_decode.UNIT_FRAMES == 3600 * audio.RATE
    monkeypatch.setattr(capture_decode, 'UNIT_FRAMES', 16000)
    units = list(capture_decode.decode_units([pcm(tmp_path, 1750000100, 16001)]))
    assert len(units) == 2
    assert [u.capture_at for u in units] == [1750000100, 1750000101]
    assert sum(round(u.duration_seconds * audio.RATE) for u in units) == 16001


def test_corrupt_sibling_prevents_any_acknowledged_partial_bundle(tmp_path):
    good = pcm(tmp_path, 1750000100)
    bad = tmp_path / 'audio_omi_pcm16_16000_101.bin'
    bad.write_bytes(b'\x04\0\0\0\x01')
    with pytest.raises(ValueError, match='frame'):
        list(capture_decode.decode_units([good, str(bad)]))
    assert Path(good).exists()  # Validation refused before destructive decode.


def test_canonical_resample_preserves_time(tmp_path):
    unit = list(capture_decode.decode_units([pcm(tmp_path, 1750000100, 8000, rate=8000)]))[0]
    assert abs(unit.duration_seconds - 1) <= 1 / audio.RATE


def test_per_pool_ceiling_bounds_units_below_conversation_cap(tmp_path):
    units = list(capture_decode.decode_units([pcm(tmp_path, 1750000100, 16001)], max_seconds=1))
    assert len(units) == 2
    assert all(u.duration_seconds <= 1 for u in units)


def test_encrypted_audio_context_preserves_pcm_for_actual_gpu_decoder(tmp_path):
    from diarizer.batch_pipeline_models import decode_pcm16_wav

    unit = list(capture_decode.decode_units([pcm(tmp_path, 1750000100)]))[0]
    context = {
        'owner_id': 'synthetic',
        'content_id': 'opaque',
        'geolocation': {'latitude': 0.0},
        'recording_session_id': 'recording',
        'capture_evidence_claims': {'file': {'frame_start': 10}},
    }
    frozen = audio.with_context(unit.wav, context)
    assert audio.read_context(frozen) == {**context, 'version': 1}
    before, after = decode_pcm16_wav(unit.wav), decode_pcm16_wav(frozen)
    assert len(before) == len(after) == 160
    assert (before == after).all()


def test_intake_context_rejects_missing_duplicate_oversized_and_truncated(tmp_path):
    unit = list(capture_decode.decode_units([pcm(tmp_path, 1750000100)]))[0]
    with pytest.raises(ValueError):
        audio.read_context(unit.wav)
    frozen = audio.with_context(unit.wav, {})
    with pytest.raises(ValueError):
        audio.read_context(audio.with_context(frozen, {}))
    with pytest.raises(ValueError):
        audio.with_context(unit.wav, {'text': 'x' * 65536})
    with pytest.raises(ValueError):
        audio.read_context(frozen[:-1])
