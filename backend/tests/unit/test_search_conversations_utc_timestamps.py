"""Tests for timezone-aware UTC timestamps in conversation search results (issue #4643).

search_conversations renders the Typesense docs' created_at/started_at/finished_at unix timestamps
into ISO strings that are handed to the chat model (search_conversations_tool for "when did X
happen?" event queries) and to API clients. It used datetime.utcfromtimestamp(ts).isoformat(), which
returns a NAIVE string with no offset, so a UTC time could be read as local time and a conversation
shown hours off. _utc_iso anchors the conversion to UTC so the offset is explicit. These cover the
pure helper.
"""

import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _load():
    # search.py constructs a module-level typesense.Client(...), so stub typesense before loading; the
    # helper under test only uses the standard library.
    sys.modules.setdefault("typesense", MagicMock())
    spec = importlib.util.spec_from_file_location(
        "search_under_test", str(BACKEND_DIR / "utils" / "conversations" / "search.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


search = _load()

TS = 1700000000  # 2023-11-14T22:13:20+00:00


class TestUtcIso:
    def test_is_timezone_aware_with_explicit_offset(self):
        out = search._utc_iso(TS)
        # An explicit +00:00 offset, not a naive string the client could read as local time.
        assert out.endswith("+00:00")
        parsed = datetime.fromisoformat(out)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_represents_the_correct_utc_instant(self):
        out = search._utc_iso(TS)
        assert datetime.fromisoformat(out) == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
        # And the same instant as the canonical tz-aware conversion.
        assert datetime.fromisoformat(out) == datetime.fromtimestamp(TS, tz=timezone.utc)

    def test_not_naive_regression(self):
        # The old datetime.utcfromtimestamp(ts).isoformat() produced a naive string with no offset;
        # guard against a regression back to that.
        out = search._utc_iso(TS)
        assert "+00:00" in out
        assert datetime.fromisoformat(out).tzinfo is not None

    def test_float_timestamp_is_handled(self):
        out = search._utc_iso(TS + 0.5)
        assert datetime.fromisoformat(out).tzinfo is not None
