"""Unit tests for demand_processing_tools input validation, clamping, and UID resolution."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import load_module_fresh

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def dpt():
    """Load demand_processing_tools hermetically with load_module_fresh."""
    return load_module_fresh(
        "utils.retrieval.tools._demand_processing_tools_test",
        str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "demand_processing_tools.py"),
    )


class TestDemandProcessingToolsGuards:
    """Hermetic unit tests for demand_processing_tools."""

    def test_resolve_uid(self, dpt):
        """Resolves user_id/uid across nested configurable and top-level configs."""
        assert dpt._resolve_uid({"configurable": {"user_id": "usr_nested"}}) == "usr_nested"
        assert dpt._resolve_uid({"configurable": {"uid": "usr_uid"}}) == "usr_uid"
        assert dpt._resolve_uid({"user_id": "usr_top"}) == "usr_top"
        assert dpt._resolve_uid({"uid": "uid_top"}) == "uid_top"

    def test_resolve_uid_invalid_or_none(self, dpt):
        """Returns None when config is missing or invalid."""
        assert dpt._resolve_uid(None) is None
        assert dpt._resolve_uid({}) is None
        assert dpt._resolve_uid({"configurable": None}) is None
        assert dpt._resolve_uid({"configurable": {}}) is None
        assert dpt._resolve_uid({"configurable": "not_a_dict"}) is None
        assert dpt._resolve_uid({"configurable": {"user_id": ""}}) is None

    def test_permission_error_when_no_owner(self, dpt):
        """Raises PermissionError when owner user ID is absent."""
        with pytest.raises(PermissionError, match="authenticated owner required"):
            dpt.process_recent_conversations.func(config=None)

        with pytest.raises(PermissionError, match="authenticated owner required"):
            dpt.process_recent_conversations.func(config={"configurable": {}})

    @patch("utils.conversations.demand_processing.process_recent")
    def test_hours_and_limit_clamping(self, mock_process, dpt):
        """Coerces strings and clamps hours to [1, 6] and limit to [1, 20]."""
        cfg = {"configurable": {"user_id": "usr_123"}}
        mock_process.return_value = {"ready": True, "processed": 5}

        # Hours above 6 clamped to 6, limit above 20 clamped to 20
        res = dpt.process_recent_conversations.func(hours=10, limit=50, config=cfg)
        data = json.loads(res)
        assert data["ready"] is True
        mock_process.assert_called_with("usr_123", hours=6, limit=20)

        # String hours and limit safely coerced
        dpt.process_recent_conversations.func(hours="4", limit="15", config=cfg)
        mock_process.assert_called_with("usr_123", hours=4, limit=15)

        # Hours below 1 clamped to 1, limit below 1 clamped to 1
        dpt.process_recent_conversations.func(hours=0, limit=-5, config=cfg)
        mock_process.assert_called_with("usr_123", hours=1, limit=1)

        # None defaults to 6 and 20
        dpt.process_recent_conversations.func(hours=None, limit=None, config=cfg)
        mock_process.assert_called_with("usr_123", hours=6, limit=20)

    @patch("utils.conversations.demand_processing.process_recent")
    def test_exception_handling(self, mock_process, dpt):
        """Catches process_recent exceptions and returns clean error JSON."""
        cfg = {"user_id": "usr_123"}
        mock_process.side_effect = RuntimeError("DB query failed")

        res = dpt.process_recent_conversations.func(config=cfg)
        data = json.loads(res)
        assert data["ready"] is False
        assert "Unable to process recent conversations right now." in data["error"]
