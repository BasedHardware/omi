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

from utils.conversations.merge_conversations import _coerce_dt, validate_merge_compatibility  # noqa: E402

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
