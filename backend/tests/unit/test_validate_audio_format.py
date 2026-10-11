"""Regression: an unsupported codec/sample_rate must be rejected before the decoder is built.

routers.transcribe._stream_handler constructs the native opus/lc3 decoders
(opuslib.Decoder(sample_rate, 1), lc3py.Decoder(frame_duration, sample_rate)) before its main
try block. An opus sample_rate outside opuslib's supported set, or a bare 'lc3' codec (which
normalizes to a None frame duration), raised OpusError/TypeError that escaped the ASGI handler
as an unclean 1006 close. validate_audio_format is checked at connect so those requests close
cleanly (1003) instead.

sample_rate is also bounded for every codec: for pcm/aac it used to pass straight through to
AudioRingBuffer, which allocates duration * rate * 2 bytes up front, so sample_rate=30000000 asked
for ~3.6 GB and OOM-killed the listen pod along with every live session on it.
"""

import pytest

from utils.transcribe_decisions import (
    OPUS_SUPPORTED_SAMPLE_RATES,
    SUPPORTED_SAMPLE_RATES,
    validate_audio_format,
)


def test_supported_formats_pass():
    assert validate_audio_format('opus', 16000) is None
    assert validate_audio_format('opus_fs320', 48000) is None
    assert validate_audio_format('lc3_fs1030', 16000) is None
    assert validate_audio_format('pcm8', 8000) is None
    assert validate_audio_format('pcm16', 16000) is None
    assert validate_audio_format('aac', 16000) is None


def test_opus_rejects_a_rate_opuslib_cannot_decode():
    # 44100 is not one of opus's supported rates; opuslib.Decoder(44100, 1) would raise OpusError.
    reason = validate_audio_format('opus', 44100)
    assert reason is not None
    assert '44100' in reason
    assert validate_audio_format('opus_fs320', 44100) is not None
    # Every advertised opus rate is accepted.
    for rate in OPUS_SUPPORTED_SAMPLE_RATES:
        assert validate_audio_format('opus', rate) is None


def test_bare_lc3_is_rejected_but_the_known_variant_is_not():
    # bare 'lc3' normalizes to a None frame duration -> lc3py.Decoder(None, ...) TypeError.
    assert validate_audio_format('lc3', 16000) is not None
    # the recognized variant carries a frame duration and must still pass.
    assert validate_audio_format('lc3_fs1030', 16000) is None


@pytest.mark.parametrize('codec', ['pcm', 'pcm8', 'pcm16', 'aac', 'opus', 'opus_fs320', 'lc3_fs1030'])
@pytest.mark.parametrize('sample_rate', [30_000_000, 2**31 - 1, 96_000, 0, -1, -16000, 16001])
def test_every_codec_rejects_a_non_standard_rate(codec, sample_rate):
    reason = validate_audio_format(codec, sample_rate)
    assert reason is not None
    assert str(sample_rate) in reason


@pytest.mark.parametrize('codec', ['pcm', 'pcm8', 'pcm16', 'aac'])
def test_non_opus_codecs_accept_every_supported_rate(codec):
    for rate in SUPPORTED_SAMPLE_RATES:
        assert validate_audio_format(codec, rate) is None


def test_rejection_reason_fits_a_websocket_close_frame():
    # The route closes with this string as the reason; RFC 6455 caps it at 123 bytes.
    reason = validate_audio_format('pcm16', int('9' * 200))
    assert reason is not None
    assert len(reason.encode()) <= 123


def test_rates_released_clients_send_stay_supported():
    # 8000: /v4/listen default (pcm8). 16000: app, desktop, web, firmware. 48000: phone calls (pcm).
    assert validate_audio_format('pcm8', 8000) is None
    assert validate_audio_format('pcm16', 16000) is None
    assert validate_audio_format('pcm', 48000) is None
    assert OPUS_SUPPORTED_SAMPLE_RATES <= SUPPORTED_SAMPLE_RATES
