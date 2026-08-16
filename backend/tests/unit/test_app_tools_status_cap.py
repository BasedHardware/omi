"""Regression: the app-tool status-message cache must stay bounded.

utils.retrieval.tools.app_tools keeps a process-global _tool_status_messages map keyed by
{app_id}_{tool}. Every agentic chat turn that loads app tools writes new keys, and nothing evicted
them, so the map grew for the whole process lifetime (the repo's own rule requires module-level dicts
to cap or TTL). _remember_tool_status caps the map and evicts the oldest entry.
"""

import pytest

import utils.retrieval.tools.app_tools as app_tools


@pytest.fixture(autouse=True)
def _clear_status_cache():
    app_tools._tool_status_messages.clear()
    yield
    app_tools._tool_status_messages.clear()


def test_status_cache_is_bounded_and_evicts_oldest():
    cap = app_tools._MAX_TOOL_STATUS_MESSAGES
    for i in range(cap + 50):
        app_tools._remember_tool_status(f"app_{i}_tool", f"status {i}")

    assert len(app_tools._tool_status_messages) == cap
    # The oldest keys were evicted; the most recent are retained and still readable.
    assert "app_0_tool" not in app_tools._tool_status_messages
    assert f"app_{cap + 49}_tool" in app_tools._tool_status_messages
    assert app_tools.get_tool_status_message(f"app_{cap + 49}_tool") == f"status {cap + 49}"


def test_rewriting_a_key_refreshes_recency_without_growth():
    for i in range(5):
        app_tools._remember_tool_status(f"k{i}", f"v{i}")
    before = len(app_tools._tool_status_messages)

    app_tools._remember_tool_status("k0", "v0-updated")

    assert len(app_tools._tool_status_messages) == before  # updating an existing key does not grow the map
    assert app_tools.get_tool_status_message("k0") == "v0-updated"
