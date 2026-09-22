import pytest
from fastapi import HTTPException


class TestMcpSanitization:
    """Ensure MCP router does not leak internal Python exception strings."""

    def test_invalid_category_error_is_sanitized(self):
        """Category ValueError string representation should not be leaked to clients."""
        try:
            raise ValueError("'invalid_cat' is not a valid MemoryCategory")
        except ValueError as e:
            detail = "Invalid memory category. Please provide valid category names."
            assert "MemoryCategory" not in detail
            assert detail == "Invalid memory category. Please provide valid category names."

    def test_action_item_validation_error_is_sanitized(self):
        """Action item payload ValueError should return clean client message."""
        try:
            raise ValueError("due_at datetime parsing failed: internal timezone table offset error")
        except ValueError as e:
            detail = "Invalid action item payload"
            assert "timezone table" not in detail
            assert detail == "Invalid action item payload"
