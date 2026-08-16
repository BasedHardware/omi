"""Tests for current-date grounding in insight + memory generation.

The proactive insight notifications and the memory extractors asked the model to reason
about whether dated content is upcoming or in the future, but never told it what "today"
is. With no anchor the model fell back to its training-cutoff year and flagged correctly
recorded future-year dates as wrong ("your clock is wrong", "this date is in the future").
These tests cover the fix: a shared current-date helper, the date injected into the four
proactive prompts, and the two memory-extraction templates now requiring a current_date.
"""

import importlib.util
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the heavy leaves the modules under test import; langchain_core is used for real.
for _p in ["database", "utils", "utils.llm"]:
    _pkg(_p)
_nb = _mod("database.notifications")
_nb.get_user_time_zone = MagicMock(return_value="UTC")
_clients = _mod("utils.llm.clients")
_clients.get_llm = MagicMock(return_value=MagicMock())

temporal = _load("utils.llm.temporal", "utils/llm/temporal.py")
proactive = _load("utils.llm.proactive_notification", "utils/llm/proactive_notification.py")
prompts = _load("utils.prompts", "utils/prompts.py")

_FIXED = datetime(2026, 5, 21, 12, 0)


class TestCurrentDate:
    def test_formats_date_in_given_tz(self):
        with patch.object(temporal, "datetime") as md:
            md.now.return_value = _FIXED
            assert temporal.current_date_in_tz("America/Los_Angeles") == "2026-05-21"

    def test_missing_or_invalid_tz_falls_back_to_utc(self):
        with patch.object(temporal, "datetime") as md:
            md.now.return_value = _FIXED
            assert temporal.current_date_in_tz(None) == "2026-05-21"
            assert temporal.current_date_in_tz("Not/AZone") == "2026-05-21"

    def test_for_uid_reads_user_timezone(self):
        # database.notifications is imported lazily inside current_date_for_uid, so patch the
        # stubbed module that the lazy import resolves to.
        with patch.object(temporal, "datetime") as md:
            md.now.return_value = _FIXED
            with patch.object(_nb, "get_user_time_zone", return_value="UTC"):
                assert temporal.current_date_for_uid("u1") == "2026-05-21"

    def test_for_uid_falls_back_when_lookup_raises(self):
        with patch.object(temporal, "datetime") as md:
            md.now.return_value = _FIXED
            with patch.object(_nb, "get_user_time_zone", side_effect=RuntimeError("down")):
                assert temporal.current_date_for_uid("u1") == "2026-05-21"

    def test_real_call_returns_iso_date(self):
        # Smoke test with no mock: a real YYYY-MM-DD string.
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", temporal.current_date_in_tz("UTC"))


class TestDateInTz:
    def test_renders_content_datetime_date(self):
        dt = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        assert temporal.date_in_tz(dt, "UTC") == "2026-05-21"

    def test_naive_datetime_treated_as_utc(self):
        assert temporal.date_in_tz(datetime(2026, 5, 21, 12, 0), "UTC") == "2026-05-21"

    def test_converts_into_offset_zone_crossing_day_boundary(self):
        # 02:00 UTC is the previous day at UTC-7. Patch the zone resolver so the assertion does
        # not depend on host tzdata.
        with patch.object(temporal, "_zone", return_value=timezone(timedelta(hours=-7))):
            dt = datetime(2026, 5, 21, 2, 0, tzinfo=timezone.utc)
            assert temporal.date_in_tz(dt, "America/Los_Angeles") == "2026-05-20"

    def test_invalid_tz_falls_back_to_utc(self):
        dt = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        assert temporal.date_in_tz(dt, "Not/AZone") == "2026-05-21"


def _capture_prompt(fn, **kwargs):
    """Run a proactive builder with the LLM mocked and return the prompt string it built."""
    captured = {}
    structured = MagicMock()
    structured.invoke.side_effect = lambda p: captured.__setitem__("prompt", p) or MagicMock()
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    with patch.object(proactive, "get_llm", return_value=llm):
        fn(**kwargs)
    return captured["prompt"]


class TestProactivePromptsGrounded:
    def test_gate_prompt_states_today(self):
        prompt = _capture_prompt(
            proactive.evaluate_relevance,
            user_name="Zach",
            user_facts="",
            goals=[],
            current_messages=[],
            recent_notifications=[],
            current_date="2026-05-21",
        )
        assert "Today is 2026-05-21" in prompt

    def test_generate_prompt_states_today(self):
        prompt = _capture_prompt(
            proactive.generate_notification,
            user_name="Zach",
            user_facts="",
            goals=[],
            past_conversations_str="",
            current_messages=[],
            recent_notifications=[],
            frequency=3,
            gate_reasoning="something",
            current_date="2026-05-21",
        )
        assert "Today is 2026-05-21" in prompt

    def test_critic_prompt_rejects_wrong_clock_claims(self):
        prompt = _capture_prompt(
            proactive.validate_notification,
            user_name="Zach",
            notification_text="Your system clock is wrong",
            draft_reasoning="date looks like the future",
            current_messages=[],
            goals=[],
            current_date="2026-05-21",
        )
        assert "2026-05-21" in prompt
        # The critic must be told to reject the exact bug class.
        assert "REJECT" in prompt and "clock" in prompt

    def test_legacy_template_states_today(self):
        prompt = _capture_prompt(
            proactive.evaluate_proactive_notification,
            user_name="Zach",
            user_facts="",
            goals=[],
            past_conversations_str="",
            current_messages=[],
            recent_notifications=[],
            frequency=3,
            current_date="2026-05-21",
        )
        assert "Today is 2026-05-21" in prompt

    def test_date_is_grounded_even_without_explicit_value(self):
        # When the caller passes no date, the builder still injects a real one (UTC fallback).
        prompt = _capture_prompt(
            proactive.evaluate_relevance,
            user_name="Zach",
            user_facts="",
            goals=[],
            current_messages=[],
            recent_notifications=[],
        )
        assert re.search(r"Today is \d{4}-\d{2}-\d{2}", prompt)


class TestMemoryPromptsRequireDate:
    def test_conversation_memory_prompt_requires_current_date(self):
        assert "current_date" in prompts.extract_memories_prompt.input_variables

    def test_text_memory_prompt_requires_current_date(self):
        assert "current_date" in prompts.extract_memories_text_content_prompt.input_variables
