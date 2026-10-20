"""Tests verifying exception sanitization in memory_tools.py.

Ensures that unexpected internal exception details (e.g. raw Exception str(e),
internal DB failures, sensitive token strings) and inline traceback printing
are not leaked to LLM chat contexts or end-user screens.

Uses the sanctioned Tier-2 ``stub_modules`` + ``load_module_fresh`` pattern from
``testing.import_isolation`` so no module stubs leak into ``sys.modules``.
"""

import contextvars
import logging
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]
_SENSITIVE = "sensitive_firestore_internal_credentials_xyz_777"
_CONFIG = {"configurable": {"user_id": "user_123", "user_timezone": "UTC"}}


@pytest.fixture
def mt():
    """Load a fresh memory_tools module against stubbed heavy leaves."""

    def _pkg(name):
        mod = ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        return mod

    def _leaf(name, attrs=()):
        mod = ModuleType(name)
        for attr in attrs:
            setattr(mod, attr, MagicMock())
        return mod

    belief_mod = _leaf("utils.memory.belief_model")
    belief_mod.belief_model_enabled = MagicMock(return_value=False)
    belief_mod.memory_use_suppressed = MagicMock(return_value=False)
    belief_mod.normalize_temporal_read_view = MagicMock(return_value="useful_now")

    privacy_mod = _leaf("utils.messaging.memory_privacy")
    privacy_mod.channel_private_filter_active = MagicMock(return_value=False)
    privacy_mod.is_channel_private_memory = MagicMock(return_value=False)
    privacy_mod.omit_channel_private = MagicMock(side_effect=lambda items, _cfg: items)

    chat_scope_mod = _leaf("utils.retrieval.chat_scope")
    chat_scope_mod.apply_chat_scope_dates = MagicMock(return_value=(None, None, None))
    chat_scope_mod.chat_scope_from_config = MagicMock(return_value=None)

    mem_evidence_mod = _leaf("utils.retrieval.memory_evidence")
    mem_evidence_mod.MAX_MEMORY_EVIDENCE_CHARS = 1000
    mem_evidence_mod.format_memory_evidence = MagicMock(return_value="evidence")
    mem_evidence_mod.render_memory_evidence = MagicMock(return_value="rendered_evidence")

    result_bounds_mod = _leaf("utils.retrieval.tools.result_bounds")
    result_bounds_mod.cap_items_for_llm = MagicMock(return_value=([], 0, False))

    projection_mod = _leaf("utils.messaging.projection")
    projection_mod.surface_runtime = contextvars.ContextVar("surface_runtime", default=None)

    agentic_mod = _leaf("utils.retrieval.agentic")
    agentic_mod.agent_config_context = contextvars.ContextVar("agent_config", default=None)

    notif_mod = _leaf("database.notifications")
    notif_mod.get_user_time_zone = MagicMock(return_value="UTC")

    fakes = {
        "database": _pkg("database"),
        "database._client": _leaf("database._client", ["db"]),
        "database.notifications": notif_mod,
        "models": _pkg("models"),
        "models.memories": _leaf("models.memories", ["MemoryDB"]),
        "utils": _pkg("utils"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.memory_service": _leaf("utils.memory.memory_service", ["MemoryService"]),
        "utils.memory.belief_model": belief_mod,
        "utils.messaging": _pkg("utils.messaging"),
        "utils.messaging.memory_privacy": privacy_mod,
        "utils.messaging.projection": projection_mod,
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.chat_scope": chat_scope_mod,
        "utils.retrieval.turn_refs": _leaf("utils.retrieval.turn_refs", ["register_record_ref"]),
        "utils.retrieval.memory_evidence": mem_evidence_mod,
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "utils.retrieval.tools.result_bounds": result_bounds_mod,
        "utils.retrieval.agentic": agentic_mod,
    }
    with stub_modules(fakes):
        load_module_fresh(
            "utils.model_text",
            os.path.join(str(_BACKEND), "utils", "model_text.py"),
        )
        load_module_fresh(
            "utils.user_clock",
            os.path.join(str(_BACKEND), "utils", "user_clock.py"),
        )
        yield load_module_fresh(
            "utils.retrieval.tools.memory_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "memory_tools.py"),
        )


def test_unexpected_exception_in_search_memories_tool_is_sanitized(mt, caplog):
    mock_service_instance = MagicMock()
    mock_service_instance.search.side_effect = RuntimeError(f"Database query crash: {_SENSITIVE}")

    with patch.object(mt, "MemoryService", return_value=mock_service_instance), caplog.at_level(
        logging.ERROR, logger=mt.logger.name
    ):
        result = mt.search_memories_tool.func(
            query="coffee preferences",
            config=_CONFIG,
        )

    assert _SENSITIVE not in result
    assert "RuntimeError" not in result
    assert result == "Error searching memories. Please try again."
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info[0] is RuntimeError
    # The exception text can carry provider keys and user content; the log line
    # keeps the type only.
    assert _SENSITIVE not in error_records[0].getMessage()


def test_traceback_print_exc_not_called_in_search_memories_tool(mt):
    mock_service_instance = MagicMock()
    mock_service_instance.search.side_effect = RuntimeError("Crash")

    with patch.object(mt, "MemoryService", return_value=mock_service_instance), patch(
        "traceback.print_exc"
    ) as mock_print_exc:
        result = mt.search_memories_tool.func(
            query="coffee preferences",
            config=_CONFIG,
        )

    assert not mock_print_exc.called
    assert result == "Error searching memories. Please try again."


def test_config_not_available_returns_clean_error(mt):
    result = mt.search_memories_tool.func(query="test", config=None)
    assert result == "Error: Configuration not available"


def test_missing_user_id_returns_clean_error(mt):
    result = mt.search_memories_tool.func(
        query="test",
        config={"configurable": {}},
    )
    assert result == "Error: User ID not found in configuration"


def test_chat_scope_blocked_returns_clean_error(mt):
    with patch.object(
        mt,
        "_memory_tools_blocked_by_chat_scope",
        return_value="Error: Chat is scoped to a single conversation.",
    ):
        result = mt.search_memories_tool.func(
            query="test",
            config=_CONFIG,
        )
    assert result == "Error: Chat is scoped to a single conversation."
