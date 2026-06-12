"""Tests for conversation title/summary timezone correctness (issue #4773).

The two structuring functions used to hand the LLM a raw UTC timestamp and ask it to convert to the
user's timezone, which mislabeled the time of day in titles/overviews. They now convert deterministically
in Python and tell the model the timestamp is already local.

Covers:
1. _local_started_at_iso converts UTC to the user's local wall-clock
2. None / invalid timezone falls back to UTC; naive datetimes are treated as UTC; DST is handled
3. get_transcript_structure and get_reprocess_transcript_structure pass the local time + a non-None tz
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub heavy dependencies so conversation_processing.py imports without external services.
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database._client",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

_stub_package("database")
sys.modules["database.auth"].get_user_name = MagicMock(return_value="Test User")

# Stub langchain core pieces used at import time.
_stub_package("langchain_core")
langchain_output_parsers = _stub_module("langchain_core.output_parsers")
langchain_output_parsers.PydanticOutputParser = MagicMock()
langchain_prompts = _stub_module("langchain_core.prompts")
langchain_prompts.ChatPromptTemplate = MagicMock()

# Stub utils packages and the LLM client module.
_stub_package("utils")
_stub_package("utils.llm")
llm_clients_stub = _stub_module("utils.llm.clients")
llm_clients_stub.get_llm = MagicMock(return_value=MagicMock())
llm_clients_stub.parser = MagicMock()

# Real models (pure pydantic) resolve from the models package directory.
_stub_package("models")
sys.modules["models"].__path__ = [str(BACKEND_DIR / "models")]

conv_proc = _load_module_from_file(
    "utils.llm.conversation_processing",
    BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
)

# Keep timezone assertions independent of host OS tzdata, which is often absent on Windows test environments.


class _JulyOnlyNewYorkTestZone(tzinfo):
    """Minimal test zone: only the current July DST case needs EDT behavior."""

    def utcoffset(self, dt):
        return timedelta(hours=-4 if dt is not None and dt.month == 7 else -5)

    def dst(self, dt):
        return timedelta(hours=1 if dt is not None and dt.month == 7 else 0)

    def tzname(self, dt):
        return "EDT" if dt is not None and dt.month == 7 else "EST"


def _test_zone_info(name):
    if name == "Pacific/Honolulu":
        return timezone(timedelta(hours=-10), name)
    if name == "America/New_York":
        return _JulyOnlyNewYorkTestZone()
    if name == "UTC":
        return timezone.utc
    raise KeyError(name)


conv_proc.ZoneInfo = _test_zone_info


# ===========================================================================
# _local_started_at_iso unit tests (pure conversion logic)
# ===========================================================================


class TestLocalStartedAtIso:

    def test_converts_utc_to_user_local(self):
        # 23:48 UTC -> 13:48 in Honolulu (UTC-10), the meal/time-of-day case from the issue.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "Pacific/Honolulu")
        assert out == "2025-01-01T13:48:00"

    def test_none_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), None)
        assert out == "2025-01-01T23:48:00"

    def test_invalid_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "Not/AZone")
        assert out == "2025-01-01T23:48:00"

    def test_empty_tz_falls_back_to_utc(self):
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), "")
        assert out == "2025-01-01T23:48:00"

    def test_naive_started_at_treated_as_utc(self):
        # A naive timestamp must be read as UTC, not silently localized.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 23, 48), "Pacific/Honolulu")
        assert out == "2025-01-01T13:48:00"

    def test_dst_summer_offset(self):
        # July: America/New_York is EDT (UTC-4). 12:00 UTC -> 08:00 local.
        out = conv_proc._local_started_at_iso(datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc), "America/New_York")
        assert out == "2025-07-01T08:00:00"

    def test_dst_winter_offset(self):
        # January: America/New_York is EST (UTC-5). 12:00 UTC -> 07:00 local.
        out = conv_proc._local_started_at_iso(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc), "America/New_York")
        assert out == "2025-01-01T07:00:00"


# ===========================================================================
# Structuring functions pass local time to the prompt
# ===========================================================================


def _capture_structure(fn, **kwargs):
    """Run a structuring function with the LLM chain mocked.

    Returns {'invoke': <dict passed to chain.invoke>, 'system_text': <joined system prompt text>}.
    """
    mock_response = MagicMock()
    mock_response.events = []

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = mock_response
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    mock_llm = MagicMock()
    mock_llm.__or__ = MagicMock(return_value=mock_chain)

    with patch.object(conv_proc, "get_llm", return_value=mock_llm), patch.object(
        conv_proc, "ChatPromptTemplate"
    ) as mock_prompt_cls, patch.object(conv_proc, "_build_conversation_context", return_value="ctx"):
        mock_prompt = MagicMock()
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)
        mock_prompt_cls.from_messages.return_value = mock_prompt
        fn(**kwargs)
        messages = mock_prompt_cls.from_messages.call_args[0][0]

    system_text = "\n".join(text for _role, text in messages)
    return {"invoke": mock_chain.invoke.call_args[0][0], "system_text": system_text}


class TestStructureFunctionsTimezone:

    def test_get_transcript_structure_passes_local_time(self):
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz="Pacific/Honolulu",
            uid="u1",
        )
        # 1:48 PM local, not 23:48 UTC — this is the value the model sees.
        assert result["invoke"]["started_at"] == "2025-01-01T13:48:00"
        assert result["invoke"]["tz"] == "Pacific/Honolulu"

    def test_get_transcript_structure_none_tz_labels_utc(self):
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz=None,
            uid="u1",
        )
        assert result["invoke"]["started_at"] == "2025-01-01T23:48:00"
        # The prompt must never say the timezone is "None".
        assert result["invoke"]["tz"] == "UTC"

    def test_get_transcript_structure_dst_offset(self):
        # America/New_York in July is EDT (UTC-4): 12:00 UTC -> 08:00 local end to end.
        result = _capture_structure(
            conv_proc.get_transcript_structure,
            transcript="Morning standup",
            started_at=datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc),
            language_code="en",
            tz="America/New_York",
            uid="u1",
        )
        assert result["invoke"]["started_at"] == "2025-07-01T08:00:00"
        assert result["invoke"]["tz"] == "America/New_York"

    def test_get_reprocess_transcript_structure_passes_local_time(self):
        result = _capture_structure(
            conv_proc.get_reprocess_transcript_structure,
            transcript="Lunch meeting about the project",
            started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc),
            language_code="en",
            tz="Pacific/Honolulu",
            title="Lunch",
        )
        assert result["invoke"]["started_at"] == "2025-01-01T13:48:00"
        assert result["invoke"]["tz"] == "Pacific/Honolulu"

    def test_both_prompts_state_local_and_drop_convert_instruction(self):
        # The semantic core of the fix is the prompt wording; pin it so a revert can't pass silently.
        for fn, kwargs in [
            (
                conv_proc.get_transcript_structure,
                dict(transcript="x", language_code="en", tz="Pacific/Honolulu", uid="u1"),
            ),
            (
                conv_proc.get_reprocess_transcript_structure,
                dict(transcript="x", language_code="en", tz="Pacific/Honolulu", title="t"),
            ),
        ]:
            result = _capture_structure(fn, started_at=datetime(2025, 1, 1, 23, 48, tzinfo=timezone.utc), **kwargs)
            text = result["system_text"]
            assert "already the user's local time" in text
            assert "do not re-interpret this timestamp as UTC" in text
            # The old buggy instruction asking the model to convert must be gone.
            assert "respond in user local timezone" not in text
