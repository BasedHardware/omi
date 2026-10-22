"""Unit tests for omi_tools input validation, config support, and error handling."""

from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

with stub_modules({
    "utils.app_integrations": AutoMockModule("utils.app_integrations"),
    "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
}):
    import utils.retrieval.tools.omi_tools as ot_module
    from utils.retrieval.tools.omi_tools import get_omi_product_info_tool


class TestOmiToolsGuards:
    """Hermetic unit tests for omi_tools."""

    def test_tool_accepts_config_parameter(self):
        """Tool accepts RunnableConfig without TypeError."""
        mock_docs = {"Overview": "Omi is an open-source AI wearable."}
        with patch.object(ot_module, "get_github_docs_content", return_value=mock_docs):
            res = get_omi_product_info_tool.func(
                query="what is omi?",
                config={"configurable": {"user_id": "usr_123"}}
            )
            assert "Omi/Friend Product Documentation:" in res
            assert "## Overview" in res
            assert "Omi is an open-source AI wearable." in res

    def test_tool_invocable_without_arguments(self):
        """Tool can be invoked with no arguments or query=None."""
        mock_docs = {"Setup": "Turn on Bluetooth and pair."}
        with patch.object(ot_module, "get_github_docs_content", return_value=mock_docs):
            # No args
            res_default = get_omi_product_info_tool.func()
            assert "## Setup" in res_default

            # query=None
            res_none = get_omi_product_info_tool.func(query=None)
            assert "## Setup" in res_none

            # query as non-string
            res_int = get_omi_product_info_tool.func(query=42)
            assert "## Setup" in res_int

    def test_tool_handles_network_exception_softly(self):
        """Network or GitHub API failure fails soft with error message."""
        with patch.object(ot_module, "get_github_docs_content", side_effect=RuntimeError("GitHub API rate limit")):
            res = get_omi_product_info_tool.func(query="battery life")
            assert "Error: the Omi product documentation could not be retrieved right now" in res

    def test_tool_handles_empty_or_invalid_docs_payload(self):
        """Empty or non-dict docs returns graceful no documentation available message."""
        with patch.object(ot_module, "get_github_docs_content", return_value={}):
            res_empty = get_omi_product_info_tool.func(query="pricing")
            assert "No Omi product documentation is available right now" in res_empty

        with patch.object(ot_module, "get_github_docs_content", return_value=None):
            res_none = get_omi_product_info_tool.func(query="pricing")
            assert "No Omi product documentation is available right now" in res_none

        with patch.object(ot_module, "get_github_docs_content", return_value="string_not_dict"):
            res_str = get_omi_product_info_tool.func(query="pricing")
            assert "No Omi product documentation is available right now" in res_str
