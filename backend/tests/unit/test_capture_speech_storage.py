"""Synthetic storage limits run before decoding/parsing can allocate without a cap."""

import json
import zlib
from unittest.mock import MagicMock

import pytest

from database import capture_speech as storage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'synthetic-storage-owner'
SEGMENTS = [
    {'text': 'A synthetic telescope observes orange stars', 'start': 0, 'end': 5, 'audio_alignment': 'unplaced'}
]


def test_list_and_compressed_storage_preserve_immutable_alignment_only():
    raw = [dict(SEGMENTS[0], speaker_id=42, is_user=True, original_text='a correction projection')]
    assert storage.decode_capture_segments(UID, raw, False) == SEGMENTS
    assert storage.decode_capture_segments(UID, zlib.compress(json.dumps(raw).encode()), True) == SEGMENTS
    assert raw[0]['speaker_id'] == 42


@pytest.mark.parametrize('compressed', [True, False])
def test_encrypted_storage_uses_account_decryption(monkeypatch, compressed):
    payload = json.dumps(SEGMENTS)
    decrypted = zlib.compress(payload.encode()).hex() if compressed else payload
    decrypt = MagicMock(return_value=decrypted)
    monkeypatch.setattr(storage.encryption, 'decrypt', decrypt)
    assert storage.decode_capture_segments(UID, 'encrypted-fixture', compressed) == SEGMENTS
    decrypt.assert_called_once_with('encrypted-fixture', UID)


def test_decryption_failure_never_accepts_parseable_plaintext(monkeypatch):
    raw = zlib.compress(json.dumps(SEGMENTS).encode()).hex()
    monkeypatch.setattr(storage.encryption, 'decrypt', lambda value, uid: value)
    parse = MagicMock(side_effect=AssertionError('must reject before JSON parsing'))
    monkeypatch.setattr(storage.json, 'loads', parse)
    with pytest.raises(storage._DecodeRejected, match='decode_invalid'):
        storage.decode_capture_segments(UID, raw, True)
    parse.assert_not_called()


@pytest.mark.parametrize('kind', ['bytes', 'encrypted'])
def test_stored_input_cap_runs_before_decryption_or_decompression(monkeypatch, kind):
    data = b'x' * (storage.MAX_STORED_TRANSCRIPT_BYTES + 1)
    raw = data if kind == 'bytes' else data.decode()
    decrypt = MagicMock(side_effect=AssertionError('must not decrypt oversized input'))
    decompress = MagicMock(side_effect=AssertionError('must not decompress oversized input'))
    monkeypatch.setattr(storage.encryption, 'decrypt', decrypt)
    monkeypatch.setattr(storage.zlib, 'decompressobj', decompress)
    with pytest.raises(storage._DecodeRejected, match='decode_bounds'):
        storage.decode_capture_segments(UID, raw, True)
    decrypt.assert_not_called()
    decompress.assert_not_called()


def test_high_expansion_payload_abstains_before_json_parser(monkeypatch):
    raw = zlib.compress(b' ' * (storage.MAX_DECODED_TRANSCRIPT_BYTES + 1))
    parse = MagicMock(side_effect=AssertionError('overflow must not reach JSON parser'))
    monkeypatch.setattr(storage.json, 'loads', parse)
    with pytest.raises(storage._DecodeRejected, match='decode_bounds'):
        storage.decode_capture_segments(UID, raw, True)
    parse.assert_not_called()


@pytest.mark.parametrize('change', ['truncated', 'trailing'])
def test_invalid_compressed_frames_abstain_before_json_parser(monkeypatch, change):
    raw = zlib.compress(json.dumps(SEGMENTS).encode())
    raw = raw[:-2] if change == 'truncated' else raw + b'trailing-data'
    parse = MagicMock(side_effect=AssertionError('invalid frame must not reach JSON parser'))
    monkeypatch.setattr(storage.json, 'loads', parse)
    with pytest.raises(storage._DecodeRejected, match='decode_invalid'):
        storage.decode_capture_segments(UID, raw, True)
    parse.assert_not_called()


@pytest.mark.parametrize('case', ['segments', 'line_chars', 'total_chars', 'shape'])
def test_structured_payloads_respect_matcher_bounds(case):
    if case == 'segments':
        raw = SEGMENTS * (storage.MAX_CAPTURE_SEGMENTS + 1)
    elif case == 'line_chars':
        raw = [dict(SEGMENTS[0], text='x' * (storage.MAX_CAPTURE_SEGMENT_CHARS + 1))]
    elif case == 'total_chars':
        raw = [dict(SEGMENTS[0], text='x' * storage.MAX_CAPTURE_SEGMENT_CHARS)] * 129
    else:
        raw = {'text': 'unexpected document shape'}
    with pytest.raises(storage._DecodeRejected):
        storage.decode_capture_segments(UID, raw, False)


def test_snapshot_overflow_returns_metadata_abstention_without_fingerprinting(monkeypatch):
    store = StrictFirestore()
    store.rows[('users', UID, 'conversations', 'capture')] = {
        'id': 'capture',
        'transcript_segments': zlib.compress(b' ' * (storage.MAX_DECODED_TRANSCRIPT_BYTES + 1)),
        'transcript_segments_compressed': True,
    }
    fingerprint = MagicMock(side_effect=AssertionError('overflow cannot become evidence'))
    monkeypatch.setattr(storage, 'transcript_fingerprint', fingerprint)
    row, digest = storage.get_shared_speech_snapshot(UID, 'capture', firestore_client=store)
    assert row['_shared_speech_rejection'] == 'decode_bounds' and row['transcript_segments'] == []
    assert digest is None
    fingerprint.assert_not_called()
