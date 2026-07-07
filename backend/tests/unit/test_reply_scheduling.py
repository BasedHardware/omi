import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (  # noqa: E402
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
)

ensure_utils_memory_packages_importable(str(BACKEND_DIR))
install_database_client_stub()
install_canonical_write_runtime_stubs()
install_ws_i_heavy_import_stubs()

# reply_scheduling imports the Google Calendar helpers from utils.retrieval.tools.*.
# Importing that package pulls the entire heavy RAG tools chain, so stub just the two
# calendar modules it needs (the async network calls are never exercised in unit tests;
# the pure logic and the LLM judge are). utils.retrieval stays real so reply_draft's
# person_service import (a sibling subpackage) still resolves.
import types as _types  # noqa: E402
from unittest.mock import MagicMock as _MM  # noqa: E402


def _stub_module(name, **attrs):
    mod = _types.ModuleType(name)
    mod.__path__ = []  # advertise as a package so submodule resolution doesn't error
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


_stub_module("utils.retrieval.tools")
_stub_module(
    "utils.retrieval.tools.calendar_tools",
    create_google_calendar_event=_MM(),
    get_google_calendar_events=_MM(),
)
_stub_module("utils.retrieval.tools.google_utils", refresh_google_token=_MM())

import utils.llm.reply_scheduling as rs  # noqa: E402

_TZ = ZoneInfo("America/New_York")


def _slot(day="2026-07-09", start="13:00", end="14:00", label="lunch"):
    s = datetime.fromisoformat(f"{day}T{start}:00+00:00")
    e = datetime.fromisoformat(f"{day}T{end}:00+00:00")
    return rs.ProposedSlot(start=s, end=e, label=label)


def _event(summary, start_iso, end_iso, **extra):
    ev = {'summary': summary, 'start': {'dateTime': start_iso}, 'end': {'dateTime': end_iso}}
    ev.update(extra)
    return ev


# --- prefilter -------------------------------------------------------------


def test_prefilter_detects_scheduling_messages():
    for text in [
        "free for lunch thursday 1pm?",
        "when are you free this week",
        "wanna grab coffee tmrw",
        "call at 3pm?",
    ]:
        assert rs.looks_like_scheduling([{'text': text, 'is_from_me': False}]), text


def test_prefilter_ignores_plain_chat():
    for text in ["haha that's hilarious", "did you see the game last night", "thanks so much"]:
        assert not rs.looks_like_scheduling([{'text': text, 'is_from_me': False}]), text


def test_prefilter_ignores_the_users_own_messages():
    # A scheduling word in the USER's own outgoing message must not trigger a lookup —
    # we only act on what the other person asked.
    thread = [{'text': "lunch tomorrow at 1?", 'is_from_me': True}]
    assert not rs.looks_like_scheduling(thread)


# --- inbound text ----------------------------------------------------------


def test_recent_inbound_text_excludes_from_me_and_orders_oldest_first():
    thread = [
        {'text': 'hey', 'is_from_me': False},
        {'text': 'you around?', 'is_from_me': False},
        {'text': 'yeah whats up', 'is_from_me': True},
    ]
    assert rs._recent_inbound_text(thread) == "hey\nyou around?"


# --- json parsing ----------------------------------------------------------


def test_parse_json_object_tolerates_code_fences():
    obj = rs._parse_json_object('```json\n{"is_scheduling": true, "proposed": []}\n```')
    assert obj == {"is_scheduling": True, "proposed": []}


def test_parse_json_object_returns_none_on_garbage():
    assert rs._parse_json_object("not json at all") is None


def test_parse_iso_treats_naive_as_utc():
    dt = rs._parse_iso("2026-07-09T13:00:00")
    assert dt.tzinfo is not None and dt.utcoffset() == timedelta(0)


# --- proposal building -----------------------------------------------------


def test_proposal_from_obj_builds_slots_and_defaults_end():
    now = datetime(2026, 7, 8, 9, 0, tzinfo=_TZ)
    obj = {
        "is_scheduling": True,
        "proposed": [{"start_iso": "2026-07-09T13:00:00-04:00", "end_iso": None, "label": "lunch"}],
        "window_start_iso": "2026-07-09T00:00:00-04:00",
        "window_end_iso": "2026-07-09T23:59:00-04:00",
    }
    p = rs._proposal_from_obj(obj, now)
    assert p.is_scheduling and len(p.slots) == 1
    slot = p.slots[0]
    assert slot.label == "lunch"
    # No end given → default one-hour hold.
    assert slot.end - slot.start == timedelta(minutes=rs.DEFAULT_HOLD_MINUTES)


