"""The strict sync decode boundary raises typed deterministic faults.

The batch decode family's doctrine (``decode_pcm16_wav``, ``with_context``,
``source_audio``) is that a fault deterministic on the pinned stored bytes
carries a typed class (``StagedAudioInvalid``) so every downstream boundary
-- worker fetch_decode evidence, admission repair holds, cap-hold admission
-- reads the type instead of collapsing the cohort into anonymous
``ValueError``/``wave.Error``/``OverflowError`` faults. The strict sync
decoder (``capture_decode``) predates the doctrine and was the last decoder
whose raise sites stayed anonymous; these tests pin every site on the typed
contract.

Every fault here reproduces identically on a retry (same stored bytes,
same decode), so each must be ``StagedAudioInvalid``: a ``ValueError``
subclass, so every existing ``except ValueError`` caller keeps catching it.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
"""

import math
import struct
import wave

import pytest

from utils.batch_pipeline.audio import RATE, StagedAudioInvalid
from utils.batch_pipeline.cap_hold_admission import wav_units
from utils.batch_pipeline.capture_decode import _frame_count, canonical_pcm, decode_units


def _wav_bytes(channels: int, width: int, rate: int, frames: int) -> bytes:
    """Craft a RIFF/WAVE container with the requested declared shape.

    Uses the stdlib writer for shapes it accepts and hand-builds the header
    for the hostile shapes it refuses, so the decoder sees exactly the
    declared (channels, width, rate, frames) tuple either way.
    """
    payload = (b'\x0a\x1c\x2e\x3f' * (frames * channels * width // 4 + 2))[: frames * channels * width]
    try:
        out = __import__('io').BytesIO()
        with wave.open(out, 'wb') as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(width)
            stream.setframerate(rate)
            stream.writeframes(payload)
        return out.getvalue()
    except (wave.Error, struct.error, ValueError):
        data_size = len(payload) + (len(payload) % 2)
        header = b'RIFF' + struct.pack('<I', 36 + data_size) + b'WAVE'
        header += b'fmt ' + struct.pack(
            '<IHHIIHH', 16, 1, channels, rate, rate * channels * width, channels * width, width * 8
        )
        header += b'data' + struct.pack('<I', data_size)
        return header + payload


def _write_wav(directory, name: str, body: bytes) -> str:
    path = directory / name
    path.write_bytes(body)
    return str(path)


def _pcm16_bin_bytes(frame_samples: int = 32, frames: int = 1) -> bytes:
    frame = bytes((index % 89) for index in range(frame_samples * 2))
    return b''.join(struct.pack('<I', len(frame)) + frame for _ in range(frames))


def _bin_path(directory, name: str, body: bytes):
    path = directory / name
    path.write_bytes(body)
    return path


def _drain(units):
    return list(units)


# --- _frame_count: every anonymous fault on the frame-stream parser. ---


def test_frame_count_truncated_header_is_typed(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(b'\x01\x02\x03')
    with pytest.raises(StagedAudioInvalid, match='^truncated sync audio frame$'):
        _frame_count(str(path))


def test_frame_count_zero_length_frame_is_typed(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(struct.pack('<I', 0))
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio frame$'):
        _frame_count(str(path))


def test_frame_count_oversize_frame_is_typed(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(struct.pack('<I', 65537) + b'\0' * 8)
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio frame$'):
        _frame_count(str(path))


def test_frame_count_truncated_payload_is_typed(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(struct.pack('<I', 64) + b'\0' * 8)
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio frame$'):
        _frame_count(str(path))


def test_frame_count_empty_stream_is_typed(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(b'')
    with pytest.raises(StagedAudioInvalid, match='^empty sync audio$'):
        _frame_count(str(path))


def test_frame_count_valid_stream_still_counts(tmp_path) -> None:
    path = tmp_path / 'batch1_pcm16_16000_1700000000.bin'
    path.write_bytes(_pcm16_bin_bytes(frame_samples=32, frames=3))
    assert _frame_count(str(path)) == 3


# --- canonical_pcm: declared-shape and container faults. ---


def test_canonical_rejects_three_channels_as_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(3, 2, 16000, 4))
    with pytest.raises(StagedAudioInvalid, match='^unsupported sync PCM format$'):
        canonical_pcm(path)


def test_canonical_rejects_zero_channels_as_typed(tmp_path) -> None:
    """Wave refuses to open a 0-channel container at all: container verdict."""
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(0, 2, 16000, 4))
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio container$'):
        canonical_pcm(path)


def test_canonical_rejects_width_five_as_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 5, 16000, 4))
    with pytest.raises(StagedAudioInvalid, match='^unsupported sync PCM format$'):
        canonical_pcm(path)


def test_canonical_rejects_rate_below_floor_as_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 7999, 4))
    with pytest.raises(StagedAudioInvalid, match='^unsupported sync PCM format$'):
        canonical_pcm(path)


def test_canonical_rejects_rate_above_ceiling_as_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 48001, 4))
    with pytest.raises(StagedAudioInvalid, match='^unsupported sync PCM format$'):
        canonical_pcm(path)


