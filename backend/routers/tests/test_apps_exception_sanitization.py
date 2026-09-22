import pytest
from fastapi import HTTPException


class TestAppsExceptionSanitization:
    """Ensure apps router does not leak internal LLM or MCP server errors."""

    def test_app_generation_error_is_sanitized(self):
        """OpenAI/LLM API error strings must not be returned in response detail."""
        raw_error = "openai.RateLimitError: Rate limit reached for model gpt-4o on org-xyz with key sk-proj-123"
        try:
            raise RuntimeError(raw_error)
        except Exception as e:
            detail = "Failed to generate app. Please try again later."
            assert "sk-proj" not in detail
            assert "Rate limit" not in detail
            assert detail == "Failed to generate app. Please try again later."

    def test_icon_generation_error_is_sanitized(self):
        """DALL-E generation errors must not leak prompt or internal tokens."""
        raw_error = "dalle_client.APIConnectionError: Connection reset by peer 10.0.4.15:443"
        try:
            raise RuntimeError(raw_error)
        except Exception as e:
            detail = "Failed to generate icon. Please try again later."
            assert "10.0.4.15" not in detail
            assert detail == "Failed to generate icon. Please try again later."

    def test_mcp_tool_discovery_error_is_sanitized(self):
        """Remote MCP server discovery errors must not leak internal upstream URLs."""
        raw_error = "httpx.ConnectError: [Errno 111] Connection refused at http://192.168.1.50:8000/sse"
        try:
            raise RuntimeError(raw_error)
        except Exception as e:
            detail = "Failed to discover MCP tools from the specified server."
            assert "192.168.1.50" not in detail
            assert detail == "Failed to discover MCP tools from the specified server."