def test_proposal_from_obj_not_scheduling_short_circuits():
    now = datetime(2026, 7, 8, 9, 0, tzinfo=_TZ)
    p = rs._proposal_from_obj({"is_scheduling": False}, now)
    assert p.is_scheduling is False and p.slots == []


def test_proposal_window_is_bounded_to_max_days():
    now = datetime(2026, 7, 8, 9, 0, tzinfo=_TZ)
    obj = {
        "is_scheduling": True,
        "proposed": [],
        "window_start_iso": "2026-07-08T00:00:00-04:00",
        "window_end_iso": "2027-01-01T00:00:00-04:00",  # absurdly far
    }
    p = rs._proposal_from_obj(obj, now)
    assert (p.window_end - p.window_start) <= timedelta(days=rs.MAX_WINDOW_DAYS)


# --- free/busy -------------------------------------------------------------


def test_compute_conflicts_flags_overlap_and_free():
    slots = [_slot(start="13:00", end="14:00"), _slot(start="16:00", end="17:00", label="call")]
    events = [_event("Standup", "2026-07-09T13:30:00+00:00", "2026-07-09T14:30:00+00:00")]
    results = rs.compute_conflicts(events, slots)
    assert len(results[0][1]) == 1  # 1pm overlaps standup
    assert results[1][1] == []  # 4pm is free


def test_compute_conflicts_ignores_free_and_cancelled_events():
    slots = [_slot(start="13:00", end="14:00")]
    events = [
        _event("OOO (free)", "2026-07-09T13:00:00+00:00", "2026-07-09T14:00:00+00:00", transparency="transparent"),
        _event("Cancelled thing", "2026-07-09T13:00:00+00:00", "2026-07-09T14:00:00+00:00", status="cancelled"),
    ]
    assert rs.compute_conflicts(events, slots)[0][1] == []


def test_compute_conflicts_adjacent_events_do_not_conflict():
    # Event ends exactly when the slot begins — half-open, no conflict.
    slots = [_slot(start="13:00", end="14:00")]
    events = [_event("Earlier", "2026-07-09T12:00:00+00:00", "2026-07-09T13:00:00+00:00")]
    assert rs.compute_conflicts(events, slots)[0][1] == []


# --- rendering -------------------------------------------------------------


def test_render_block_says_free_when_no_conflict():
    now = datetime(2026, 7, 9, 9, 0, tzinfo=_TZ)
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[_slot()], window_start=now, window_end=now)
    text = rs.render_availability_block(proposal, [], _TZ, "America/New_York", now)
    assert "FREE" in text and "CONFLICT" not in text


def test_render_block_flags_conflict_with_event_name():
    now = datetime(2026, 7, 9, 9, 0, tzinfo=_TZ)
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[_slot()], window_start=now, window_end=now)
    events = [_event("Dentist", "2026-07-09T13:00:00+00:00", "2026-07-09T14:00:00+00:00")]
    text = rs.render_availability_block(proposal, events, _TZ, "America/New_York", now)
    assert "CONFLICT" in text and "Dentist" in text


# --- accept-slot judge -----------------------------------------------------


def _fake_llm(content):
    return SimpleNamespace(invoke=lambda msgs: SimpleNamespace(content=content))


def test_judge_accepted_slot_returns_slot_on_yes():
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[_slot()])
    with patch.object(rs, 'get_llm', return_value=_fake_llm('{"accepted": true, "slot_index": 0}')):
        got = rs.judge_accepted_slot("yeah 1 works", proposal)
    assert got is proposal.slots[0]


def test_judge_accepted_slot_returns_none_on_decline():
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[_slot()])
    with patch.object(rs, 'get_llm', return_value=_fake_llm('{"accepted": false, "slot_index": -1}')):
        assert rs.judge_accepted_slot("cant do 1, how about 3", proposal) is None


