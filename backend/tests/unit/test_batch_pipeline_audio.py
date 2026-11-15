"""Canonical intake preserves every frame and real capture-clock boundaries."""

import struct
from pathlib import Path
import wave
import io

import pytest

from utils.batch_pipeline import audio, capture_decode


def pcm(tmp_path, capture, samples=160, rate=16000, sample=1):
    path = tmp_path / f'audio_omi_pcm16_{rate}_{capture}.bin'
    body = struct.pack('<h', sample) * samples
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


def test_early_capture_batch_keeps_raw_identity_and_order_with_receipt_clock(tmp_path):
    receipt = 1800000000.0
    # Reverse input order, separated enough to produce two units.
    paths = [pcm(tmp_path, 788918500, 16000), pcm(tmp_path, 788918400, 16000)]
    units = list(capture_decode.decode_units(paths, received_at=receipt, max_seconds=1))
    assert [u.capture_at for u in units] == [788918400, 788918500]
    assert [u.stored_capture_at for u in units] == [receipt - 2, receipt - 1]
    assert [u.duration_seconds for u in units] == [1, 1]
    assert units[-1].stored_capture_at + units[-1].duration_seconds == receipt


def test_distinct_reset_years_pack_in_order_without_keeping_bogus_gaps(tmp_path):
    receipt = 1800000000.0
    paths = [pcm(tmp_path, 1685577600, 16000), pcm(tmp_path, 788918400, 16000)]
    units = list(capture_decode.decode_units(paths, received_at=receipt, max_seconds=1))
    assert [u.capture_at for u in units] == [788918400, 1685577600]
    assert [u.stored_capture_at for u in units] == [receipt - 2, receipt - 1]
    assert sum(u.duration_seconds for u in units) == 2


def test_early_packing_keeps_pcm_order_without_inventing_wall_clock_silence(tmp_path):
    paths = [pcm(tmp_path, 1685577600, 16000, sample=2), pcm(tmp_path, 788918400, 16000, sample=1)]
    [unit] = list(capture_decode.decode_units(paths, received_at=1800000000.0))
    assert unit.capture_at == 788918400 and unit.stored_capture_at == 1799999998.0
    with wave.open(io.BytesIO(unit.wav)) as stream:
        assert stream.getnframes() == 32000
        assert stream.readframes(32000) == b'\x01\x00' * 16000 + b'\x02\x00' * 16000


def test_early_and_normal_clocks_do_not_share_one_packed_unit(tmp_path):
    # Adjacent raw stamps straddle the policy floor but use different clocks.
    receipt = 1800000000.0
    paths = [pcm(tmp_path, 1704067199, 16000), pcm(tmp_path, 1704067200, 16000)]
    units = list(capture_decode.decode_units(paths, received_at=receipt))
    assert len(units) == 2
    assert units[0].stored_capture_at == receipt - 1
    assert units[1].capture_at == 1704067200 and units[1].stored_capture_at is None


def test_split_early_file_keeps_its_clock_after_a_derived_start_crosses_the_floor(tmp_path):
    receipt = 1800000000.0
    units = list(capture_decode.decode_units([pcm(tmp_path, 1704067199, 32000)], received_at=receipt, max_seconds=1))
    assert [u.capture_at for u in units] == [1704067199, 1704067200]
    assert [u.stored_capture_at for u in units] == [receipt - 2, receipt - 1]


@pytest.mark.parametrize('covered,kept', [((0, 2), [2, 3]), ((1, 2), [0, 2, 3])])
def test_coverage_trimmed_early_units_keep_receipt_clock_and_pcm_order(tmp_path, monkeypatch, covered, kept):
    from types import SimpleNamespace
    from models.capture_coverage import FrameRange
    from utils.capture import coverage

    path = pcm(tmp_path, 1704067199)
    Path(path).write_bytes(
        b''.join(struct.pack('<I', 32000) + struct.pack('<h', index + 1) * 16000 for index in range(4))
    )
    claim = {
        'capture_root': '123e4567-e89b-12d3-a456-426614174000',
        'clock_epoch': 1,
        'source_frame_start': 0,
        'frame_count': 4,
        'rate_hz': 16000,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    monkeypatch.setenv(coverage.FLAG, 'serve')
    monkeypatch.setattr(
        coverage, 'admit', lambda *_a, **_k: SimpleNamespace(covered=[FrameRange(start=covered[0], end=covered[1])])
    )
    receipt = 1800000000.0
    units = list(
        capture_decode.decode_units(
            [path],
            received_at=receipt,
            max_seconds=1,
            coverage_context={'uid': 'synthetic', 'capture_evidence_claims': {Path(path).name: claim}},
        )
    )
    assert [unit.capture_at for unit in units] == [1704067199 + index for index in kept]
    assert [unit.stored_capture_at for unit in units] == [receipt - len(kept) + index for index in range(len(kept))]
    for unit, index in zip(units, kept):
        with wave.open(io.BytesIO(unit.wav)) as stream:
            assert stream.readframes(16000) == struct.pack('<h', index + 1) * 16000


def test_receipt_clock_does_not_change_normal_or_future_batch_units(tmp_path):
    receipt = 1800000000.0
    paths = [pcm(tmp_path, receipt - 100, 16000), pcm(tmp_path, receipt + 170, 16000)]
    units = list(capture_decode.decode_units(paths, received_at=receipt))
    assert [u.capture_at for u in units] == [receipt - 100, receipt + 170]
    assert all(u.stored_capture_at is None for u in units)


def test_trimmed_tail_cannot_move_an_older_file_behind_its_newer_sibling(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from models.capture_coverage import FrameRange
    from utils.capture import coverage

    older, newer = pcm(tmp_path, 1704067190), pcm(tmp_path, 1704067195, 16000, sample=2)
    Path(older).write_bytes((struct.pack('<I', 32000) + b'\x01\x00' * 16000) * 20)
    base = {
        'capture_root': '123e4567-e89b-12d3-a456-426614174000',
        'clock_epoch': 1,
        'rate_hz': 16000,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    claims = {
        Path(older).name: {**base, 'source_frame_start': 0, 'frame_count': 20},
        Path(newer).name: {**base, 'source_frame_start': 20, 'frame_count': 1},
    }
    monkeypatch.setenv(coverage.FLAG, 'serve')
    monkeypatch.setattr(
        coverage,
        'admit',
        lambda _uid, _key, ranges, **_k: SimpleNamespace(
            covered=[FrameRange(start=0, end=19)] if ranges[0].start == 0 else []
        ),
    )
    units = list(
        capture_decode.decode_units(
            [newer, older],
            received_at=1800000000.0,
            max_seconds=1,
            coverage_context={'uid': 'synthetic', 'capture_evidence_claims': claims},
        )
    )
    assert [unit.capture_at for unit in units] == [1704067209, 1704067195]
    assert [unit.stored_capture_at for unit in units] == [1799999998, 1799999999]
    for unit, sample in zip(units, (1, 2)):
        with wave.open(io.BytesIO(unit.wav)) as stream:
            assert stream.readframes(16000) == struct.pack('<h', sample) * 16000
