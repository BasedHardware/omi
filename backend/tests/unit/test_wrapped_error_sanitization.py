"""Hermetic unit tests for error sanitization in Wrapped generation and router.

Verifies that:
1. _run_wrapped_generation logs exception type and writes generic error without str(e).
2. generate_wrapped_2025 in backend/utils/wrapped/generate_2025.py logs exception type
   and writes generic error without str(e) or raw tracebacks.
3. get_wrapped_status sanitizes any legacy exception or traceback strings stored in the DB.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

WRAPPED_ROUTER_FILE = Path(__file__).resolve().parents[2] / "routers" / "wrapped.py"
WRAPPED_GEN_FILE = Path(__file__).resolve().parents[2] / "utils" / "wrapped" / "generate_2025.py"


def _get_function_source(file_path: Path, function_name: str) -> str:
    source = file_path.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class WrappedErrorSanitizationTests(unittest.TestCase):
    def test_run_wrapped_generation_sanitizes_errors(self):
        source = _get_function_source(WRAPPED_ROUTER_FILE, "_run_wrapped_generation")
        self.assertNotIn("error=str(e)", source)
        self.assertNotIn("logger.error(f\"Error in wrapped generation for user {uid}: {e}\")", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('error="Failed to generate Wrapped. Please try again later."', source)

    def test_get_wrapped_status_sanitizes_raw_db_errors(self):
        source = _get_function_source(WRAPPED_ROUTER_FILE, "get_wrapped_status")
        self.assertIn("raw_error = wrapped.get('error')", source)
        self.assertIn("Traceback", source)
        self.assertIn("Exception", source)
        self.assertIn("Failed to generate Wrapped. Please try again later.", source)

    def test_generate_wrapped_2025_sanitizes_errors(self):
        source = _get_function_source(WRAPPED_GEN_FILE, "generate_wrapped_2025")
        self.assertNotIn("error=str(e)", source)
        self.assertNotIn("traceback.print_exc()", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('error="Failed to generate Wrapped. Please try again later."', source)


if __name__ == "__main__":
    unittest.main()
