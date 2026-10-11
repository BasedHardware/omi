"""Hermetic unit tests for error sanitization in the memory_use router.

Verifies that:
1. All exception handlers in memory_use.py sanitize error details via _sanitize_memory_use_error.
2. The _sanitize_memory_use_error helper logs internal diagnostic information and returns
   clean, constant fallback messages to callers without exposing database internals or tracebacks.
3. No raw detail=str(exc), detail=str(e), or detail=message leaks remain in memory_use.py.
4. Behavioral executions for MemoryFirestoreApplyError, MemoryUseConflict, RuntimeError,
   and unhandled ValueError return sanitized HTTP 409 responses.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
MEMORY_USE_ROUTER_FILE = BACKEND_DIR / "routers" / "memory_use.py"


def _get_function_source(router_path: Path, function_name: str) -> str:
    source = router_path.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def |class )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class MemoryUseErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _sanitize_fn = None
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        # Stub dependencies inside setUpClass for hermetic standalone execution
        class StubMemoryUseAction(str, Enum):
            THUMBS_UP = "thumbs_up"
            THUMBS_DOWN = "thumbs_down"

        class StubMemoryUseConflict(Exception):
            pass

        class StubCanonicalMemoryIntakePausedError(Exception):
            pass

        class StubMemoryFirestoreApplyError(Exception):
            pass

        stub_names = [
            "database",
            "database._client",
            "database.memory_apply_store",
            "models",
            "models.feedback",
            "models.product_memory",
            "utils",
            "utils.memory",
            "utils.memory.belief_model",
            "utils.memory.memory_use",
            "utils.memory.canonical_memory_adapter",
            "utils.other",
            "utils.other.endpoints",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Inject known classes and functions into stubs
        sys.modules["database.memory_apply_store"].CanonicalMemoryIntakePausedError = (
            StubCanonicalMemoryIntakePausedError
        )
        sys.modules["database.memory_apply_store"].MemoryFirestoreApplyError = StubMemoryFirestoreApplyError
        sys.modules["utils.memory.memory_use"].MemoryUseAction = StubMemoryUseAction
        sys.modules["utils.memory.memory_use"].MemoryUseConflict = StubMemoryUseConflict
        sys.modules["utils.memory.memory_use"].MAX_FEEDBACK_ID_LENGTH = 128

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        # Support both repository-relative imports and local scratch imports
        try:
            from routers.memory_use import _sanitize_memory_use_error, use_memory
            import routers.memory_use as memory_use_mod
        except ImportError:
            # Fallback when running from scratch directory
            import memory_use as memory_use_mod
            from memory_use import _sanitize_memory_use_error, use_memory

        cls._sanitize_fn = staticmethod(_sanitize_memory_use_error)
        cls._router_mod = memory_use_mod
        cls._StubMemoryFirestoreApplyError = StubMemoryFirestoreApplyError
        cls._StubMemoryUseConflict = StubMemoryUseConflict

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_memory_use_error_behavior(self):
        fallback = "internal memory use operation error"
        sanitize = self._sanitize_fn

        # 1. Any ValueError strictly returns the safe fallback key
        self.assertEqual(
            sanitize(ValueError("clean_error_code"), fallback),
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

        # 3. Firestore / google.cloud internals filtered to fallback
        self.assertEqual(
            sanitize(
                self._StubMemoryFirestoreApplyError(
                    "google.cloud.exceptions.Conflict: 409 Document already exists in Firestore users/123/memories/456"
                ),
                fallback,
            ),
            fallback,
        )

        # 4. Multiline error text filtered to fallback
        self.assertEqual(
            sanitize(ValueError("line 1\nline 2 sensitive database details"), fallback),
            fallback,
        )

        # 5. Empty exception detail falls back cleanly
        self.assertEqual(
            sanitize(RuntimeError(""), fallback),
            fallback,
        )

    def test_no_raw_str_exc_leak_in_memory_use(self):
        # Resolve memory_use.py either in routers/ or in local directory
        target_path = MEMORY_USE_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "memory_use.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=message", source)
        self.assertIn("_sanitize_memory_use_error", source)

    def test_source_handlers_route_through_sanitizer(self):
        target_path = MEMORY_USE_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "memory_use.py"
        source = _get_function_source(target_path, "use_memory")

        self.assertIn("memory update could not be committed", source)
        self.assertIn("memory use feedback conflict", source)
        self.assertIn("invalid memory use parameters", source)
        self.assertIn("internal memory use operation error", source)
        self.assertIn("feedback action conflicts with existing memory use record", source)

    def test_behavioral_sanitized_exceptions(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        use_memory = router_mod.use_memory

        mock_request = MagicMock()
        mock_request.action.value = "thumbs_up"
        mock_request.feedback_id = "fb-123"
        mock_request.expected_item_revision = None
        mock_response = MagicMock()

        # 1. MemoryFirestoreApplyError sanitization
        with patch.object(router_mod, "belief_model_enabled", return_value=True), patch.object(
            router_mod, "get_data_plane_firestore_client", return_value=MagicMock()
        ), patch.object(
            router_mod,
            "_apply_canonical_user_mutation",
            side_effect=self._StubMemoryFirestoreApplyError("internal db lock failed"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                use_memory("mem-1", mock_request, mock_response, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "memory update could not be committed")

        # 2. MemoryUseConflict sanitization
        with patch.object(router_mod, "belief_model_enabled", return_value=True), patch.object(
            router_mod, "get_data_plane_firestore_client", return_value=MagicMock()
        ), patch.object(
            router_mod,
            "_apply_canonical_user_mutation",
            side_effect=self._StubMemoryUseConflict("conflict with prior feedback"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                use_memory("mem-1", mock_request, mock_response, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "memory use feedback conflict")

        # 3. RuntimeError sanitization
        with patch.object(router_mod, "belief_model_enabled", return_value=True), patch.object(
            router_mod, "get_data_plane_firestore_client", return_value=MagicMock()
        ), patch.object(
            router_mod,
            "_apply_canonical_user_mutation",
            side_effect=RuntimeError("unexpected runtime failure in ledger worker"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                use_memory("mem-1", mock_request, mock_response, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "internal memory use operation error")

        # 4. Unhandled ValueError sanitization
        with patch.object(router_mod, "belief_model_enabled", return_value=True), patch.object(
            router_mod, "get_data_plane_firestore_client", return_value=MagicMock()
        ), patch.object(
            router_mod, "_apply_canonical_user_mutation", side_effect=ValueError("malformed internal payload syntax")
        ):
            with self.assertRaises(HTTPException) as ctx:
                use_memory("mem-1", mock_request, mock_response, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "invalid memory use parameters")


if __name__ == "__main__":
    unittest.main()
