"""Single-snapshot immutable transcript reads for deterministic capture grouping."""

import json
import zlib
from collections.abc import Mapping

from config.capture_shared_speech import (
    MAX_CAPTURE_SEGMENTS,
    MAX_CAPTURE_CHARS,
    MAX_CAPTURE_SEGMENT_CHARS,
    MAX_STORED_TRANSCRIPT_BYTES,
    MAX_DECODED_TRANSCRIPT_BYTES,
)
from database._client import get_firestore_client
from database.capture_groups import transcript_fingerprint
from utils import encryption


class _DecodeRejected(Exception):
    pass


def _bounded_segments(segments):
    if not isinstance(segments, list):
        raise _DecodeRejected('decode_invalid')
    if len(segments) > MAX_CAPTURE_SEGMENTS:
        raise _DecodeRejected('decode_bounds')
    safe = []
    chars = 0
    for segment in segments:
        if not isinstance(segment, Mapping) or not isinstance(segment.get('text'), str):
            raise _DecodeRejected('decode_invalid')
        chars += len(segment['text'])
        if len(segment['text']) > MAX_CAPTURE_SEGMENT_CHARS or chars > MAX_CAPTURE_CHARS:
            raise _DecodeRejected('decode_bounds')
        for key in ('start', 'end'):
            value = segment.get(key)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                raise _DecodeRejected('decode_invalid')
        alignment = segment.get('audio_alignment')
        if alignment is not None and (not isinstance(alignment, str) or len(alignment) > 64):
            raise _DecodeRejected('decode_invalid')
        safe.append({key: segment[key] for key in ('text', 'start', 'end', 'audio_alignment') if key in segment})
    return safe


def decode_capture_segments(uid, raw, compressed):
    """Bound stored input and decompressed output before parsing the storage JSON.

    Same bytes/hex-encrypted/list formats as the verified canonical decoder.
    Only immutable text/timing/alignment survive; no speaker or correction reads.
    """
    if isinstance(raw, list):
        return _bounded_segments(raw)
    try:
        if isinstance(raw, str):
            if len(raw) > MAX_STORED_TRANSCRIPT_BYTES or len(raw.encode('utf-8')) > MAX_STORED_TRANSCRIPT_BYTES:
                raise _DecodeRejected('decode_bounds')
            plaintext = encryption.decrypt(raw, uid)
            if plaintext == raw:
                raise _DecodeRejected('decode_invalid')
            if len(plaintext) > MAX_DECODED_TRANSCRIPT_BYTES:
                raise _DecodeRejected('decode_bounds')
            if compressed:
                if len(plaintext) > MAX_STORED_TRANSCRIPT_BYTES * 2:
                    raise _DecodeRejected('decode_bounds')
                stored = bytes.fromhex(plaintext)
            else:
                stored = plaintext.encode('utf-8')
        elif isinstance(raw, (bytes, bytearray)) and compressed:
            if len(raw) > MAX_STORED_TRANSCRIPT_BYTES:
                raise _DecodeRejected('decode_bounds')
            stored = bytes(raw)
        else:
            raise _DecodeRejected('decode_invalid')
        if compressed:
            if len(stored) > MAX_STORED_TRANSCRIPT_BYTES:
                raise _DecodeRejected('decode_bounds')
            decoder = zlib.decompressobj()
            decoded = decoder.decompress(stored, MAX_DECODED_TRANSCRIPT_BYTES + 1)
            if len(decoded) > MAX_DECODED_TRANSCRIPT_BYTES or decoder.unconsumed_tail:
                raise _DecodeRejected('decode_bounds')
            if not decoder.eof or decoder.unused_data:
                raise _DecodeRejected('decode_invalid')
        else:
            decoded = stored
            if len(decoded) > MAX_DECODED_TRANSCRIPT_BYTES:
                raise _DecodeRejected('decode_bounds')
        return _bounded_segments(json.loads(decoded.decode('utf-8')))
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError, zlib.error):
        raise _DecodeRejected('decode_invalid') from None


def get_shared_speech_snapshot(uid: str, conversation_id: str, *, firestore_client=None):
    """Never project mutable correction overlays or perform their additional reads.

    Corrected captures retain their metadata and abstain before decoding. The
    matcher and commit guard both reject corrections, including concurrent edits.
    """
    client = firestore_client or get_firestore_client()
    snapshot = client.collection('users').document(uid).collection('conversations').document(conversation_id).get()
    raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
    if not raw:
        return None, None
    row = dict(raw)
    row.pop('_shared_speech_rejection', None)
    if raw.get('has_transcript_corrections') or raw.get('transcript_correction_overlay') is not None:
        row['transcript_segments'] = []
        return row, None  # never eligible, and no payload decoding/fingerprinting is necessary
    else:
        try:
            row['transcript_segments'] = decode_capture_segments(
                uid, raw.get('transcript_segments') or [], bool(raw.get('transcript_segments_compressed'))
            )
        except _DecodeRejected as error:
            row.update(transcript_segments=[], _shared_speech_rejection=str(error))
            return row, None
    return row, transcript_fingerprint(raw)
