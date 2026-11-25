"""Storage equality for the v3 projection's already-fenced snapshots."""

import json
import zlib
from typing import Any
from uuid import UUID

try:
    from google.cloud.firestore_v1._helpers import encode_value
    from google.cloud.firestore_v1.types import Value
except ImportError:
    # Some isolated backend entry points run with a file-less Firestore test stub.
    # Without the SDK encoder there is no basis to call two values equal.
    encode_value = None
    Value = None

from config.speaker_match_scores import FIELD as MATCH_SCORES
from utils.conversations.speaker_grouping_storage import FIELD as SPEAKER_GROUPING
from utils.encryption import decrypt
from utils.home_feed.projection import DISPLAY, VERSION, reveal_display
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD

_COMPRESSED_FIELDS = {
    'transcript_segments': 'transcript_segments_compressed',
    'user_corrections': 'user_corrections_compressed',
    'manual_speaker_assignments': 'manual_speaker_assignments_compressed',
    OPEN_LOOP_EXTRACTIONS_FIELD: OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD,
    MATCH_SCORES: None,  # This codec always compresses.
}


def same_value(left: Any, right: Any) -> bool:
    """Use Firestore's typed encoding, including exact timestamps and floating point bits.

    Unknown values and transforms have no literal Value encoding and must be written.
    """
    if encode_value is None or Value is None:
        return False
    try:
        return Value.pb(encode_value(left)).SerializeToString(deterministic=True) == Value.pb(
            encode_value(right)
        ).SerializeToString(deterministic=True)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return False


def same_patch(stored: dict, patch: dict) -> bool:
    return all('.' not in key and key in stored and same_value(stored[key], value) for key, value in patch.items())


def _plaintext(uid: str, blob: str) -> str:
    value = decrypt(blob, uid)
    if value == blob:
        raise ValueError('unverified encrypted field')
    return value


def _unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError('duplicate JSON field')
    return fields


def _json_blob(uid: str, blob: bytes | str, *, compressed: bool) -> Any:
    payload = _plaintext(uid, blob) if isinstance(blob, str) else blob
    if compressed:
        payload = zlib.decompress(bytes.fromhex(payload) if isinstance(payload, str) else payload)
    return json.loads(payload, object_pairs_hook=_unique_fields)


def _grouping_payloads(uid: str, segments: list) -> list:
    return [
        (
            {**segment, SPEAKER_GROUPING: _json_blob(uid, segment[SPEAKER_GROUPING], compressed=False)}
            if SPEAKER_GROUPING in segment
            else segment
        )
        for segment in segments
    ]


def same_blob(uid: str, left: Any, right: Any, *, compressed: bool, transcript: bool = False) -> bool:
    if same_value(left, right):
        return True
    # A pointer change has an independent custody identity. Never resolve it here.
    if type(left) is not type(right) or not isinstance(left, (bytes, str)):
        return False
    try:
        before = _json_blob(uid, left, compressed=compressed)
        after = _json_blob(uid, right, compressed=compressed)
        if transcript and not same_value(before, after):
            before = _grouping_payloads(uid, before)
            after = _grouping_payloads(uid, after)
        return same_value(before, after)
    except (ValueError, TypeError, OverflowError, AttributeError, zlib.error):
        return False


def _generated_version(value: Any) -> bool:
    try:
        if not isinstance(value, str):
            return False
        parsed = UUID(hex=value)
        return parsed.version == 4 and parsed.hex == value
    except ValueError:
        return False


def same_conversation(uid: str, stored: dict, planned: dict) -> bool:
    # The commit hook generates a new version only when a conversation write occurs.
    # Its invalidation bit is meaningful and must still match what that write would produce.
    before = dict(stored)
    after = dict(planned)
    if _generated_version(before.get('home_source_version')):
        before.pop('home_source_version')
        after.pop('home_source_version', None)
        if {'transcript_segments', 'user_corrections'} & after.keys():
            after['home_content_invalidated'] = 'structured' not in after
    if before.keys() != after.keys():
        return False
    if DISPLAY in after:
        stored_display = reveal_display(uid, before[DISPLAY])
        planned_display = reveal_display(uid, after[DISPLAY])
        if stored_display is None or planned_display is None or not same_value(stored_display, planned_display):
            return False
    for field, value in after.items():
        old = before[field]
        if same_value(old, value):
            continue
        if field == DISPLAY:
            continue
        if field == VERSION and DISPLAY in after and _generated_version(old) and _generated_version(value):
            continue
        if field in _COMPRESSED_FIELDS:
            marker = _COMPRESSED_FIELDS[field]
            same_protection = same_value(before.get('data_protection_level'), after.get('data_protection_level'))
            if same_protection and (marker is None or (before.get(marker) is True and after.get(marker) is True)):
                if same_blob(uid, old, value, compressed=True, transcript=field == 'transcript_segments'):
                    continue
        return False
    return True
