"""
Tests for the search_conversations tool in the standalone MCP server.

Validates the REST helper builds correct URLs/params, handles HTTP errors,
and the tool handler validates required arguments.
"""

import json
from unittest.mock import patch, MagicMock
import logging

import pytest

from mcp_server_omi.server import (
    search_conversations,
    SearchConversations,
    OmiTools,
)


class TestSearchConversationsHelper:
    """Tests for the search_conversations REST helper function."""

    def test_builds_correct_url_and_params(self):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "c1", "structured": {"title": "Result 1"}},
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server_omi.server.requests.get", return_value=mock_response) as mock_get:
            logger = logging.getLogger("test")
            result = search_conversations(logger, "omi_mcp_testkey", query="AI discussion", limit=5)

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "conversations/search" in call_args.args[0]
            assert call_args.kwargs["params"]["query"] == "AI discussion"
            assert call_args.kwargs["params"]["limit"] == 5
            assert call_args.kwargs["headers"]["Authorization"] == "Bearer omi_mcp_testkey"

        assert result == [{"id": "c1", "structured": {"title": "Result 1"}}]

    def test_passes_date_filters_when_provided(self):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server_omi.server.requests.get", return_value=mock_response) as mock_get:
            logger = logging.getLogger("test")
            search_conversations(
                logger, "omi_mcp_testkey",
                query="meeting",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

            params = mock_get.call_args.kwargs["params"]
            assert params["start_date"] == "2026-01-01"
            assert params["end_date"] == "2026-01-31"

    def test_omits_date_filters_when_none(self):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server_omi.server.requests.get", return_value=mock_response) as mock_get:
            logger = logging.getLogger("test")
            search_conversations(logger, "omi_mcp_testkey", query="test")

            params = mock_get.call_args.kwargs["params"]
            assert "start_date" not in params
            assert "end_date" not in params

    def test_raises_on_http_error(self):
        from requests.exceptions import HTTPError

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError("404 Not Found")

        with patch("mcp_server_omi.server.requests.get", return_value=mock_response):
            logger = logging.getLogger("test")
            with pytest.raises(HTTPError):
                search_conversations(logger, "omi_mcp_testkey", query="test")

    def test_does_not_log_raw_query(self):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server_omi.server.requests.get", return_value=mock_response):
            logger = MagicMock(spec=logging.Logger)
            search_conversations(logger, "key", query="my secret medical condition")

            log_message = logger.info.call_args[0][0]
            assert "my secret medical condition" not in log_message


class TestSearchConversationsModel:
    """Tests for the SearchConversations Pydantic model."""

    def test_query_is_required(self):
        schema = SearchConversations.model_json_schema()
        assert "query" in schema.get("required", [])

    def test_defaults_are_correct(self):
        model = SearchConversations(query="test")
        assert model.limit == 10
        assert model.start_date is None
        assert model.end_date is None
        assert model.api_key is None

    def test_all_fields_accepted(self):
        model = SearchConversations(
            api_key="omi_mcp_test",
            query="search term",
            limit=5,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        assert model.query == "search term"
        assert model.limit == 5
        assert model.start_date == "2026-01-01"


class TestOmiToolsEnum:
    """Verify the enum includes the new tool."""

    def test_search_conversations_in_enum(self):
        assert OmiTools.SEARCH_CONVERSATIONS == "search_conversations"

    def test_total_tool_count(self):
        assert len(OmiTools) == 7
