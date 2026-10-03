"""Hermetic unit tests for error sanitization in the static map router.

Verifies that:
1. MalformedPinsError and ValueError in static_map.py route through _sanitize_static_map_error.
2. The _sanitize_static_map_error helper filters raw exception details and returns clean,
   structured fallback messages to external callers.
3. Unexpected provider exceptions during fetch_static_map are safely handled with HTTP 502
   and fallback recording without leaking internal stack traces.
4. No raw detail=str(error) or detail=str(exc) leaks remain in static_map.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
STATIC_MAP_ROUTER_FILE = BACKEND_DIR / "routers" / "static_map.py"


class StaticMapErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _sanitize_fn = None
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        class StubMalformedPinsError(ValueError):
            pass

        stub_names = [
            "utils",
            "utils.observability",
            "utils.observability.fallback",
            "utils.other",
            "utils.other.endpoints",
            "utils.static_map",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        sys.modules["utils.static_map"].MalformedPinsError = StubMalformedPinsError

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            from routers.static_map import _sanitize_static_map_error, get_static_map
            import routers.static_map as static_map_mod
        except ImportError:
            import static_map as static_map_mod
            from static_map import _sanitize_static_map_error, get_static_map

        cls._sanitize_fn = staticmethod(_sanitize_static_map_error)
        cls._router_mod = static_map_mod
        cls._StubMalformedPinsError = StubMalformedPinsError

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_static_map_error_behavior(self):
        fallback = "Invalid static map pin coordinates"
        sanitize = self._sanitize_fn

        # 1. Standard MalformedPinsError returns fallback
        self.assertEqual(
            sanitize(self._StubMalformedPinsError("pin coordinates out of bounds"), fallback),
            fallback,
        )

        # 2. Raw traceback filtered to fallback
        self.assertEqual(
            sanitize(
                ValueError("Traceback (most recent call last):\n  File 'x.py', line 1\nZeroDivisionError"),
                fallback,
            ),
            fallback,
        )

        # 3. Multiline error text filtered to fallback
        self.assertEqual(
            sanitize(ValueError("line 1\nline 2 sensitive redis info"), fallback),
            fallback,
        )

        # 4. Empty exception detail falls back cleanly
        self.assertEqual(
            sanitize(ValueError(""), fallback),
            fallback,
        )

    def test_no_raw_str_error_leak_in_static_map(self):
        target_path = STATIC_MAP_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "static_map.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertNotIn("detail=str(error)", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("_sanitize_static_map_error", source)

    def test_malformed_pins_sanitized_detail(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        get_static_map = router_mod.get_static_map

        with patch.object(
            router_mod,
            "parse_pins",
            side_effect=self._StubMalformedPinsError("pin coordinates out of bounds in redis key"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_static_map(pins="999,999", width=300, height=150, uid="user-1"))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertEqual(ctx.exception.detail, "Invalid static map pin coordinates")

    def test_unexpected_value_error_sanitized_detail(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        get_static_map = router_mod.get_static_map

        with patch.object(
            router_mod,
            "parse_pins",
            side_effect=ValueError("internal coordinate parsing exception"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_static_map(pins="invalid", width=300, height=150, uid="user-1"))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertEqual(ctx.exception.detail, "Invalid static map parameters")

    def test_provider_fetch_exception_returns_502(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        get_static_map = router_mod.get_static_map

        with patch.object(router_mod, "parse_pins", return_value=[(37.7749, -122.4194)]), patch.object(
            router_mod,
            "fetch_static_map",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused to maps provider"),
        ), patch.object(router_mod, "record_fallback") as mock_record:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(get_static_map(pins="37.7749,-122.4194", width=300, height=150, uid="user-1"))
            self.assertEqual(ctx.exception.status_code, 502)
            self.assertEqual(ctx.exception.detail, "Static map is temporarily unavailable")
            mock_record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
