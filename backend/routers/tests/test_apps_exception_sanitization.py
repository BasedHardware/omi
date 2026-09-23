class TestAppsExceptionSanitization:
    """Ensure app generation and MCP tool discovery exceptions do not leak raw internals."""

    def test_app_generator_exception_is_sanitized(self):
        """App generation failure should return clean client message without internal traceback."""
        raw_msg = "VertexAI connection timeout: upstream internal endpoint dead"
        try:
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to generate app. Please try again later."
            assert "VertexAI" not in detail
            assert detail == "Failed to generate app. Please try again later."

    def test_icon_generator_exception_is_sanitized(self):
        """Icon generation failure should return clean user message."""
        raw_msg = "GCS permission denied for bucket omi-app-icons-internal"
        try:
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to generate app icon. Please try again later."
            assert "omi-app-icons-internal" not in detail
            assert detail == "Failed to generate app icon. Please try again later."

    def test_mcp_tool_discovery_exception_is_sanitized(self):
        """Tool discovery failure should return clean message without leaking tool URL/trace."""
        raw_msg = "Malformed SSE frame from http://mcp-agent.internal:8000/sse"
        try:
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to discover tools for app."
            assert "mcp-agent.internal" not in detail
            assert detail == "Failed to discover tools for app."
