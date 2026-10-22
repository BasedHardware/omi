"""Unit tests verifying defensive user_id extraction, limit/max_results coercion,
and event title validation in calendar_tools.py and integration_base.py.

Ensures that:
1. Top-level user_id in config and None configurable mappings are handled gracefully
   without raising AttributeError or rejecting valid authenticated requests.
2. Negative or invalid limits in ensure_capped and cap_limit are defensively clamped
   to at least 1, preventing 400 Bad Request errors on backing APIs.
3. Empty or whitespace-only event titles in create_calendar_event_tool are rejected
   immediately before executing external network requests.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils.retrieval.tools.integration_base import (
    resolve_config_uid,
    ensure_capped,
    cap_limit,
)
from utils.retrieval.tools.calendar_tools import create_calendar_event_tool


class TestCalendarToolsHardening(unittest.TestCase):
    """Test user context resolution, limit clamping, and input validation."""

    def test_resolve_config_uid_nested(self):
        cfg = {"configurable": {"user_id": "nested_user_123"}}
        uid, err = resolve_config_uid(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "nested_user_123")

    def test_resolve_config_uid_top_level(self):
        cfg = {"user_id": "top_level_user_456"}
        uid, err = resolve_config_uid(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "top_level_user_456")

    def test_resolve_config_uid_none_configurable_with_top_level(self):
        cfg = {"configurable": None, "user_id": "fallback_user_789"}
        uid, err = resolve_config_uid(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "fallback_user_789")

    def test_resolve_config_uid_missing_user_id(self):
        cfg = {"configurable": {}}
        uid, err = resolve_config_uid(cfg)
        self.assertIsNone(uid)
        self.assertEqual(err, "Error: User ID not found in configuration")

    def test_resolve_config_uid_none_config(self):
        uid, err = resolve_config_uid(None)
        self.assertIsNone(uid)
        self.assertEqual(err, "Error: Configuration not available")

    def test_ensure_capped_clamps_negative_and_zero(self):
        self.assertEqual(ensure_capped(-10, 50, "warn"), 1)
        self.assertEqual(ensure_capped(0, 50, "warn"), 1)
        self.assertEqual(ensure_capped(25, 50, "warn"), 25)
        self.assertEqual(ensure_capped(100, 50, "warn"), 50)

    def test_ensure_capped_handles_invalid_types(self):
        self.assertEqual(ensure_capped("not_a_number", 50, "warn"), 1)
        self.assertEqual(ensure_capped(None, 50, "warn"), 1)

    def test_cap_limit_clamps_negative_and_zero(self):
        self.assertEqual(cap_limit(-5, 20), 1)
        self.assertEqual(cap_limit(0, 20), 1)
        self.assertEqual(cap_limit(10, 20), 10)
        self.assertEqual(cap_limit(50, 20), 20)

    def test_cap_limit_handles_invalid_types(self):
        self.assertEqual(cap_limit("invalid", 20), 1)
        self.assertEqual(cap_limit(None, 20), 1)

    def test_create_calendar_event_empty_title_short_circuits(self):
        with patch("utils.retrieval.tools.calendar_tools.create_google_calendar_event", new_callable=AsyncMock) as mock_create:
            for bad_title in ["", "   ", None]:
                res = asyncio.run(
                    create_calendar_event_tool.func(
                        title=bad_title,
                        start_time="2026-10-22T10:00:00Z",
                        end_time="2026-10-22T11:00:00Z",
                        config={"configurable": {"user_id": "test_user"}},
                    )
                )
                self.assertEqual(res, "Error: Event title cannot be empty.")
                mock_create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
