"""Unit tests for demand_processing_tools input validation, clamping, and UID resolution."""

import json
import sys
from unittest.mock import MagicMock
import pytest

# Ensure parent and child modules exist in sys.modules
mock_demand_mod = MagicMock()
mock_conv_pkg = MagicMock()
mock_conv_pkg.demand_processing = mock_demand_mod
sys.modules["utils.conversations"] = mock_conv_pkg
sys.modules["utils.conversations.demand_processing"] = mock_demand_mod
sys.modules["utils.log_sanitizer"] = MagicMock()

import utils.retrieval.tools.demand_processing_tools as dpt_module
from utils.retrieval.tools.demand_processing_tools import (
    _resolve_uid,
    process_recent_conversations,
)


class TestDemandProcessingToolsGuards:
    """Hermetic unit tests for demand_processing_tools."""

    def test_resolve_uid(self):
        """Resolves user_id/uid across nested configurable and top-level configs."""
        assert _resolve_uid({"configurable": {"user_id": "usr_nested"}}) == "usr_nested"
        assert _resolve_uid({"configurable": {"uid": "usr_uid"}}) == "usr_uid"
        assert _resolve_uid({"user_id": "usr_top"}) == "usr_top"
        assert _resolve_uid({"uid": "uid_top"}) == "uid_top"

    def test_resolve_uid_invalid_or_none(self):
        """Returns None when config is missing or invalid."""
        assert _resolve_uid(None) is None
        assert _resolve_uid({}) is None
        assert _resolve_uid({"configurable": None}) is None
        assert _resolve_uid({"configurable": {}}) is None
        assert _resolve_uid({"configurable": "not_a_dict"}) is None
        assert _resolve_uid({"configurable": {"user_id": ""}}) is None

    def test_permission_error_when_no_owner(self):
        """Raises PermissionError when owner user ID is absent."""
        with pytest.raises(PermissionError, match="authenticated owner required"):
            process_recent_conversations.func(config=None)

        with pytest.raises(PermissionError, match="authenticated owner required"):
            process_recent_conversations.func(config={"configurable": {}})

    def test_hours_and_limit_clamping(self):
        """Coerces strings and clamps hours to [1, 6] and limit to [1, 20]."""
        cfg = {"configurable": {"user_id": "usr_123"}}
        mock_demand_mod.process_recent.reset_mock()
        mock_demand_mod.process_recent.return_value = {"ready": True, "processed": 5}

        # Hours above 6 clamped to 6, limit above 20 clamped to 20
        res = process_recent_conversations.func(hours=10, limit=50, config=cfg)
        data = json.loads(res)
        assert data["ready"] is True
        mock_demand_mod.process_recent.assert_called_with("usr_123", hours=6, limit=20)

        # String hours and limit safely coerced
        process_recent_conversations.func(hours="4", limit="15", config=cfg)
        mock_demand_mod.process_recent.assert_called_with("usr_123", hours=4, limit=15)

        # Hours below 1 clamped to 1, limit below 1 clamped to 1
        process_recent_conversations.func(hours=0, limit=-5, config=cfg)
        mock_demand_mod.process_recent.assert_called_with("usr_123", hours=1, limit=1)

        # None defaults to 6 and 20
        process_recent_conversations.func(hours=None, limit=None, config=cfg)
        mock_demand_mod.process_recent.assert_called_with("usr_123", hours=6, limit=20)

    def test_exception_handling(self):
        """Catches process_recent exceptions and returns clean error JSON."""
        cfg = {"user_id": "usr_123"}
        mock_demand_mod.process_recent.reset_mock()
        mock_demand_mod.process_recent.side_effect = RuntimeError("DB query failed")

        res = process_recent_conversations.func(config=cfg)
        data = json.loads(res)
        assert data["ready"] is False
        assert "Unable to process recent conversations right now." in data["error"]
