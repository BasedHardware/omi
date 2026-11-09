"""Canonical PCM tail boundary grid: the sample-rate floor and ceiling
neighborhoods, odd-length parity guards, float and string rate coercions and
the pass-through identity, each pinned through the real decode_source.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import pytest

from utils.batch_pipeline.source_audio import RetainedAudioInvalid, decode_source

KEY = b"\6" * 32
PCM = b"\x00\x02" * 320


def test_rate_16000_is_the_exact_passthrough():
    assert decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 16000}, KEY) == PCM


def test_rate_floor_neighborhood_7990_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7990}, KEY)


def test_rate_floor_neighborhood_7991_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7991}, KEY)


def test_rate_floor_neighborhood_7992_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7992}, KEY)


def test_rate_floor_neighborhood_7993_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7993}, KEY)


def test_rate_floor_neighborhood_7994_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7994}, KEY)


def test_rate_floor_neighborhood_7995_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7995}, KEY)


def test_rate_floor_neighborhood_7996_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7996}, KEY)


def test_rate_floor_neighborhood_7997_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7997}, KEY)


def test_rate_floor_neighborhood_7998_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7998}, KEY)


def test_rate_floor_neighborhood_7999_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7999}, KEY)


def test_rate_floor_neighborhood_8000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47990_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47990}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47991_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47991}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47992_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47992}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47993_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47993}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47994_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47994}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47995_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47995}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47996_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47996}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47997_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47997}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47998_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47998}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_47999_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 47999}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_48000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48000}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_ceiling_neighborhood_48001_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48001}, KEY)


def test_rate_ceiling_neighborhood_48002_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48002}, KEY)


def test_rate_ceiling_neighborhood_48003_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48003}, KEY)


def test_rate_ceiling_neighborhood_48004_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48004}, KEY)


def test_rate_ceiling_neighborhood_48005_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48005}, KEY)


def test_rate_ceiling_neighborhood_48006_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48006}, KEY)


def test_rate_ceiling_neighborhood_48007_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48007}, KEY)


def test_rate_ceiling_neighborhood_48008_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48008}, KEY)


def test_rate_ceiling_neighborhood_48009_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48009}, KEY)


def test_rate_ceiling_neighborhood_48010_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48010}, KEY)


def test_odd_pcm_length_1_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 1, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_3_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 3, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_5_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 5, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_7_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 7, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_9_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 9, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_11_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 11, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_13_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 13, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_15_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 15, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_17_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 17, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_19_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 19, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_21_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 21, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_23_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 23, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_25_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 25, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_27_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 27, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_29_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 29, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_31_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 31, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_odd_pcm_length_33_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 33, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_even_pcm_length_2_passes_the_parity_guard():
    out = decode_source(b'\x00\x02' * 1, {'path': 'chunks/o/c/x.bin'}, KEY)
    assert out == b'\x00\x02' * 1


def test_even_pcm_length_34_passes_the_parity_guard():
    out = decode_source(b'\x00\x02' * 17, {'path': 'chunks/o/c/x.bin'}, KEY)
    assert out == b'\x00\x02' * 17


def test_even_pcm_length_340_passes_the_parity_guard():
    out = decode_source(b'\x00\x02' * 170, {'path': 'chunks/o/c/x.bin'}, KEY)
    assert out == b'\x00\x02' * 170


def test_even_pcm_length_640_passes_the_parity_guard():
    out = decode_source(b'\x00\x02' * 320, {'path': 'chunks/o/c/x.bin'}, KEY)
    assert out == b'\x00\x02' * 320


def test_rate_string_8000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '8000'}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_bytes_8000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': b'8000'}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_float_8000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000.0}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_float_8000_point_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000.4}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_string_48000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '48000'}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_float_48000_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48000.9}, KEY)
    assert isinstance(out, bytes) and out


def test_rate_string_7999_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '7999'}, KEY)


def test_rate_float_7999_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 7999.9}, KEY)


def test_rate_bytes_7999_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': b'7999'}, KEY)


def test_rate_float_48001_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48001.0}, KEY)


def test_rate_string_48001_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '48001'}, KEY)


def test_missing_rate_passthrough_is_byte_exact():
    assert decode_source(PCM, {'path': 'chunks/o/c/x.bin'}, KEY) == PCM


def test_explicit_16000_beats_the_default():
    assert decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 16000}, KEY) == PCM


def test_rate_8000_doubles_the_sample_count():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)
    assert isinstance(out, bytes) and out
    assert len(out) > len(PCM)


def test_rate_48000_shrinks_the_sample_count():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 48000}, KEY)
    assert isinstance(out, bytes) and out
    assert len(out) < len(PCM)


def test_rate_32000_shrinks_toward_half():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 32000}, KEY)
    assert isinstance(out, bytes) and out
    assert len(out) < len(PCM)


def test_padded_zero_string_rate_is_passthrough():
    assert decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '016000'}, KEY) == PCM


def test_whitespace_string_rate_converts():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': ' 8000'}, KEY)
    assert isinstance(out, bytes) and out


def test_unicode_digit_string_rate_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': '1\\u00b2'}, KEY)


def test_negative_zero_float_rate_is_typed_below_floor():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': -0.0}, KEY)


def test_complex_rate_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': complex(16000, 0)}, KEY)


def test_rate_key_with_extra_unknown_keys_still_passes_through():
    ref = {'path': 'chunks/o/c/x.bin', 'sample_rate': 16000, 'unused': 'x'}
    assert decode_source(PCM, ref, KEY) == PCM


for size in range(1, 17):
    T = None


def test_pcm_tail_body_size_1_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 1, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_2_is_passthrough():
    assert decode_source(b'\x00\x02' * 1, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 1


def test_pcm_tail_body_size_3_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 3, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_4_is_passthrough():
    assert decode_source(b'\x00\x02' * 2, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 2


def test_pcm_tail_body_size_5_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 5, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_6_is_passthrough():
    assert decode_source(b'\x00\x02' * 3, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 3


def test_pcm_tail_body_size_7_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 7, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_8_is_passthrough():
    assert decode_source(b'\x00\x02' * 4, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 4


def test_pcm_tail_body_size_9_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 9, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_10_is_passthrough():
    assert decode_source(b'\x00\x02' * 5, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 5


def test_pcm_tail_body_size_11_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 11, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_12_is_passthrough():
    assert decode_source(b'\x00\x02' * 6, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 6


def test_pcm_tail_body_size_13_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 13, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_14_is_passthrough():
    assert decode_source(b'\x00\x02' * 7, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 7


def test_pcm_tail_body_size_15_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\x00' * 15, {'path': 'chunks/o/c/x.bin'}, KEY)


def test_pcm_tail_body_size_16_is_passthrough():
    assert decode_source(b'\x00\x02' * 8, {'path': 'chunks/o/c/x.bin'}, KEY) == b'\x00\x02' * 8
