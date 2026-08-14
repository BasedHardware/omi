"""Regression: the proxy must not re-inject history a live VM session already holds.

The agent VM keeps its Claude session (and full conversation context) alive across
reconnects and announces it with a ``session_state`` hello. The proxy used to seed the
last-N Firestore history on the first query of *every* connection, keyed only on a
per-connection ``first_query_sent`` flag — so each mobile reconnect re-injected recent
turns the live session already had (duplicate context, wasted tokens). The seeding
decision now keys off the VM's reported session state.
"""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import firebase_admin
import pytest
from firebase_admin import firestore

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENT_PROXY_DIR = BACKEND_DIR / "agent-proxy"


@pytest.fixture
def agent_proxy(monkeypatch) -> ModuleType:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.syspath_prepend(str(AGENT_PROXY_DIR))  # main.py imports sibling `resilience`
    monkeypatch.setattr(firebase_admin, "initialize_app", MagicMock(return_value=object()))
    monkeypatch.setattr(firestore, "client", MagicMock(return_value=object()))
    spec = importlib.util.spec_from_file_location("agent_proxy_history_seeding_test", AGENT_PROXY_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HISTORY = [
    {"sender": "human", "text": "what did I do yesterday"},
    {"sender": "ai", "text": "You had 3 meetings."},
]


def test_current_time_prompt_uses_server_clock_and_mobile_timezone(agent_proxy):
    result = agent_proxy.current_time_prompt(
        "What year is it?",
        "America/New_York",
        now=datetime(2026, 7, 31, 2, 30, 45, tzinfo=timezone.utc),
    )

    assert result == "# Current Time\n2026-07-30T22:30:45-04:00 (America/New_York)\n\nWhat year is it?"


def test_current_time_prompt_falls_back_to_utc_for_invalid_mobile_timezone(agent_proxy):
    result = agent_proxy.current_time_prompt(
        "What year is it?",
        "Not/AZone",
        now=datetime(2026, 7, 31, 2, 30, 45, tzinfo=timezone.utc),
    )

    assert result == "# Current Time\n2026-07-31T02:30:45+00:00 (UTC)\n\nWhat year is it?"


def _patch_history(agent_proxy, monkeypatch) -> MagicMock:
    fetch = MagicMock(return_value=HISTORY)

    async def direct_run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_proxy, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(agent_proxy, "_fetch_chat_history", fetch)
    return fetch


@pytest.mark.asyncio
async def test_active_vm_session_skips_history_seeding(agent_proxy, monkeypatch):
    fetch = _patch_history(agent_proxy, monkeypatch)

    result = await agent_proxy._prepare_first_query_prompt("uid1", "sess1", "hello", vm_session_active=True)

    assert result == "hello"  # raw prompt, unchanged
    assert "<conversation_history>" not in result
    fetch.assert_not_called()  # no needless Firestore read on every reconnect


@pytest.mark.asyncio
async def test_fresh_vm_session_seeds_history(agent_proxy, monkeypatch):
    fetch = _patch_history(agent_proxy, monkeypatch)

    result = await agent_proxy._prepare_first_query_prompt("uid1", "sess1", "hello", vm_session_active=False)

    fetch.assert_called_once_with("uid1", "sess1")
    assert "<conversation_history>" in result
    assert "what did I do yesterday" in result
    assert result.endswith("hello")  # the current prompt rides after the seeded history


@pytest.mark.asyncio
async def test_history_failure_falls_back_to_raw_prompt_before_time_prefix(agent_proxy, monkeypatch):
    async def fail_history(*_args, **_kwargs):
        raise RuntimeError("Firestore unavailable")

    monkeypatch.setattr(agent_proxy, "_prepare_first_query_prompt", fail_history)

    result = await agent_proxy._prepare_first_query_prompt_with_fallback("uid1", "sess1", "hello", False)

    assert result == "hello"
