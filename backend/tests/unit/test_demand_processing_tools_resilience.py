"""Hermetic unit tests for demand_processing_tools resilience (#23337)."""

import json
from unittest.mock import Mock, patch
import pytest

from utils.retrieval.tools.demand_processing_tools import (
    _coerce_int,
    _extract_user_id,
    process_recent_conversations,
)


class TestNumericCoercion:
    """Test suite for _coerce_int validation and bounds clamping."""

    def test_coerce_int_valid_types(self):
        assert _coerce_int(4, default=6, min_val=1, max_val=6) == 4
        assert _coerce_int(4.0, default=6, min_val=1, max_val=6) == 4
        assert _coerce_int("4", default=6, min_val=1, max_val=6) == 4
        assert _coerce_int(" 4.0 ", default=6, min_val=1, max_val=6) == 4

    def test_coerce_int_clamping(self):
        # Under min
        assert _coerce_int(-5, default=6, min_val=1, max_val=6) == 1
        assert _coerce_int(0, default=6, min_val=1, max_val=6) == 1
        # Over max
        assert _coerce_int(10, default=6, min_val=1, max_val=6) == 6
        assert _coerce_int("100", default=20, min_val=1, max_val=20) == 20

    def test_coerce_int_invalid_fallback(self):
        assert _coerce_int(None, default=6, min_val=1, max_val=6) == 6
        assert _coerce_int("invalid", default=6, min_val=1, max_val=6) == 6
        assert _coerce_int([], default=20, min_val=1, max_val=20) == 20
        assert _coerce_int({}, default=20, min_val=1, max_val=20) == 20


class TestConfigExtraction:
    """Test suite for _extract_user_id supporting diverse invocation configurations."""

    def test_extract_standard_configurable(self):
        config = {"configurable": {"user_id": "user_123"}}
        assert _extract_user_id(config) == "user_123"

    def test_extract_configurable_uid_alias(self):
        config = {"configurable": {"uid": "user_456"}}
        assert _extract_user_id(config) == "user_456"

    def test_extract_top_level_user_id(self):
        config = {"user_id": "user_789"}
        assert _extract_user_id(config) == "user_789"

    def test_extract_missing_or_invalid(self):
        assert _extract_user_id(None) is None
        assert _extract_user_id({}) is None
        assert _extract_user_id({"configurable": {}}) is None
        assert _extract_user_id({"configurable": {"user_id": ""}}) is None
        assert _extract_user_id({"configurable": {"user_id": None}}) is None

    def test_extract_from_context_fallback(self):
        with patch("utils.retrieval.tools.demand_processing_tools._agent_config") as mock_agent_cfg:
            mock_agent_cfg.return_value = {"configurable": {"user_id": "context_user"}}
            assert _extract_user_id(None) == "context_user"


class TestProcessRecentConversationsTool:
    """Test suite for process_recent_conversations tool invocation."""

    def test_tool_args_schema_excludes_injected_config(self):
        assert set(process_recent_conversations.args) == {"hours", "limit"}

    def test_missing_owner_raises_permission_error(self):
        with pytest.raises(PermissionError, match="authenticated owner required"):
            process_recent_conversations.invoke({})

    def test_successful_invocation_with_coercion_and_clamping(self):
        with patch("utils.conversations.demand_processing.process_recent") as mock_proc:
            mock_proc.return_value = {"ready": True, "count": 5}
            raw = process_recent_conversations.invoke(
                {"hours": "100", "limit": "-5"},
                config={"configurable": {"user_id": "test_owner"}},
            )
            # Clamped hours=6, limit=1
            mock_proc.assert_called_once_with("test_owner", hours=6, limit=1)
            parsed = json.loads(raw)
            assert parsed["ready"] is True
            assert parsed["count"] == 5

    def test_downstream_exception_containment(self):
        with patch("utils.conversations.demand_processing.process_recent") as mock_proc:
            mock_proc.side_effect = RuntimeError("Redis connection failure")
            raw = process_recent_conversations.invoke(
                {"hours": 3, "limit": 10},
                config={"configurable": {"user_id": "test_owner"}},
            )
            mock_proc.assert_called_once_with("test_owner", hours=3, limit=10)
            parsed = json.loads(raw)
            assert parsed["ready"] is False
            assert parsed["status"] == "error"
            assert "Redis connection failure" in parsed["error"]
