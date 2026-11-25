"""Storage equality for the v3 projection's already-fenced snapshots."""

import json
import zlib
from collections.abc import Callable
from threading import Lock
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
from database import conversations
from utils.conversations.v3 import metrics
from utils.conversations.speaker_grouping_storage import FIELD as SPEAKER_GROUPING, reveal_segments
from utils.encryption import decrypt
from utils.home_feed.projection import DISPLAY, VERSION, reveal_display
from utils.observability.fallback import record_fallback
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD

_COMPRESSED_FIELDS = {
    'user_corrections': 'user_corrections_compressed',
    'manual_speaker_assignments': 'manual_speaker_assignments_compressed',
    OPEN_LOOP_EXTRACTIONS_FIELD: OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD,
    MATCH_SCORES: None,  # This codec always compresses.
}


_fallback_lock = Lock()
_fallback_reported = False


def _write_on_uncertainty() -> bool:
    global _fallback_reported
    metrics.safe_metric(lambda: metrics.EQUALITY_UNAVAILABLE.inc())
    with _fallback_lock:
        if _fallback_reported:
            return False
        _fallback_reported = True
    metrics.safe_metric(
        lambda: record_fallback(
            component='other', from_mode='elide_write', to_mode='write', reason='other', outcome='degraded'
        )
    )
    return False


def or_write(compare: Callable[..., bool], *args: Any) -> bool:
    """Run an optional comparison before staging a write."""
    try:
        return compare(*args)
    except Exception:
        return _write_on_uncertainty()


def same_value(left: Any, right: Any) -> bool:
    """Use Firestore's typed encoding, including exact timestamps and floating point bits.

    Unknown values and transforms have no literal Value encoding and must be written.
    """
    if encode_value is None or Value is None:
        return _write_on_uncertainty()
    try:
        return Value.pb(encode_value(left)).SerializeToString(deterministic=True) == Value.pb(
            encode_value(right)
        ).SerializeToString(deterministic=True)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return _write_on_uncertainty()


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


def _grouping_payloads(uid: str, segments: list) -> list:
    # The reader enforces authentication, binding, and both per-sidecar and
    # aggregate byte limits. Reveal on copies so its TTL filtering never
    # participates in equality or removes anything from a write payload.
    if not reveal_segments([dict(segment) for segment in segments], uid, report_rejection=False):
        raise ValueError('unreadable grouping sidecar')
    return [
        (
            {
                **segment,
                SPEAKER_GROUPING: json.loads(
                    _plaintext(uid, segment[SPEAKER_GROUPING]), object_pairs_hook=_unique_fields
                ),
            }
            if SPEAKER_GROUPING in segment
            else segment
        )
        for segment in segments
    ]


def _decode_comparable_transcript(uid: str, value: bytes | str) -> list:
    # Public chat applies the strict inline limits. Compare the full codec output
    # because its public safe-field projection omits data kept by other readers.
    conversations._decode_public_transcript_segments_bounded(  # pyright: ignore[reportPrivateUsage]
        uid, value, compressed=True, retain_anchors=True
    )
    return _grouping_payloads(
        uid, conversations.decode_transcript_segments_blob(uid, value, True, require_decryption=True)
    )


def _same_transcript(uid: str, left: Any, right: Any) -> bool:
    # Preserve pointer identity without resolving it or opening another read.
    if isinstance(left, dict) or isinstance(right, dict):
        return same_value(left, right)
    if type(left) is not type(right) or not isinstance(left, (bytes, str)):
        return False
    try:
        return same_value(_decode_comparable_transcript(uid, left), _decode_comparable_transcript(uid, right))
    except (ValueError, TypeError, OverflowError, AttributeError, RecursionError, zlib.error):
        return _write_on_uncertainty()


def _same_protected_field(uid: str, field: str, left: Any, right: Any) -> bool:
    if type(left) is not type(right) or not isinstance(left, (bytes, str)):
        return False
    try:
        # This is the codec used by the corrections, assignments, match scores
        # and open-loop readers. Verify authentication explicitly on both sides.
        if isinstance(left, str):
            _plaintext(uid, left)
            _plaintext(uid, right)
        before = conversations._reveal_json_value(left, uid, True)  # pyright: ignore[reportPrivateUsage]
        after = conversations._reveal_json_value(right, uid, True)  # pyright: ignore[reportPrivateUsage]
        expected = list if field in {'user_corrections', MATCH_SCORES} else dict
        if not isinstance(before, expected) or not isinstance(after, expected):
            return _write_on_uncertainty()
        return same_value(before, after)
    except (ValueError, TypeError, OverflowError, AttributeError, RecursionError, zlib.error):
        return _write_on_uncertainty()


def same_outline_cache(uid: str, left: Any, right: Any) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        # Load and save_outline both read the authenticated UTF-8 JSON list.
        before = json.loads(_plaintext(uid, left), object_pairs_hook=_unique_fields)
        after = json.loads(_plaintext(uid, right), object_pairs_hook=_unique_fields)
        if not isinstance(before, list) or not isinstance(after, list):
            return _write_on_uncertainty()
        return same_value(before, after)
    except (ValueError, TypeError, RecursionError):
        return _write_on_uncertainty()


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
        if stored_display is None or planned_display is None:
            return _write_on_uncertainty()
        if not same_value(stored_display, planned_display):
            return False
    for field, value in after.items():
        old = before[field]
        if (
            field == 'transcript_segments'
            and before.get('transcript_segments_compressed') is True
            and after.get('transcript_segments_compressed') is True
        ):
            if not _same_transcript(uid, old, value):
                return False
            continue
        if field in _COMPRESSED_FIELDS and isinstance(value, (bytes, str)):
            marker = _COMPRESSED_FIELDS[field]
            if not same_value(before.get('data_protection_level'), after.get('data_protection_level')):
                return False
            if marker is not None and (before.get(marker) is not True or after.get(marker) is not True):
                return _write_on_uncertainty()
            if not _same_protected_field(uid, field, old, value):
                return False
            continue
        if same_value(old, value) or field == DISPLAY:
            continue
        if field == VERSION and DISPLAY in after and _generated_version(old) and _generated_version(value):
            continue
        return False
    return True
