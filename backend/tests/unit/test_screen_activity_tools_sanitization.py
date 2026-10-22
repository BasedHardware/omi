import os
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Canonical import from utils.retrieval.tools.screen_activity_tools
from utils.retrieval.tools.screen_activity_tools import (
    _get_uid,
    _chat_context_window,
    get_screen_activity_tool,
    search_screen_activity_tool,
)


def test_get_uid_resolution_variants():
    # 1. Standard configurable.user_id
    assert _get_uid({"configurable": {"user_id": "user_abc"}}) == "user_abc"
    # 2. Configurable uid fallback
    assert _get_uid({"configurable": {"uid": "user_def"}}) == "user_def"
    # 3. Top-level user_id fallback
    assert _get_uid({"user_id": "user_ghi"}) == "user_ghi"
    # 4. Top-level uid fallback
    assert _get_uid({"uid": "user_jkl"}) == "user_jkl"
    # 5. Non-string coercion
    assert _get_uid({"configurable": {"user_id": 12345}}) == "12345"
    # 6. None / empty
    assert _get_uid({}) is None
    assert _get_uid(None) is None


def test_chat_context_window_non_dict_config():
    clock_mock = MagicMock()
    clock_mock.tz = None
    window = _chat_context_window(12345, clock_mock)
    assert window is not None


def test_get_screen_activity_tool_missing_uid():
    result = get_screen_activity_tool.func(config={})
    assert result == "Error: User ID not found in configuration"


def test_get_screen_activity_tool_malformed_summary():
    with patch("database.screen_activity.get_screen_activity_summary", return_value=None):
        with patch("utils.retrieval.tools.screen_activity_tools.clock_for_config") as mock_clock:
            mock_clock.return_value = MagicMock()
            result = get_screen_activity_tool.func(config={"configurable": {"user_id": "test_user"}})
            assert "No synced screen observations are available" in result

    with patch("database.screen_activity.get_screen_activity_summary", return_value={"total_screenshots": 10}):
        with patch("utils.retrieval.tools.screen_activity_tools.clock_for_config") as mock_clock:
            mock_clock.return_value = MagicMock()
            result = get_screen_activity_tool.func(config={"configurable": {"user_id": "test_user"}})
            assert "No synced screen observations are available" in result


def test_get_screen_activity_tool_app_filter_trim():
    summary_data = {
        "total_screenshots": 2,
        "coverage": {},
        "apps": {
            "Google Chrome": {"count": 10, "window_titles": ["Google Search"]},
            "Visual Studio Code": {"count": 5, "window_titles": ["main.py"]},
        },
    }
    with patch("database.screen_activity.get_screen_activity_summary", return_value=summary_data):
        with patch("utils.retrieval.tools.screen_activity_tools.clock_for_config") as mock_clock:
            mock_clock.return_value = MagicMock()
            # Whitespace trimmed matching
            res_match = get_screen_activity_tool.func(
                app_filter="  Google Chrome  ",
                config={"configurable": {"user_id": "test_user"}},
            )
            assert "Google Chrome" in res_match
            assert "Visual Studio Code" not in res_match

            # Non-existent filter
            res_none = get_screen_activity_tool.func(
                app_filter="NonExistentApp",
                config={"configurable": {"user_id": "test_user"}},
            )
            assert "No observations for app 'NonExistentApp'" in res_none


def test_search_screen_activity_tool_empty_query():
    result_empty = search_screen_activity_tool.func(
        query="",
        config={"configurable": {"user_id": "test_user"}},
    )
    assert result_empty == "Error: Search query cannot be empty"

    result_ws = search_screen_activity_tool.func(
        query="    ",
        config={"configurable": {"user_id": "test_user"}},
    )
    assert result_ws == "Error: Search query cannot be empty"


def test_search_screen_activity_tool_missing_uid():
    result = search_screen_activity_tool.func(
        query="Python error",
        config={},
    )
    assert result == "Error: User ID not found in configuration"


def test_search_screen_activity_tool_limit_coercion():
    with patch("utils.retrieval.tools.screen_activity_tools.clock_for_config") as mock_clock, \
         patch("utils.retrieval.tools.screen_activity_tools.gemini_embed_query") as mock_embed, \
         patch("database.vector_db.search_screen_activity_vectors") as mock_vec:
        mock_clock.return_value = MagicMock()
        mock_embed.return_value = [0.1, 0.2]
        mock_vec.return_value = []

        # String limit coerced and clamped
        search_screen_activity_tool.func(
            query="valid search",
            limit="5",
            config={"configurable": {"user_id": "test_user"}},
        )
        assert mock_vec.call_args[1]["k"] == 5

        # Overflow limit clamped to 20
        search_screen_activity_tool.func(
            query="valid search",
            limit=999,
            config={"configurable": {"user_id": "test_user"}},
        )
        assert mock_vec.call_args[1]["k"] == 20

        # Negative limit clamped to 1
        search_screen_activity_tool.func(
            query="valid search",
            limit=-10,
            config={"configurable": {"user_id": "test_user"}},
        )
        assert mock_vec.call_args[1]["k"] == 1