def test_judge_accepted_slot_rejects_out_of_range_index():
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[_slot()])
    with patch.object(rs, 'get_llm', return_value=_fake_llm('{"accepted": true, "slot_index": 5}')):
        assert rs.judge_accepted_slot("ok", proposal) is None


def test_judge_accepted_slot_no_slots_skips_llm():
    proposal = rs.ScheduleProposal(is_scheduling=True, slots=[])
    # No LLM patch: must return None without invoking anything.
    assert rs.judge_accepted_slot("sure", proposal) is None


# --- orchestration wiring --------------------------------------------------

import asyncio  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _passthrough_run_blocking(executor, fn, *args):
    """Stand-in for utils.executors.run_blocking (mocked in the unit env): just call the
    (patched) sync function directly so the orchestration wiring is what's exercised."""
    return fn(*args)


def _avail_with_slot():
    return rs.AvailabilityContext(
        text="Fri 1pm: FREE",
        proposal=rs.ScheduleProposal(is_scheduling=True, slots=[_slot()]),
        has_calendar=True,
    )


def test_orchestration_creates_hold_when_reply_accepts_free_slot():
    hold = {'event_id': 'e1', 'title': '[Hold] lunch'}
    with patch.object(rs, 'run_blocking', _passthrough_run_blocking), patch.object(
        rs, 'build_availability_context', AsyncMock(return_value=_avail_with_slot())
    ), patch.object(rs, 'draft_reply', return_value={'draft': 'yeah 1 works', 'name': 'Sam'}), patch.object(
        rs, 'judge_accepted_slot', return_value=_slot()
    ), patch.object(
        rs, 'create_hold', AsyncMock(return_value=hold)
    ) as create:
        result, got = _run(rs.draft_reply_with_scheduling('u', 'Sam', [{'text': 'lunch fri 1?'}], None, False, ''))
    assert got == hold
    create.assert_awaited_once()


def test_orchestration_no_hold_when_reply_declines():
    with patch.object(rs, 'run_blocking', _passthrough_run_blocking), patch.object(
        rs, 'build_availability_context', AsyncMock(return_value=_avail_with_slot())
    ), patch.object(rs, 'draft_reply', return_value={'draft': 'cant do 1', 'name': 'Sam'}), patch.object(
        rs, 'judge_accepted_slot', return_value=None
    ), patch.object(
        rs, 'create_hold', AsyncMock()
    ) as create:
        _result, got = _run(rs.draft_reply_with_scheduling('u', 'Sam', [{'text': 'lunch fri 1?'}], None, False, ''))
    assert got is None
    create.assert_not_awaited()


def test_orchestration_no_hold_when_calendar_absent():
    avail = rs.AvailabilityContext(text="can't verify", proposal=_avail_with_slot().proposal, has_calendar=False)
    with patch.object(rs, 'run_blocking', _passthrough_run_blocking), patch.object(
        rs, 'build_availability_context', AsyncMock(return_value=avail)
    ), patch.object(rs, 'draft_reply', return_value={'draft': 'maybe', 'name': 'Sam'}), patch.object(
        rs, 'judge_accepted_slot', return_value=_slot()
    ) as judge, patch.object(
        rs, 'create_hold', AsyncMock()
    ) as create:
        _result, got = _run(rs.draft_reply_with_scheduling('u', 'Sam', [{'text': 'lunch fri 1?'}], None, False, ''))
    assert got is None
    judge.assert_not_called()  # gated out before the judge runs
    create.assert_not_awaited()


def test_orchestration_no_hold_when_ambiguous_person():
    with patch.object(rs, 'run_blocking', _passthrough_run_blocking), patch.object(
        rs, 'build_availability_context', AsyncMock(return_value=_avail_with_slot())
    ), patch.object(rs, 'draft_reply', return_value={'draft': 'which Sam?', 'ambiguous': True}), patch.object(
        rs, 'judge_accepted_slot', return_value=_slot()
    ) as judge, patch.object(
        rs, 'create_hold', AsyncMock()
    ) as create:
        _result, got = _run(rs.draft_reply_with_scheduling('u', 'Sam', [{'text': 'lunch fri 1?'}], None, False, ''))
    assert got is None
    judge.assert_not_called()
    create.assert_not_awaited()
