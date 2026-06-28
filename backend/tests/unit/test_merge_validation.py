"""Tests for ``utils.conversations.merge_conversations.validate_merge_compatibility``.

Regression coverage for the ``TypeError: unsupported operand type(s) for -: 'str' and 'str'``
crash on ``/v1/conversations/merge`` when a conversation's ``started_at`` or
``finished_at`` was persisted as an ISO string instead of a Firestore-native
datetime. The endpoint 500'd for any user whose merge selection included an
older conversation with string-typed timestamps.

These tests cover ``_coerce_dt`` (the helper that normalises both shapes to a
tz-aware UTC ``datetime``) and the full ``validate_merge_compatibility``
matrix across all-datetime, all-string, and mixed inputs.
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub the database modules that merge_conversations imports — these init
# Firestore at module load. utils.other.storage is also pre-stubbed because it
# pulls google.cloud.storage + opuslib at import time and we don't want either
# wired up for a pure-function test.
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "conversations", "vector_db", "redis_db", "users"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.conversations"].get_conversation = MagicMock(return_value=None)
sys.modules["database.vector_db"].delete_vector = MagicMock()

# Pre-stub utils.other.storage. We do NOT stub `utils` or `utils.other` —
# those are real packages on disk and overwriting their __path__ with an empty
# list would break `from utils.conversations.merge_conversations import ...`
# below. Make sure those real packages are loaded first so their __path__ is set.
import utils  # noqa: F401, E402
import utils.other  # noqa: F401, E402

_fake_storage = types.ModuleType("utils.other.storage")
for _name in [
    "delete_conversation_audio_files",
    "list_audio_chunks",
    "storage_client",
    "private_cloud_sync_bucket",
    "_get_extension_for_path",
]:
    setattr(_fake_storage, _name, MagicMock())
sys.modules["utils.other.storage"] = _fake_storage

# Stub the models.* chain. merge_conversations only references these names
# inside perform_merge_async (the actual merge runner), not inside the
# validate function under test — but the top-level imports still resolve at
# module load. Stubbing avoids dragging in pydantic v2 / heavy model graph
# for what is really a pure-function unit test.
_fake_models = types.ModuleType("models")
_fake_models.__path__ = []
sys.modules["models"] = _fake_models
for _modname, _attrs in [
    ("models.audio_file", ["AudioFile"]),
    ("models.conversation", ["Conversation"]),
    ("models.conversation_enums", ["ConversationStatus"]),
    ("models.structured", ["Structured"]),
]:
    _mod = types.ModuleType(_modname)
    for _attr in _attrs:
        setattr(_mod, _attr, MagicMock())
    sys.modules[_modname] = _mod

# Drop any earlier empty stub of utils.conversations.merge_conversations so
# the real module file is re-loaded with our pre-installed stubs in place.
for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
    _existing = sys.modules.get(_modname)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_modname]

from utils.conversations.merge_conversations import (  # noqa: E402
    _coerce_dt,
    _merge_transcript_segments,
    _normalize_conversation_timestamps,
    validate_merge_compatibility,
)

# ---------------------------------------------------------------------------
# _coerce_dt
# ---------------------------------------------------------------------------


class TestCoerceDt:
    def test_none_returns_none(self):
        assert _coerce_dt(None) is None

    def test_tz_aware_datetime_unchanged(self):
        dt = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        assert _coerce_dt(dt) is dt

    def test_tz_naive_datetime_assumed_utc(self):
        dt = datetime(2026, 5, 30, 12, 0)
        result = _coerce_dt(dt)
        assert result == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        assert result.tzinfo is timezone.utc

    def test_iso_string_with_z_suffix(self):
        result = _coerce_dt("2026-05-30T12:00:00Z")
        assert result == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

    def test_iso_string_with_offset(self):
        result = _coerce_dt("2026-05-30T12:00:00+00:00")
        assert result == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

    def test_iso_string_with_nonzero_offset_normalises(self):
        # 12:00-05:00 is 17:00 UTC; equality across zones works on datetime.
        result = _coerce_dt("2026-05-30T12:00:00-05:00")
        assert result == datetime(2026, 5, 30, 17, 0, tzinfo=timezone.utc)

    def test_iso_string_without_tz_assumed_utc(self):
        result = _coerce_dt("2026-05-30T12:00:00")
        assert result == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        assert result.tzinfo is timezone.utc

    def test_iso_string_with_microseconds(self):
        result = _coerce_dt("2026-05-30T12:00:00.123456Z")
        assert result == datetime(2026, 5, 30, 12, 0, 0, 123456, tzinfo=timezone.utc)

    def test_invalid_string_returns_none(self):
        assert _coerce_dt("not-a-date") is None

    def test_unsupported_type_returns_none(self):
        assert _coerce_dt(12345) is None
        assert _coerce_dt([2026, 5, 30]) is None


# ---------------------------------------------------------------------------
# validate_merge_compatibility — gate checks
# ---------------------------------------------------------------------------


def _conv(conv_id="c1", started=None, finished=None, status="completed", locked=False):
    return {
        "id": conv_id,
        "started_at": started,
        "finished_at": finished,
        "status": status,
        "is_locked": locked,
    }


class TestValidateGateChecks:
    def test_rejects_single_conversation(self):
        ok, err, warn = validate_merge_compatibility([_conv("c1")])
        assert ok is False
        assert "At least 2" in err
        assert warn is None

    def test_rejects_empty_list(self):
        ok, err, warn = validate_merge_compatibility([])
        assert ok is False
        assert "At least 2" in err

    def test_rejects_locked_conversation(self):
        convs = [_conv("c1", locked=True), _conv("c2")]
        ok, err, warn = validate_merge_compatibility(convs)
        assert ok is False
        assert "locked" in err.lower()

    def test_rejects_non_completed_conversation(self):
        convs = [_conv("c1"), _conv("c2", status="processing")]
        ok, err, warn = validate_merge_compatibility(convs)
        assert ok is False
        assert "c2" in err
        assert "processing" in err


# ---------------------------------------------------------------------------
# validate_merge_compatibility — gap math (the regression surface)
# ---------------------------------------------------------------------------


class TestValidateGapMath:
    def test_datetime_inputs_small_gap_no_warning(self):
        c1 = _conv(
            "c1",
            started=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc),
        )
        c2 = _conv(
            "c2",
            started=datetime(2026, 5, 30, 10, 45, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
        )
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert err is None
        assert warn is None  # 15-minute gap, well under 1h

    def test_datetime_inputs_large_gap_warning(self):
        c1 = _conv(
            "c1",
            started=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc),
        )
        c2 = _conv(
            "c2",
            started=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 13, 30, tzinfo=timezone.utc),
        )
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert err is None
        assert warn is not None
        assert "2.5h" in warn

    def test_string_inputs_no_crash(self):
        # Regression: previously raised
        # TypeError: unsupported operand type(s) for -: 'str' and 'str'
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished="2026-05-30T10:30:00Z")
        c2 = _conv("c2", started="2026-05-30T13:00:00Z", finished="2026-05-30T13:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert err is None
        assert warn is not None
        assert "2.5h" in warn

    def test_string_inputs_small_gap_no_warning(self):
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished="2026-05-30T10:30:00Z")
        c2 = _conv("c2", started="2026-05-30T10:45:00Z", finished="2026-05-30T11:00:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is None

    def test_mixed_datetime_and_string_inputs(self):
        # Realistic case: older conv stored timestamps as strings, newer as
        # Firestore datetimes. Subtraction between the two also throws without
        # the coercion fix.
        c1 = _conv(
            "c1",
            started="2026-05-30T10:00:00Z",
            finished="2026-05-30T10:30:00Z",
        )
        c2 = _conv(
            "c2",
            started=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 13, 30, tzinfo=timezone.utc),
        )
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is not None
        assert "2.5h" in warn

    def test_mixed_tz_aware_and_naive_datetimes(self):
        # Subtracting an aware datetime from a naive one throws — _coerce_dt
        # normalises naive timestamps to UTC so the math is consistent.
        c1 = _conv(
            "c1",
            started=datetime(2026, 5, 30, 10, 0),  # naive
            finished=datetime(2026, 5, 30, 10, 30),  # naive
        )
        c2 = _conv(
            "c2",
            started=datetime(2026, 5, 30, 13, 0, tzinfo=timezone.utc),
            finished=datetime(2026, 5, 30, 13, 30, tzinfo=timezone.utc),
        )
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is not None
        assert "2.5h" in warn

    def test_missing_finished_at_skips_gap(self):
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished=None)
        c2 = _conv("c2", started="2026-05-30T13:00:00Z", finished="2026-05-30T13:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is None  # gap skipped because prev_finished missing

    def test_missing_started_at_skips_gap(self):
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished="2026-05-30T10:30:00Z")
        c2 = _conv("c2", started=None, finished="2026-05-30T13:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is None

    def test_invalid_iso_string_skips_gap(self):
        # Malformed timestamp must not 500 the request — the gap warning is
        # best-effort and a single bad doc just gets skipped.
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished="not-a-date")
        c2 = _conv("c2", started="2026-05-30T13:00:00Z", finished="2026-05-30T13:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        assert warn is None

    def test_three_conversations_warnings_concatenated(self):
        c1 = _conv("c1", started="2026-05-30T10:00:00Z", finished="2026-05-30T10:30:00Z")
        c2 = _conv("c2", started="2026-05-30T13:00:00Z", finished="2026-05-30T13:30:00Z")
        c3 = _conv("c3", started="2026-05-30T17:00:00Z", finished="2026-05-30T17:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2, c3])
        assert ok is True
        assert warn is not None
        # Both gaps surface: c1→c2 = 2.5h, c2→c3 = 3.5h
        assert "2.5h" in warn
        assert "3.5h" in warn
        assert ";" in warn

    def test_sorting_handles_string_timestamps(self):
        # Pass conversations in the wrong chronological order with string
        # timestamps — the sort key path also went through _coerce_dt, so
        # ordering must still resolve correctly.
        c1 = _conv("c1", started="2026-05-30T13:00:00Z", finished="2026-05-30T13:30:00Z")
        c2 = _conv("c2", started="2026-05-30T10:00:00Z", finished="2026-05-30T10:30:00Z")
        ok, err, warn = validate_merge_compatibility([c1, c2])
        assert ok is True
        # After sort, c2 comes first → gap c2.finished (10:30) → c1.started (13:00) = 2.5h
        assert warn is not None
        assert "2.5h" in warn


# ---------------------------------------------------------------------------
# _normalize_conversation_timestamps — called by perform_merge_async so the
# background task's sort/max/.isoformat/subtraction sites can assume datetime
# ---------------------------------------------------------------------------


class TestNormalizeConversationTimestamps:
    def test_coerces_all_three_timestamp_fields(self):
        conv = {
            "id": "c1",
            "started_at": "2026-05-30T10:00:00Z",
            "finished_at": "2026-05-30T10:30:00Z",
            "created_at": "2026-05-30T09:00:00Z",
            "language": "en",
        }
        [out] = _normalize_conversation_timestamps([conv])
        assert out["started_at"] == datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)
        assert out["finished_at"] == datetime(2026, 5, 30, 10, 30, tzinfo=timezone.utc)
        assert out["created_at"] == datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)
        assert out["language"] == "en"

    def test_leaves_native_datetimes_untouched(self):
        dt = datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)
        [out] = _normalize_conversation_timestamps(
            [{"id": "c1", "started_at": dt, "finished_at": dt, "created_at": dt}]
        )
        assert out["started_at"] is dt
        assert out["finished_at"] is dt

    def test_does_not_mutate_input(self):
        conv = {"id": "c1", "started_at": "2026-05-30T10:00:00Z"}
        _normalize_conversation_timestamps([conv])
        # Caller's dict must still see the original string.
        assert conv["started_at"] == "2026-05-30T10:00:00Z"

    def test_omits_unknown_fields(self):
        # Fields outside _TIMESTAMP_FIELDS pass through unchanged.
        conv = {"id": "c1", "started_at": "2026-05-30T10:00:00Z", "other": "value"}
        [out] = _normalize_conversation_timestamps([conv])
        assert out["other"] == "value"

    def test_skips_missing_timestamp_field(self):
        # A doc without a given timestamp key keeps the key absent rather
        # than introducing a None — downstream sites use `.get(...)` and
        # already handle the missing case.
        conv = {"id": "c1", "started_at": "2026-05-30T10:00:00Z"}
        [out] = _normalize_conversation_timestamps([conv])
        assert "finished_at" not in out
        assert "created_at" not in out

    def test_unparseable_becomes_none(self):
        conv = {"id": "c1", "started_at": "not-a-date", "finished_at": None}
        [out] = _normalize_conversation_timestamps([conv])
        assert out["started_at"] is None
        assert out["finished_at"] is None


# ---------------------------------------------------------------------------
# _merge_transcript_segments — receives normalised input from perform_merge_async,
# but the gap/duration arithmetic is the same shape that previously crashed
# the background task on string timestamps (Greptile P1 on PR #7554).
# ---------------------------------------------------------------------------


def _seg(start, end, text="hi", speaker_id=0):
    return {"start": start, "end": end, "text": text, "speaker_id": speaker_id}


class TestMergeTranscriptSegments:
    def test_two_conversations_with_gap_adjusts_offsets(self):
        c1 = {
            "started_at": datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 5, 30, 10, 0, 30, tzinfo=timezone.utc),
            "transcript_segments": [_seg(0.0, 5.0, "first")],
        }
        c2 = {
            "started_at": datetime(2026, 5, 30, 10, 1, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 5, 30, 10, 1, 30, tzinfo=timezone.utc),
            "transcript_segments": [_seg(0.0, 5.0, "second")],
        }
        merged = _merge_transcript_segments([c1, c2])
        assert len(merged) == 2
        assert merged[0]["start"] == 0.0
        assert merged[0]["end"] == 5.0
        # Cumulative offset = 5.0 (max end of c1); gap = 60-30 = 30s.
        # c2's seg starts at 0.0 → offset 35.0.
        assert merged[1]["start"] == 35.0
        assert merged[1]["end"] == 40.0

    def test_inputs_post_normalisation_string_origin_does_not_crash(self):
        # Simulates the exact path perform_merge_async takes: it now calls
        # _normalize_conversation_timestamps before passing to this function.
        # Verify the normaliser → merge_segments handoff produces the same
        # arithmetic as native-datetime inputs would. Pre-fix this scenario
        # surfaced as a silent TypeError caught by the outer except.
        raw = [
            {
                "started_at": "2026-05-30T10:00:00Z",
                "finished_at": "2026-05-30T10:00:30Z",
                "transcript_segments": [_seg(0.0, 5.0, "first")],
            },
            {
                "started_at": "2026-05-30T10:01:00Z",
                "finished_at": "2026-05-30T10:01:30Z",
                "transcript_segments": [_seg(0.0, 5.0, "second")],
            },
        ]
        normalized = _normalize_conversation_timestamps(raw)
        merged = _merge_transcript_segments(normalized)
        assert len(merged) == 2
        assert merged[1]["start"] == 35.0
        assert merged[1]["end"] == 40.0

    def test_first_conv_with_no_segments_uses_finished_minus_started(self):
        # When the first conversation has no segments, cumulative_offset is
        # seeded via finished_at - started_at. This is a datetime subtraction
        # and was one of the silent-failure sites for string-typed docs.
        raw = [
            {
                "started_at": "2026-05-30T10:00:00Z",
                "finished_at": "2026-05-30T10:00:20Z",
                "transcript_segments": [],
            },
            {
                "started_at": "2026-05-30T10:00:30Z",
                "finished_at": "2026-05-30T10:00:40Z",
                "transcript_segments": [_seg(0.0, 5.0, "second")],
            },
        ]
        merged = _merge_transcript_segments(_normalize_conversation_timestamps(raw))
        # c1 duration = 20s; gap = 30-20 = 10s; c2 seg → offset 30s.
        assert len(merged) == 1
        assert merged[0]["start"] == 30.0
        assert merged[0]["end"] == 35.0

    def test_mid_conv_with_no_segments_keeps_offset_chain(self):
        # The third site: when an intermediate conversation has no segments,
        # cumulative_offset advances by offset + (finished_at - started_at).
        raw = [
            {
                "started_at": "2026-05-30T10:00:00Z",
                "finished_at": "2026-05-30T10:00:05Z",
                "transcript_segments": [_seg(0.0, 5.0, "first")],
            },
            {
                "started_at": "2026-05-30T10:00:10Z",
                "finished_at": "2026-05-30T10:00:30Z",
                "transcript_segments": [],
            },
            {
                "started_at": "2026-05-30T10:00:40Z",
                "finished_at": "2026-05-30T10:00:45Z",
                "transcript_segments": [_seg(0.0, 5.0, "third")],
            },
        ]
        merged = _merge_transcript_segments(_normalize_conversation_timestamps(raw))
        # c1: max_end = 5. cumulative_offset = 5.
        # c2 (empty): gap = 10-5 = 5; offset = 10. duration = 20 → cum = 30.
        # c3: gap = 40-30 = 10; offset = 40. Seg starts at 0 → 40.
        assert len(merged) == 2
        assert merged[0]["start"] == 0.0
        assert merged[1]["start"] == 40.0
        assert merged[1]["end"] == 45.0

    def test_does_not_mutate_input_segments(self):
        seg = _seg(0.0, 5.0, "first")
        raw = [
            {
                "started_at": datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
                "finished_at": datetime(2026, 5, 30, 10, 0, 5, tzinfo=timezone.utc),
                "transcript_segments": [seg],
            },
            {
                "started_at": datetime(2026, 5, 30, 10, 0, 10, tzinfo=timezone.utc),
                "finished_at": datetime(2026, 5, 30, 10, 0, 15, tzinfo=timezone.utc),
                "transcript_segments": [_seg(0.0, 5.0, "second")],
            },
        ]
        _merge_transcript_segments(raw)
        assert seg["start"] == 0.0
        assert seg["end"] == 5.0
