import logging
import pytest
from unittest import mock

# Import the function under test
from backend.utils.retrieval.tools.notification_settings_tools import (
    manage_daily_summary_tool,
)

# Helper to suppress logging during tests
logging.getLogger("backend.utils.retrieval.tools.notification_settings_tools").setLevel(
    logging.CRITICAL
)


@pytest.fixture
def user_id():
    return "test-user-123"


def test_manage_daily_summary_tool_enable_exception(user_id):
    """When setting enabled state raises an exception, the function returns an error."""
    with mock.patch(
        "backend.utils.retrieval.tools.notification_settings_tools.set_daily_summary_enabled",
        side_effect=Exception("DB timeout"),
    ):
        result = manage_daily_summary_tool(user_id, enable=True)
        assert "error" in result
        assert "Failed to update daily summary settings" in result["error"]


def test_manage_daily_summary_tool_hour_exception(user_id):
    """When setting hour raises an exception, the function returns an error."""
    with mock.patch(
        "backend.utils.retrieval.tools.notification_settings_tools.set_daily_summary_hour_local",
        side_effect=Exception("Permission denied"),
    ):
        result = manage_daily_summary_tool(user_id, hour=9)
        assert "error" in result
        assert "Failed to update daily summary hour" in result["error"]


def test_manage_daily_summary_tool_get_hour_exception(user_id):
    """When retrieving hour raises an exception, the function returns an error."""
    with mock.patch(
        "backend.utils.retrieval.tools.notification_settings_tools.get_daily_summary_hour_local",
        side_effect=Exception("Network error"),
    ):
        result = manage_daily_summary_tool(user_id)
        assert "error" in result
        assert "Failed to retrieve daily summary hour" in result["error"]
