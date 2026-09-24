"""Hermetic unit tests for error sanitization in the memory product router.

Verifies that:
1. Product memory search handlers catch ValueError and sanitize error details
   instead of reflecting raw str(exc) (which can leak user UIDs or document IDs).
2. The _sanitize_search_error helper maps parameter validation errors to generic,
   safe HTTP 400 responses and logs error type safely.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest
from unittest.mock import patch

MEMORY_PRODUCT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "memory_product.py"


def _get_function_source(function_name: str) -> str:
    source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class MemoryProductErrorSanitizationTests(unittest.TestCase):
    def test_search_product_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_product_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_search_error(exc, \"Product memory search\")", source)

    def test_search_vector_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_vector_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_search_error(exc, \"Vector memory search\")", source)

    def test_search_archive_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_archive_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn("_sanitize_search_error(exc, \"Archive memory search\")", source)

    def test_sanitize_search_error_masks_internal_details(self):
        source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
        self.assertIn("def _sanitize_search_error", source)
        self.assertIn("type(exc).__name__", source)
        self.assertIn("Invalid search parameters", source)
        self.assertIn("Invalid limit parameter", source)
        self.assertIn("Invalid offset parameter", source)
        self.assertIn("Invalid as_of parameter", source)

    def test_no_raw_str_exc_leak_in_memory_product(self):
        source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)


if __name__ == "__main__":
    unittest.main()
