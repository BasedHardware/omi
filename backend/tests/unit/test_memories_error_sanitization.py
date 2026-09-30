import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2]
MEMORIES_ROUTER_FILE = BACKEND_DIR / "routers" / "memories.py"


class MemoriesErrorSanitizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stubbed_modules = {}

        class StubModel(BaseModel):
            model_config = {"extra": "allow"}

        class StubDeviceScopeValidationError(ValueError):
            pass

        stub_names = [
            "database",
            "database._client",
            "database.legal_holds",
            "database.memory_imports",
            "database.review_queue",
            "database.conversations",
            "database.memories",
            "database.redis_db",
            "database.vector_db",
            "database.action_items",
            "database.external_data",
            "database.user_preferences",
            "models",
            "models.memories",
            "models.memory",
            "models.memory_imports",
            "models.action_item",
            "utils",
            "utils.client_device",
            "utils.observability",
            "utils.observability.fallback",
            "utils.product_metrics",
            "utils.feedback",
            "utils.jit_rollout",
            "utils.other",
            "utils.other.account_gate_http",
            "utils.other.endpoints",
            "utils.other.storage",
            "utils.other.list_budget",
            "utils.memory",
            "utils.memory.import_write_guard",
            "utils.memory.memory_api_contract",
            "utils.memory.memory_api_response",
            "utils.memory.universal_list_cursor",
            "utils.memory.memory_system",
            "utils.memory.device_scope_filter",
            "utils.memory.belief_model",
            "utils.memory.memory_service",
            "utils.memory.canonical_memory_adapter",
            "utils.memory.product_memory_read_service",
            "utils.retrieval",
            "utils.retrieval.rag",
            "utils.analytics",
            "utils.notifications",
            "utils.executors",
            "utils.apps",
            "testing",
            "testing.parity_pack_v0",
            "testing.parity_pack_v0.live_capture",
        ]

        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                mock_mod.__path__ = []
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        for mod in stub_names:
            if "." in mod:
                parent, child = mod.rsplit(".", 1)
                if parent in sys.modules:
                    setattr(sys.modules[parent], child, sys.modules[mod])

        sys.modules["utils.client_device"].DeviceScopeValidationError = StubDeviceScopeValidationError

        # Link model attributes with StubModel
        models_mem = sys.modules["models.memories"]
        models_mem.Memory = StubModel
        models_mem.MemoryDB = StubModel
        models_mem.CreateMemory = StubModel
        models_mem.UpdateMemory = StubModel
        models_mem.MemoryCategory = MagicMock()
        models_mem.Structured = StubModel

        models_imp = sys.modules["models.memory_imports"]
        models_imp.MemoryImportBatchRequest = StubModel
        models_imp.MemoryImportBatchResponse = StubModel

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            from routers.memories import _sanitize_memories_error
            import routers.memories as memories_mod
        except ImportError:
            import memories as memories_mod
            from memories import _sanitize_memories_error

        cls._sanitize_fn = staticmethod(_sanitize_memories_error)
        cls._router_mod = memories_mod
        cls._StubDeviceScopeValidationError = StubDeviceScopeValidationError

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_memories_error_unsupported_view(self):
        sanitize = self._sanitize_fn
        fallback = "Invalid memories query parameters"

        # 1. Unsupported read view with arbitrary user payload is sanitized
        err = ValueError("unsupported memory read view: <script>alert('xss')</script>")
        self.assertEqual(sanitize(err, fallback), "unsupported memory read view")

        # 2. Path injection attempt in view parameter is stripped
        err2 = ValueError("unsupported memory read view: ../../../etc/passwd")
        self.assertEqual(sanitize(err2, fallback), "unsupported memory read view")

    def test_sanitize_memories_error_device_scope(self):
        sanitize = self._sanitize_fn
        fallback = "Invalid memories query parameters"

        # Known safe device scope message
        err = self._StubDeviceScopeValidationError("device_scope must be one of: all, current, explicit")
        self.assertEqual(sanitize(err, fallback), "device_scope must be one of: all, current, explicit")

    def test_sanitize_memories_error_filters_sensitive_internals(self):
        sanitize = self._sanitize_fn
        fallback = "Invalid memories query parameters"

        sensitive_cases = [
            "Internal Firestore query failure at /databases/(default)/documents/users/u1/memories",
            "Traceback (most recent call last):\n  File 'belief.py', line 99\nKeyError: 'tier'",
            "PostgresDeadlockDetected: waiting for table lock on memories_ledger",
            "",
            "   ",
        ]

        for leak in sensitive_cases:
            err = ValueError(leak)
            self.assertEqual(sanitize(err, fallback), fallback)

    def test_no_raw_str_exc_in_memories_router(self):
        target_path = MEMORIES_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).resolve().parents[1] / "routers" / "memories.py"
        if not target_path.exists():
            target_path = Path(__file__).resolve().parents[0] / "memories.py"
        if not target_path.exists():
            target_path = Path.cwd() / "backend" / "routers" / "memories.py"
        if not target_path.exists():
            target_path = Path.cwd() / "memories.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertIn("_sanitize_memories_error", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)


if __name__ == "__main__":
    unittest.main()
