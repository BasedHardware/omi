"""Cloud chat screen-activity tools must not read the retired Firestore/Pinecone mirror.

Desktop no longer syncs screen activity to the cloud. These tools remain in CORE_TOOLS for
prompt-cache prefix stability, but must fail closed so chat cannot answer from stale history.
"""

import os
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sa():
    def _pkg(name):
        mod = ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        return mod

    fakes = {
        "utils": _pkg("utils"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.retrieval.tools.screen_activity_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "screen_activity_tools.py"),
        )
        yield module


def _call_tool(tool_obj, **kwargs):
    # Sibling screen-activity tests may stub @tool as the identity; support both shapes.
    fn = getattr(tool_obj, "func", tool_obj)
    return fn(**kwargs)


def test_get_screen_activity_tool_fails_closed(sa):
    out = _call_tool(
        sa.get_screen_activity_tool,
        start_date="2025-01-15T00:00:00+00:00",
        end_date="2025-01-16T00:00:00+00:00",
        config={"configurable": {"user_id": "u1"}},
    )
    assert out == sa.SCREEN_ACTIVITY_CLOUD_UNAVAILABLE
    assert "no longer available from cloud chat" in out


def test_search_screen_activity_tool_fails_closed(sa):
    out = _call_tool(
        sa.search_screen_activity_tool,
        query="python error",
        config={"configurable": {"user_id": "u1"}},
    )
    assert out == sa.SCREEN_ACTIVITY_CLOUD_UNAVAILABLE
    assert "Rewind" in out
