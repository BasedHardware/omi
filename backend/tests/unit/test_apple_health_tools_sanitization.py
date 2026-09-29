"""Unit tests verifying exception sanitization in Apple Health retrieval tools.

Failure-Class: none
Ensures internal database/API exception details and raw exception formats
are never returned directly in tool output strings.
"""

from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]
SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _setup_stubs(failing: bool = True):
    mock_integ = MagicMock()
    if failing:
        mock_integ.get.side_effect = RuntimeError(SENTINEL_ERROR)

    mock_integration_base = _module(
        "utils.retrieval.tools.integration_base",
        resolve_config_uid=lambda *args, **kwargs: ("test-uid-123", None),
        get_integration_checked=lambda *args, **kwargs: (mock_integ, None),
    )
    mock_users_db = _module(
        "database.users",
        get_integration=MagicMock(return_value=mock_integ),
    )
    mock_notifications_db = _module(
        "database.notifications",
        get_user_timezone=MagicMock(return_value="UTC"),
    )

    return {
        "utils.retrieval.tools.integration_base": mock_integration_base,
        "database.users": mock_users_db,
        "database.notifications": mock_notifications_db,
    }


def _load_tools():
    return load_module_fresh(
        "utils.retrieval.tools.apple_health_tools",
        str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "apple_health_tools.py"),
    )


def test_get_apple_health_steps_tool_exception_sanitized():
    with stub_modules(_setup_stubs(failing=True)):
        tools = _load_tools()
        result = tools.get_apple_health_steps_tool.func(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in result
    assert "Error retrieving step data" in result


def test_get_apple_health_sleep_tool_exception_sanitized():
    with stub_modules(_setup_stubs(failing=True)):
        tools = _load_tools()
        result = tools.get_apple_health_sleep_tool.func(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in result
    assert "Error retrieving sleep data" in result


def test_get_apple_health_heart_rate_tool_exception_sanitized():
    with stub_modules(_setup_stubs(failing=True)):
        tools = _load_tools()
        result = tools.get_apple_health_heart_rate_tool.func(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in result
    assert "Error retrieving heart rate data" in result


def test_get_apple_health_workouts_tool_exception_sanitized():
    with stub_modules(_setup_stubs(failing=True)):
        tools = _load_tools()
        result = tools.get_apple_health_workouts_tool.func(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in result
    assert "Error retrieving workout data" in result


def test_get_apple_health_summary_tool_exception_sanitized():
    with stub_modules(_setup_stubs(failing=True)):
        tools = _load_tools()
        result = tools.get_apple_health_summary_tool.func(config={"configurable": {"user_id": "test-uid-123"}})
    assert SENTINEL_ERROR not in result
    assert "Error retrieving health summary" in result
