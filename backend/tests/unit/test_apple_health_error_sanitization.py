import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

class AutoMockModule(ModuleType):
    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock

stub_modules = [
    "pinecone",
    "database.vector_db",
    "anthropic",
    "openai",
]
for mod in stub_modules:
    if mod not in sys.modules:
        sys.modules[mod] = AutoMockModule(mod)

tools_submodules = [
    "conversation_tools", "memory_tools", "action_item_tools", "omi_tools",
    "calendar_tools", "gmail_tools", "file_tools", "notification_settings_tools",
    "chart_tools", "screen_activity_tools", "frame_request_tools", "preference_tools",
    "web_tools", "graph_tools", "entity_timeline_tools", "knowledge_ledger_tools",
    "knowledge_ledger_write_tools", "app_tools", "web_search_tools", "generic_tools",
    "finance_tools", "contacts_tools",
]

for sub in tools_submodules:
    name = f"utils.retrieval.tools.{sub}"
    if name not in sys.modules:
        sys.modules[name] = AutoMockModule(name)

from utils.retrieval.tools.apple_health_tools import (
    get_apple_health_steps_tool,
    get_apple_health_sleep_tool,
    get_apple_health_heart_rate_tool,
    get_apple_health_workouts_tool,
    get_apple_health_summary_tool,
)


class ExplodingDict(dict):
    """A dictionary that raises a sensitive internal exception on access."""
    def get(self, key, default=None):
        raise RuntimeError("CRITICAL_INTERNAL_DB_PASSWORD_LEAK: postgres://admin:secret@db.internal:5432")


@pytest.fixture
def mock_exploding_access():
    with patch(
        "utils.retrieval.tools.apple_health_tools.prepare_apple_health_access",
        return_value=("test_uid_123", ExplodingDict(), None)
    ):
        yield


def test_steps_tool_sanitizes_exceptions(mock_exploding_access):
    res = get_apple_health_steps_tool.invoke({})
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in res
    assert "secret" not in res
    assert res == "Error retrieving step data from Apple Health. Please try again later."


def test_sleep_tool_sanitizes_exceptions(mock_exploding_access):
    res = get_apple_health_sleep_tool.invoke({})
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in res
    assert "secret" not in res
    assert res == "Error retrieving sleep data from Apple Health. Please try again later."


def test_heart_rate_tool_sanitizes_exceptions(mock_exploding_access):
    res = get_apple_health_heart_rate_tool.invoke({})
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in res
    assert "secret" not in res
    assert res == "Error retrieving heart rate data from Apple Health. Please try again later."


def test_workouts_tool_sanitizes_exceptions(mock_exploding_access):
    res = get_apple_health_workouts_tool.invoke({})
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in res
    assert "secret" not in res
    assert res == "Error retrieving workout data from Apple Health. Please try again later."


def test_summary_tool_sanitizes_exceptions(mock_exploding_access):
    res = get_apple_health_summary_tool.invoke({})
    assert "CRITICAL_INTERNAL_DB_PASSWORD_LEAK" not in res
    assert "secret" not in res
    assert res == "Error retrieving health summary from Apple Health. Please try again later."