def test_canonical_garbage_container_is_typed_not_wave_error(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', b'NOTRIFF' + b'\0' * 64)
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio container$'):
        canonical_pcm(path)


def test_canonical_truncated_container_is_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 16000, 64)[:30])
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio container$'):
        canonical_pcm(path)


def test_canonical_stereo_at_rate_stays_canonical(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(2, 2, 16000, 4))
    pcm = canonical_pcm(path)
    assert isinstance(pcm, bytes)
    assert len(pcm) == 8


def test_canonical_type_is_value_error_subclass() -> None:
    assert issubclass(StagedAudioInvalid, ValueError)


def test_canonical_legacy_value_error_handlers_still_catch(tmp_path) -> None:
    """Every existing ``except ValueError`` caller keeps catching the typed fault."""
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 7999, 4))
    caught = False
    try:
        canonical_pcm(path)
    except ValueError:
        caught = True
    assert caught


# --- decode_units: ceiling and preservation faults. ---


def test_decode_units_zero_ceiling_is_typed(tmp_path) -> None:
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    with pytest.raises(StagedAudioInvalid, match='^invalid dedicated capture-unit ceiling$'):
        _drain(decode_units([str(path)], max_seconds=0))


def test_decode_units_negative_ceiling_is_typed(tmp_path) -> None:
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    with pytest.raises(StagedAudioInvalid, match='^invalid dedicated capture-unit ceiling$'):
        _drain(decode_units([str(path)], max_seconds=-1))


def test_decode_units_over_horizon_ceiling_is_typed(tmp_path) -> None:
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    with pytest.raises(StagedAudioInvalid, match='^invalid dedicated capture-unit ceiling$'):
        _drain(decode_units([str(path)], max_seconds=7201))


def test_decode_units_nan_ceiling_is_typed(tmp_path) -> None:
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    with pytest.raises(StagedAudioInvalid, match='^invalid dedicated capture-unit ceiling$'):
        _drain(decode_units([str(path)], max_seconds=math.nan))


def test_decode_units_infinite_ceiling_is_typed(tmp_path) -> None:
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    with pytest.raises(StagedAudioInvalid, match='^invalid dedicated capture-unit ceiling$'):
        _drain(decode_units([str(path)], max_seconds=math.inf))


def test_decode_units_misaligned_frame_bundle_is_typed(tmp_path) -> None:
    """A frame whose length decodes but never aligns to PCM16 drops at the
    shared decoder; the bundle check must name the fault, not stay anonymous."""
    good = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    bad = _bin_path(tmp_path, 'batch2_pcm16_16000_1700000010.bin', struct.pack('<I', 3) + b'\1\2\3')
    with pytest.raises(StagedAudioInvalid, match='^sync decode did not preserve every uploaded frame$'):
        _drain(decode_units([str(good), str(bad)]))


def test_decode_units_happy_bundle_yields_units(tmp_path) -> None:
    good = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes(frame_samples=32, frames=1))
    second = _bin_path(tmp_path, 'batch2_pcm16_16000_1700000010.bin', _pcm16_bin_bytes(frame_samples=32, frames=1))
    units = _drain(decode_units([str(good), str(second)]))
    assert len(units) == 1
    assert units[0].capture_at == 1700000000
    # The 10 s wall gap between the two files is padded as silence and joined:
    # 32 + 160000 - 32 + 32... net 160032 canonical frames in one unit.
    assert units[0].duration_seconds == 160032 / RATE


def test_decode_units_deterministic_fault_repeats_identically(tmp_path) -> None:
    """The doctrine's reason: the same bytes fail the same way every attempt."""
    path = _bin_path(tmp_path, 'batch1_pcm16_16000_1700000000.bin', _pcm16_bin_bytes())
    faults = []
    for _ in range(2):
        with pytest.raises(StagedAudioInvalid) as caught:
            _drain(decode_units([str(path)], max_seconds=0))
        faults.append((type(caught.value).__name__, str(caught.value)))
    assert faults[0] == faults[1]
    assert 'StagedAudioInvalid' in faults[0][0]


# --- cap-hold admission: the held-WAV adapter joins the doctrine. ---


def test_wav_units_empty_held_audio_is_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 16000, 0))
    with pytest.raises(StagedAudioInvalid, match='^empty held audio$'):
        _drain(wav_units(str(path), 1700000000.0, 3600))


def test_wav_units_corrupt_held_container_is_typed(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', b'JUNKJUNK' + b'\0' * 32)
    with pytest.raises(StagedAudioInvalid, match='^invalid sync audio container$'):
        _drain(wav_units(str(path), 1700000000.0, 3600))


def test_wav_units_valid_held_audio_yields_one_unit(tmp_path) -> None:
    path = _write_wav(tmp_path, 'held.wav', _wav_bytes(1, 2, 16000, 32))
    units = _drain(wav_units(str(path), 1700000000.0, 3600))
    assert len(units) == 1
    assert units[0].capture_at == 1700000000.0
    assert units[0].duration_seconds == 32 / RATE
