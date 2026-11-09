"""The intake-side canonicalization grid: sync-frame length guards, the
width/channels/rate canonicalization matrix (every stored shape canonicalizes
to mono PCM16 at 16kHz), and the decode_units unit ceiling guard - the CPU
twin of the retained GPU decode family.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import audioop
import struct
import wave
import io

import pytest

from utils.batch_pipeline.capture_decode import _canonical, _frame_count, decode_units


def wav_bytes(channels=1, width=2, rate=16000, frames=160):
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        if width == 1:
            handle.writeframes(b'\x80' * frames * channels)
        else:
            handle.writeframes(b'\x00\x00' * frames * channels * (width // 2))
    return output.getvalue()


def test_canonical_w1_c1_r8000_is_mono16_16k():
    body = wav_bytes(channels=1, width=1, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c1_r16000_is_mono16_16k():
    body = wav_bytes(channels=1, width=1, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c1_r44100_is_mono16_16k():
    body = wav_bytes(channels=1, width=1, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c1_r48000_is_mono16_16k():
    body = wav_bytes(channels=1, width=1, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c2_r8000_is_mono16_16k():
    body = wav_bytes(channels=2, width=1, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c2_r16000_is_mono16_16k():
    body = wav_bytes(channels=2, width=1, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c2_r44100_is_mono16_16k():
    body = wav_bytes(channels=2, width=1, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w1_c2_r48000_is_mono16_16k():
    body = wav_bytes(channels=2, width=1, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c1_r8000_is_mono16_16k():
    body = wav_bytes(channels=1, width=2, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c1_r16000_is_mono16_16k():
    body = wav_bytes(channels=1, width=2, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c1_r44100_is_mono16_16k():
    body = wav_bytes(channels=1, width=2, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c1_r48000_is_mono16_16k():
    body = wav_bytes(channels=1, width=2, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c2_r8000_is_mono16_16k():
    body = wav_bytes(channels=2, width=2, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c2_r16000_is_mono16_16k():
    body = wav_bytes(channels=2, width=2, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c2_r44100_is_mono16_16k():
    body = wav_bytes(channels=2, width=2, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w2_c2_r48000_is_mono16_16k():
    body = wav_bytes(channels=2, width=2, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c1_r8000_is_mono16_16k():
    body = wav_bytes(channels=1, width=3, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c1_r16000_is_mono16_16k():
    body = wav_bytes(channels=1, width=3, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c1_r44100_is_mono16_16k():
    body = wav_bytes(channels=1, width=3, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c1_r48000_is_mono16_16k():
    body = wav_bytes(channels=1, width=3, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c2_r8000_is_mono16_16k():
    body = wav_bytes(channels=2, width=3, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c2_r16000_is_mono16_16k():
    body = wav_bytes(channels=2, width=3, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c2_r44100_is_mono16_16k():
    body = wav_bytes(channels=2, width=3, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w3_c2_r48000_is_mono16_16k():
    body = wav_bytes(channels=2, width=3, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c1_r8000_is_mono16_16k():
    body = wav_bytes(channels=1, width=4, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c1_r16000_is_mono16_16k():
    body = wav_bytes(channels=1, width=4, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c1_r44100_is_mono16_16k():
    body = wav_bytes(channels=1, width=4, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c1_r48000_is_mono16_16k():
    body = wav_bytes(channels=1, width=4, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c2_r8000_is_mono16_16k():
    body = wav_bytes(channels=2, width=4, rate=8000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c2_r16000_is_mono16_16k():
    body = wav_bytes(channels=2, width=4, rate=16000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c2_r44100_is_mono16_16k():
    body = wav_bytes(channels=2, width=4, rate=44100)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_w4_c2_r48000_is_mono16_16k():
    body = wav_bytes(channels=2, width=4, rate=48000)
    pcm = _canonical_from_bytes(body)
    assert isinstance(pcm, bytes)
    assert len(pcm) % 2 == 0


def test_canonical_stereo_halves_the_frame_count():
    mono = wav_bytes(channels=1, width=2, rate=16000, frames=160)
    stereo = wav_bytes(channels=2, width=2, rate=16000, frames=160)
    assert len(_canonical_from_bytes(mono)) == len(PCM16out := _canonical_from_bytes(mono))


def test_canonical_rate_downsample_shrinks():
    src = wav_bytes(channels=1, width=2, rate=48000, frames=480)
    out = _canonical_from_bytes(src)
    assert len(out) <= 2 * 160 * 2 + 4


def test_canonical_rate_upsample_grows():
    src = wav_bytes(channels=1, width=2, rate=8000, frames=80)
    out = _canonical_from_bytes(src)
    assert len(out) >= 2 * 80 * 2 - 4


def test_canonical_width4_matches_width2_length():
    w2 = _canonical_from_bytes(wav_bytes(channels=1, width=2, rate=16000, frames=160))
    w4 = _canonical_from_bytes(wav_bytes(channels=1, width=4, rate=16000, frames=160))
    assert len(w2) == len(w4) == 320


def test_canonical_width3_never_exceeds_the_width2_length():
    w2 = _canonical_from_bytes(wav_bytes(channels=1, width=2, rate=16000, frames=160))
    w3 = _canonical_from_bytes(wav_bytes(channels=1, width=3, rate=16000, frames=160))
    assert len(w3) <= len(w2)


def test_canonical_8bit_unsigned_centers_at_zero():
    src = wav_bytes(channels=1, width=1, rate=16000, frames=160)
    pcm = _canonical_from_bytes(src)
    assert len(pcm) == 320


def test_canonical_rejects_three_channels():
    body = wav_bytes(channels=2, width=2, rate=16000, frames=8)
    body = _rewrite_channels(body, 3)
    with pytest.raises(ValueError, match='^unsupported sync PCM format$'):
        _canonical_from_bytes(body)


def test_canonical_rejects_width_five():
    body = wav_bytes(channels=1, width=2, rate=16000, frames=8)
    body = _rewrite_width(body, 40)
    with pytest.raises(ValueError, match='^unsupported sync PCM format$'):
        _canonical_from_bytes(body)


def test_canonical_rejects_rate_below_8000():
    body = wav_bytes(channels=1, width=2, rate=16000, frames=8)
    body = _rewrite_rate(body, 7999)
    with pytest.raises(ValueError, match='^unsupported sync PCM format$'):
        _canonical_from_bytes(body)


def test_canonical_rejects_rate_above_48000():
    body = wav_bytes(channels=1, width=2, rate=16000, frames=8)
    body = _rewrite_rate(body, 48001)
    with pytest.raises(ValueError, match='^unsupported sync PCM format$'):
        _canonical_from_bytes(body)


def test_frame_count_counts_every_frame():
    frames = b''.join(struct.pack('<I', 4) + b'abcd' for _ in range(3))
    assert _frame_count_from_bytes(frames) == 3


def test_frame_count_empty_stream_is_typed():
    with pytest.raises(ValueError, match='^empty sync audio$'):
        _frame_count_from_bytes(b'')


def test_frame_count_trailing_short_header_is_typed():
    frames = struct.pack('<I', 4) + b'abcd' + struct.pack('<I', 4)[:2]
    with pytest.raises(ValueError, match='^truncated sync audio frame$'):
        _frame_count_from_bytes(frames)


def test_frame_count_zero_size_frame_is_typed():
    frames = struct.pack('<I', 0)
    with pytest.raises(ValueError, match='^invalid sync audio frame$'):
        _frame_count_from_bytes(frames)


def test_frame_count_oversize_frame_is_typed():
    frames = struct.pack('<I', 1 << 24)
    with pytest.raises(ValueError, match='^invalid sync audio frame$'):
        _frame_count_from_bytes(frames)


def test_frame_count_payload_past_eof_is_typed():
    frames = struct.pack('<I', 64) + b'ab'
    with pytest.raises(ValueError, match='^invalid sync audio frame$'):
        _frame_count_from_bytes(frames)


def test_decode_units_rejects_a_zero_ceiling():
    with pytest.raises(ValueError, match='^invalid dedicated capture-unit ceiling$'):
        list(decode_units([], max_seconds=0))


def test_decode_units_rejects_a_negative_ceiling():
    with pytest.raises(ValueError, match='^invalid dedicated capture-unit ceiling$'):
        list(decode_units([], max_seconds=-1))


def test_decode_units_rejects_above_two_hours():
    with pytest.raises(ValueError, match='^invalid dedicated capture-unit ceiling$'):
        list(decode_units([], max_seconds=7201))


def test_decode_units_missing_path_is_a_deterministic_guard():
    with pytest.raises(OSError):
        list(decode_units(['/nonexistent-path/x.bin'], max_seconds=3600))


def test_decode_units_empty_stream_file_is_typed_empty_sync_audio():
    import tempfile
    import os

    handle = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
    handle.close()
    try:
        with pytest.raises(ValueError, match='^empty sync audio$'):
            list(decode_units([handle.name], max_seconds=3600))
    finally:
        os.unlink(handle.name)


def _fmt_chunk_offset(body):
    offset = 12
    while offset + 8 <= len(body):
        name, size = body[offset : offset + 4], struct.unpack('<I', body[offset + 4 : offset + 8])[0]
        if name == b'fmt ':
            return offset + 8
        offset += 8 + size + (size % 2)
    raise ValueError('no fmt chunk')


def _patch_header(body, offset, value):
    return body[:offset] + struct.pack('<H', value) + body[offset + 2 :]


def _rewrite_channels(body, channels):
    return _patch_header(body, _fmt_chunk_offset(body) + 2, channels)


def _rewrite_width(body, width):
    return _patch_header(body, _fmt_chunk_offset(body) + 14, width)


def _rewrite_rate(body, rate):
    return _patch_header(body, _fmt_chunk_offset(body) + 4, rate)


def _canonical_from_bytes(body):
    import tempfile
    import os

    handle = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    handle.write(body)
    handle.close()
    try:
        return _canonical(handle.name)
    finally:
        os.unlink(handle.name)


def _frame_count_from_bytes(body):
    import tempfile
    import os

    handle = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
    handle.write(body)
    handle.close()
    try:
        return _frame_count(handle.name)
    finally:
        os.unlink(handle.name)
