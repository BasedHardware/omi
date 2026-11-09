"""The encrypted retained-frame guard matrix: header truncations at every byte
position, declared sizes around the 28-byte minimum, payload shortfalls at
every boundary, and authentication faults from wrong keys or tampered bytes -
each pinned to its exact typed message through the real decode_source.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import struct

import pytest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.batch_pipeline.source_audio import RetainedAudioInvalid, decode_source

KEY = b"\x0a" * 32
PCM = b"\x00\x02" * 160


def enc_frame(key, payload):
    nonce = b'\n' * 12
    sealed = AESGCM(key).encrypt(nonce, payload, None)
    return struct.pack('>I', 12 + len(sealed)) + nonce + sealed


def enc_ref():
    return {'path': 'chunks/o/c/x.bin.enc'}


def test_full_header_frame_roundtrips():
    body = enc_frame(KEY, PCM)
    assert decode_source(body, enc_ref(), KEY) == PCM


def test_header_of_1_bytes_is_typed_truncated():
    body = enc_frame(KEY, PCM)[:1]
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(body, enc_ref(), KEY)


def test_header_of_2_bytes_is_typed_truncated():
    body = enc_frame(KEY, PCM)[:2]
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(body, enc_ref(), KEY)


def test_header_of_3_bytes_is_typed_truncated():
    body = enc_frame(KEY, PCM)[:3]
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_size_0_below_minimum_is_typed_invalid():
    body = struct.pack('>I', 0) + b'\x00' * 64
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_size_1_below_minimum_is_typed_invalid():
    body = struct.pack('>I', 1) + b'\x00' * 64
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_size_27_below_minimum_is_typed_invalid():
    body = struct.pack('>I', 27) + b'\x00' * 64
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_28_with_27_payload_bytes_is_typed_invalid():
    body = struct.pack('>I', 28) + b'\x00' * 27
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_28_with_28_payload_bytes_is_typed_retained():
    body = struct.pack('>I', 28) + b'\x00' * 28
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_40_with_39_payload_bytes_is_typed_invalid():
    body = struct.pack('>I', 40) + b'\x00' * 39
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_40_with_40_payload_bytes_is_typed_retained():
    body = struct.pack('>I', 40) + b'\x00' * 40
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_64_with_63_payload_bytes_is_typed_invalid():
    body = struct.pack('>I', 64) + b'\x00' * 63
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_64_with_64_payload_bytes_is_typed_retained():
    body = struct.pack('>I', 64) + b'\x00' * 64
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_size_28_is_the_minimum_authenticatable_frame():
    nonce = b'\n' * 12
    sealed = AESGCM(KEY).encrypt(nonce, PCM, None)
    frame = nonce + sealed
    body = struct.pack('>I', len(frame)) + frame
    assert decode_source(body, enc_ref(), KEY) == PCM


def test_tampering_the_head_byte_is_typed_authentication():
    body = enc_frame(KEY, PCM)
    tampered = body[: len(body) // 3] + bytes([body[len(body) // 3] ^ 1]) + body[len(body) // 3 + 1 :]
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(tampered, enc_ref(), KEY)


def test_tampering_the_mid_byte_is_typed_authentication():
    body = enc_frame(KEY, PCM)
    mid = len(body) // 2
    tampered = body[:mid] + bytes([body[mid] ^ 1]) + body[mid + 1 :]
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(tampered, enc_ref(), KEY)


def test_tampering_the_tail_byte_is_typed_authentication():
    body = enc_frame(KEY, PCM)
    tampered = body[:-1] + bytes([body[-1] ^ 1])
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(tampered, enc_ref(), KEY)


def test_wrong_key_short_key_is_typed_authentication():
    body = enc_frame(b'\x0b' * 16, PCM)
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_wrong_key_wrong_owner_is_typed_authentication():
    body = enc_frame(b'\x0c' * 32, PCM)
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_wrong_key_zero_key_is_typed_authentication():
    body = enc_frame(bytes(32), PCM)
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, enc_ref(), KEY)


def test_two_frames_roundtrip_through_one_decrypt_loop():
    body = enc_frame(KEY, PCM[:80]) + enc_frame(KEY, PCM[80:])
    assert decode_source(body, enc_ref(), KEY) == PCM


def test_frame_boundary_after_decrypt_leaves_no_residue():
    body = enc_frame(KEY, PCM) + b'x'
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(body, enc_ref(), KEY)


def test_declared_size_larger_than_the_source_budget_is_typed():
    body = struct.pack('>I', 4096)
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)


def test_ciphertext_of_the_maximum_declared_size_that_is_short_is_typed():
    body = struct.pack('>I', 28) + b'\x00' * 27
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, enc_ref(), KEY)
