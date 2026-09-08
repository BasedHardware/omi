"""Regression: an unsupported codec/sample_rate must be rejected before the decoder is built.

routers.transcribe._stream_handler constructs the native opus/lc3 decoders
(opuslib.Decoder(sample_rate, 1), lc3py.Decoder(frame_duration, sample_rate)) before its main
try block. An opus sample_rate outside opuslib's supported set, or a bare 'lc3' codec (which
normalizes to a None frame duration), raised OpusError/TypeError that escaped the ASGI handler
as an unclean 1006 close. validate_audio_format is checked at connect so those requests close
cleanly (1003) instead.
"""

from utils.transcribe_decisions import OPUS_SUPPORTED_SAMPLE_RATES, validate_audio_format


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
