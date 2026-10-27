"""Chat/agent tool timestamps render in the user's timezone (issue #6214).

``/v1/tools/*`` (``routers/tools.py``) is the tool surface desktop, web, and MCP agent clients
call. Its conversations service already localized timestamps, but two siblings did not:

- ``get_action_items_text`` emitted a bare UTC wall clock (``Due: 2026-06-26 22:00:00``) with no
  timezone label, so the model read it as local time and stated the wrong time of day.
- ``search_memories_text`` / ``search_memories_tool`` emitted a bare UTC calendar date, which is a
  day late for a user west of Greenwich in the evening.

The modules under test are imported normally and their collaborators are swapped with
``monkeypatch.setattr``, so the assertions run the real formatting code.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from utils.model_text import DisplayClock, format_date, format_instant  # noqa: E402
import database.notifications as notification_db  # noqa: E402
import utils.retrieval.tool_services.action_items as action_items_svc  # noqa: E402
import utils.retrieval.tool_services.memories as memories_svc  # noqa: E402
import utils.retrieval.tools.memory_tools as memory_tools  # noqa: E402

# 22:00 UTC on 2026-06-26 is 19:00 the same day in Sao Paulo (UTC-3) — the reporter's 3-hour skew.
UTC_INSTANT = datetime(2026, 6, 26, 22, 0, 0, tzinfo=timezone.utc)
# 01:30 UTC on the 27th is still the 26th in Sao Paulo: the UTC date rolls over at a different
# instant than the user's, which is what made memory dates a day late.
UTC_AFTER_MIDNIGHT = datetime(2026, 6, 27, 1, 30, 0, tzinfo=timezone.utc)
SAO_PAULO = "America/Sao_Paulo"
HO_CHI_MINH = "Asia/Ho_Chi_Minh"
UTC_REPORTER_INSTANT = datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc)


@pytest.fixture
def user_tz(monkeypatch):
    """Set the stored timezone used by REST/MCP services without turning chat tools into lookups."""

    def _set(tz, *, fail=False):
        def _get_user_time_zone(uid):
            if fail:
                raise RuntimeError("firestore down")
            return tz

        monkeypatch.setattr(notification_db, "get_user_time_zone", _get_user_time_zone)

    return _set


def _memory(created_at):
    return SimpleNamespace(
        content="Likes espresso",
        created_at=created_at,
        category=SimpleNamespace(value="preferences"),
        is_locked=False,
    )


def _run_action_items(monkeypatch, items):
    monkeypatch.setattr(action_items_svc.action_items_db, "get_action_items", lambda *a, **k: items)
    return action_items_svc.get_action_items_text(uid="test-uid")


def _stub_canonical_memory_search(monkeypatch, module, memories):
    """Return ``memories`` from universal MemoryService search."""
    matches = [SimpleNamespace(memory=m, score=0.9) for m in memories]
    monkeypatch.setattr(
        module,
        "MemoryService",
        lambda *a, **k: SimpleNamespace(search=lambda *sa, **sk: matches),
    )


# ---------------------------------------------------------------------------
# The shared formatters
# ---------------------------------------------------------------------------
class TestRenderFormatters:
    def test_time_converted_and_labelled(self):
        assert format_instant(UTC_INSTANT, DisplayClock.from_name(SAO_PAULO)) == (
            f"Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)"
        )

    def test_time_naive_value_treated_as_utc(self):
        naive = datetime(2026, 6, 26, 22, 0, 0)
        assert format_instant(naive, DisplayClock.from_name(SAO_PAULO)) == (
            f"Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)"
        )

    def test_date_rolls_back_across_utc_midnight(self):
        assert format_date(UTC_AFTER_MIDNIGHT, DisplayClock.from_name(SAO_PAULO)) == "Fri 26 Jun 2026"

    def test_date_naive_value_treated_as_utc(self):
        naive = datetime(2026, 6, 27, 1, 30, 0)
        assert format_date(naive, DisplayClock.from_name(SAO_PAULO)) == "Fri 26 Jun 2026"

    def test_utc_fallback_unchanged(self):
        assert format_instant(UTC_INSTANT, DisplayClock.utc()) == "Fri 26 Jun 2026, 22:00 UTC"
        assert format_date(UTC_AFTER_MIDNIGHT, DisplayClock.utc()) == "Sat 27 Jun 2026"


# ---------------------------------------------------------------------------
# get_action_items_text — the REST tool service the agent clients call
# ---------------------------------------------------------------------------
class TestActionItemsTextTimezone:
    def test_seven_eighteen_utc_is_fourteen_eighteen_in_ho_chi_minh(self, monkeypatch, user_tz):
        user_tz(HO_CHI_MINH)
        out = _run_action_items(
            monkeypatch,
            [{'id': 'ai-1', 'description': 'Call the dentist', 'due_at': UTC_REPORTER_INSTANT}],
        )
        assert f"Due: Sat 26 Sep 2026, 14:18 {HO_CHI_MINH} (UTC+07:00)" in out

    def test_due_and_created_rendered_in_user_timezone(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        out = _run_action_items(
            monkeypatch,
            [{'id': 'ai-1', 'description': 'Call the dentist', 'created_at': UTC_INSTANT, 'due_at': UTC_INSTANT}],
        )
        assert f"Due: Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)" in out
        assert f"Created: Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)" in out
        # The bare UTC wall clock the model used to misread as local time is gone.
        assert "22:00" not in out

    def test_completed_at_rendered_in_user_timezone(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        out = _run_action_items(
            monkeypatch,
            [{'id': 'ai-1', 'description': 'Ship it', 'completed': True, 'completed_at': UTC_INSTANT}],
        )
        assert f"Completed: Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)" in out

    def test_every_timestamp_carries_a_timezone_label(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        out = _run_action_items(
            monkeypatch,
            [
                {
                    'id': 'ai-1',
                    'description': 'Call the dentist',
                    'created_at': UTC_INSTANT,
                    'due_at': UTC_INSTANT,
                    'completed_at': UTC_INSTANT,
                }
            ],
        )
        stamped = [ln for ln in out.splitlines() if ln.strip().startswith(("Created:", "Due:", "Completed:"))]
        assert len(stamped) == 3
        for line in stamped:
            assert line.rstrip().endswith(f"{SAO_PAULO} (UTC-03:00)"), f"unlabelled timestamp: {line!r}"

    def test_naive_timestamp_treated_as_utc(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        out = _run_action_items(
            monkeypatch,
            [{'id': 'ai-1', 'description': 'Task', 'due_at': datetime(2026, 6, 26, 22, 0, 0)}],
        )
        assert f"Due: Fri 26 Jun 2026, 19:00 {SAO_PAULO} (UTC-03:00)" in out

    def test_unset_timezone_falls_back_to_labelled_utc(self, monkeypatch, user_tz):
        user_tz(None)
        out = _run_action_items(monkeypatch, [{'id': 'ai-1', 'description': 'Task', 'due_at': UTC_INSTANT}])
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in out

    def test_timezone_lookup_failure_does_not_abort_retrieval(self, monkeypatch, user_tz):
        user_tz(None, fail=True)
        out = _run_action_items(monkeypatch, [{'id': 'ai-1', 'description': 'Task', 'due_at': UTC_INSTANT}])
        assert "Task" in out
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in out


# ---------------------------------------------------------------------------
# Memory dates — REST tool service and the agentic tool
# ---------------------------------------------------------------------------
class TestMemoryDateTimezone:
    def test_service_memory_timestamp_uses_turnless_user_clock(self, monkeypatch, user_tz):
        user_tz(HO_CHI_MINH)
        monkeypatch.setattr(
            memories_svc,
            "MemoryService",
            lambda **kwargs: SimpleNamespace(read=lambda *args, **kwargs: [_memory(UTC_REPORTER_INSTANT)]),
        )
        out = memories_svc.get_memories_text(uid="test-uid", limit=1)
        assert f"Sat 26 Sep 2026, 14:18 {HO_CHI_MINH} (UTC+07:00)" in out

    def test_memory_tool_timestamp_uses_turn_zone(self, monkeypatch):
        monkeypatch.setattr(
            memory_tools,
            "MemoryService",
            lambda **kwargs: SimpleNamespace(read=lambda *args, **kwargs: [_memory(UTC_REPORTER_INSTANT)]),
        )
        out = memory_tools.get_memories_tool.func(
            limit=1,
            config={"configurable": {"user_id": "test-uid", "user_timezone": HO_CHI_MINH}},
        )
        assert f"Sat 26 Sep 2026, 14:18 {HO_CHI_MINH} (UTC+07:00)" in out

    def test_service_search_date_uses_user_timezone(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        _stub_canonical_memory_search(monkeypatch, memories_svc, [_memory(UTC_AFTER_MIDNIGHT)])
        out = memories_svc.search_memories_text(uid="test-uid", query="coffee")
        assert "date: Fri 26 Jun 2026" in out
        assert "date: Sat 27 Jun 2026" not in out

    def test_tool_search_date_uses_user_timezone(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        _stub_canonical_memory_search(monkeypatch, memory_tools, [_memory(UTC_AFTER_MIDNIGHT)])
        out = memory_tools.search_memories_tool.func(
            query="coffee",
            config={"configurable": {"user_id": "test-uid", "user_timezone": SAO_PAULO}},
        )
        assert "date: Fri 26 Jun 2026" in out
        assert "date: Sat 27 Jun 2026" not in out

    def test_unset_timezone_falls_back_to_utc_date(self, monkeypatch, user_tz):
        user_tz(None)
        _stub_canonical_memory_search(monkeypatch, memories_svc, [_memory(UTC_AFTER_MIDNIGHT)])
        out = memories_svc.search_memories_text(uid="test-uid", query="coffee")
        assert "date: Sat 27 Jun 2026" in out

    def test_missing_created_at_still_renders(self, monkeypatch, user_tz):
        user_tz(SAO_PAULO)
        _stub_canonical_memory_search(monkeypatch, memories_svc, [_memory(None)])
        out = memories_svc.search_memories_text(uid="test-uid", query="coffee")
        assert "date: Unknown" in out
