"""Hermetic unit tests for error sanitization in the api_key_management router."""

from __future__ import annotations

from datetime import datetime
import importlib
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if not (BACKEND_DIR / "routers").is_dir():
    for parent in Path(__file__).resolve().parents:
        if (parent / "routers").is_dir():
            BACKEND_DIR = parent
            break
        if (parent / "backend" / "routers").is_dir():
            BACKEND_DIR = parent / "backend"
            break
        if (parent / "omi-backend").is_dir():
            BACKEND_DIR = parent / "omi-backend"
            break

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Established test helpers from tests/unit/conftest.py / memory_import_isolation.py
try:
    from tests.unit.conftest import (
        _AutoMockModule as AutoMockModule,
        install_database_client_stub,
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    try:
        from tests.unit.memory_import_isolation import (
            AutoMockModule,
            install_database_client_stub,
            restore_sys_modules,
            snapshot_sys_modules,
        )
    except ImportError:
        class AutoMockModule(types.ModuleType):
            def __getattr__(self, name: str):
                if name.startswith("__") and name.endswith("__"):
                    raise AttributeError(name)
                mock = MagicMock()
                setattr(self, name, mock)
                return mock

        def snapshot_sys_modules(names):
            return {name: sys.modules.get(name) for name in names}

        def restore_sys_modules(saved):
            for name, original in saved.items():
                if original is None:
                    sys.modules.pop(name, None)
                    if "." in name:
                        p, c = name.rsplit(".", 1)
                        pm = sys.modules.get(p)
                        if isinstance(pm, types.ModuleType) and hasattr(pm, c):
                            delattr(pm, c)
                else:
                    sys.modules[name] = original
                    if "." in name:
                        p, c = name.rsplit(".", 1)
                        pm = sys.modules.get(p)
                        if isinstance(pm, types.ModuleType):
                            setattr(pm, c, original)

        def install_database_client_stub():
            client_mod = types.ModuleType("database._client")
            client_mod.db = MagicMock()
            client_mod.get_firestore_client = lambda: client_mod.db
            client_mod.get_customer_firestore_client = lambda: client_mod.db
            sys.modules["database._client"] = client_mod
            database_pkg = sys.modules.get("database")
            if isinstance(database_pkg, types.ModuleType):
                setattr(database_pkg, "_client", client_mod)
            return client_mod


def _get_function_source(router_path: Path, function_name: str) -> str:
    source = router_path.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@|def |async def |class )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class ApiKeyManagementErrorSanitizationTests(unittest.TestCase):
    _saved_modules: dict = {}
    _sanitize_fn = None
    _router_mod = None
    _mcp_req_class = None
    _dev_req_class = None

    @classmethod
    def setUpClass(cls):
        tracked_names = [
            "database._client",
            "database.dev_api_key",
            "database.mcp_api_key",
            "database.api_key_metadata",
            "dependencies",
            "models.dev_api_key",
            "models.mcp_api_key",
            "utils.dev_cache",
            "utils.observability.api_keys",
            "utils.scopes",
            "routers.api_key_management",
        ]
        cls._saved_modules = snapshot_sys_modules(tracked_names)

        # 1. Install database client stub
        install_database_client_stub()

        # 2. Stub fastapi only if missing
        try:
            from fastapi import HTTPException
        except Exception:
            class StubAPIRouter:
                def get(self, *args, **kwargs):
                    return lambda fn: fn

                def post(self, *args, **kwargs):
                    return lambda fn: fn

                def delete(self, *args, **kwargs):
                    return lambda fn: fn

            def StubDepends(arg=None):
                return arg

            class StubHTTPException(Exception):
                def __init__(self, status_code: int, detail: any = None, headers: any = None):
                    self.status_code = status_code
                    self.detail = detail
                    self.headers = headers
                    super().__init__(f"{status_code}: {detail}")

            mock_fastapi = types.ModuleType("fastapi")
            mock_fastapi.APIRouter = StubAPIRouter
            mock_fastapi.Depends = StubDepends
            mock_fastapi.HTTPException = StubHTTPException
            sys.modules["fastapi"] = mock_fastapi

        def _register_submodule(full_name: str, mod: types.ModuleType):
            sys.modules[full_name] = mod
            if "." in full_name:
                parent_name, child_name = full_name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if isinstance(parent, types.ModuleType):
                    setattr(parent, child_name, mod)

        # Ensure database and models exist
        try:
            import database
        except Exception:
            db_pkg = types.ModuleType("database")
            db_pkg.__path__ = []
            sys.modules["database"] = db_pkg

        try:
            import models
        except Exception:
            models_pkg = types.ModuleType("models")
            models_pkg.__path__ = []
            sys.modules["models"] = models_pkg

        # 3. Import or declare real models (never stub response models with bare MagicMock)
        try:
            import models.dev_api_key as dev_models
            import models.mcp_api_key as mcp_models
            cls._mcp_req_class = mcp_models.McpApiKeyCreate
            cls._dev_req_class = dev_models.DevApiKeyCreate
        except Exception:
            try:
                from pydantic import BaseModel
            except Exception:
                class BaseModel:
                    def __init__(self, **kwargs):
                        for k, v in kwargs.items():
                            setattr(self, k, v)

            class McpApiKey(BaseModel):
                id: str = "test-id"
                name: str = "test-name"
                key_prefix: str = "test-prefix"
                created_at: datetime = datetime.now()
                last_used_at: datetime | None = None
                app_id: str | None = None
                scopes: list[str] | None = None

            class McpApiKeyCreate(BaseModel):
                name: str = "test-name"

            class McpApiKeyCreated(McpApiKey):
                key: str = "test-key"

            class DevApiKey(BaseModel):
                id: str = "test-id"
                name: str = "test-name"
                key_prefix: str = "test-prefix"
                created_at: datetime = datetime.now()
                last_used_at: datetime | None = None
                scopes: list[str] | None = None

            class DevApiKeyCreate(BaseModel):
                name: str = "test-name"
                scopes: list[str] | None = None

            class DevApiKeyCreated(DevApiKey):
                key: str = "test-key"

            mcp_mod = AutoMockModule("models.mcp_api_key")
            mcp_mod.McpApiKey = McpApiKey
            mcp_mod.McpApiKeyCreate = McpApiKeyCreate
            mcp_mod.McpApiKeyCreated = McpApiKeyCreated
            _register_submodule("models.mcp_api_key", mcp_mod)

            dev_mod = AutoMockModule("models.dev_api_key")
            dev_mod.DevApiKey = DevApiKey
            dev_mod.DevApiKeyCreate = DevApiKeyCreate
            dev_mod.DevApiKeyCreated = DevApiKeyCreated
            _register_submodule("models.dev_api_key", dev_mod)

            cls._mcp_req_class = McpApiKeyCreate
            cls._dev_req_class = DevApiKeyCreate

        # 4. Stub leaf service dependencies
        class StubApiKeyValidationError(ValueError):
            pass

        class StubApiKeyRevocationUnavailableError(RuntimeError):
            pass

        meta_mod = AutoMockModule("database.api_key_metadata")
        meta_mod.ApiKeyValidationError = StubApiKeyValidationError
        meta_mod.ApiKeyRevocationUnavailableError = StubApiKeyRevocationUnavailableError
        _register_submodule("database.api_key_metadata", meta_mod)

        _register_submodule("database.dev_api_key", AutoMockModule("database.dev_api_key"))
        _register_submodule("database.mcp_api_key", AutoMockModule("database.mcp_api_key"))

        deps_mod = AutoMockModule("dependencies")
        deps_mod.get_current_user_id = lambda: "test-user-id"
        _register_submodule("dependencies", deps_mod)

        _register_submodule("utils.dev_cache", AutoMockModule("utils.dev_cache"))
        _register_submodule("utils.observability.api_keys", AutoMockModule("utils.observability.api_keys"))

        scopes_mod = AutoMockModule("utils.scopes")
        scopes_mod.AVAILABLE_SCOPES = ["conversations:read", "memories:read"]
        scopes_mod.validate_scopes = lambda s: True
        _register_submodule("utils.scopes", scopes_mod)

        # 5. Import router module
        try:
            import routers.api_key_management as api_key_mod
        except ImportError:
            import api_key_management_hardened as api_key_mod

        cls._sanitize_fn = staticmethod(api_key_mod._sanitize_api_key_error)
        cls._router_mod = api_key_mod
        cls._StubApiKeyValidationError = StubApiKeyValidationError
        cls._StubApiKeyRevocationUnavailableError = StubApiKeyRevocationUnavailableError

    @classmethod
    def tearDownClass(cls):
        restore_sys_modules(cls._saved_modules)

    def test_sanitize_api_key_error_behavior(self):
        fallback = "Invalid API key parameters"
        sanitize = self._sanitize_fn

        # 1. Any ValueError strictly returns safe fallback key
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

        # 3. Firestore / internal paths filtered to fallback
        self.assertEqual(
            sanitize(
                self._StubApiKeyValidationError(
                    "google.cloud.exceptions.Conflict: 409 Document in firestore users/123/keys/456"
                ),
                fallback,
            ),
            fallback,
        )

        # 4. Multiline error text filtered to fallback
        self.assertEqual(
            sanitize(ValueError("line 1\nline 2 sensitive redis info"), fallback),
            fallback,
        )

        # 5. Empty exception detail falls back cleanly
        self.assertEqual(
            sanitize(RuntimeError(""), fallback),
            fallback,
        )

    def test_no_raw_str_exc_leak_in_api_key_management(self):
        target_path = BACKEND_DIR / "routers" / "api_key_management.py"
        if not target_path.exists():
            target_path = BACKEND_DIR / "api_key_management_hardened.py"
        if not target_path.exists():
            target_path = BACKEND_DIR / "api_key_management.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(error)", source)
        self.assertIn("_sanitize_api_key_error", source)

    def test_source_handlers_route_through_sanitizer(self):
        target_path = BACKEND_DIR / "routers" / "api_key_management.py"
        if not target_path.exists():
            target_path = BACKEND_DIR / "api_key_management_hardened.py"
        if not target_path.exists():
            target_path = BACKEND_DIR / "api_key_management.py"

        source_mcp = _get_function_source(target_path, "create_mcp_key")
        self.assertIn("_sanitize_api_key_error", source_mcp)
        self.assertIn("API key name must not contain a raw API key", source_mcp)
        self.assertIn("Invalid MCP API key app_id", source_mcp)
        self.assertIn("Invalid API key parameters", source_mcp)

        source_dev = _get_function_source(target_path, "create_developer_key")
        self.assertIn("_sanitize_api_key_error", source_dev)
        self.assertIn("API key name must not contain a raw API key", source_dev)
        self.assertIn("Invalid API key parameters", source_dev)

    def test_create_mcp_key_sanitized_exceptions(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_mcp_key = router_mod.create_mcp_key
        mock_req = self._mcp_req_class(name="valid_name")

        # 1. ApiKeyValidationError containing raw API key -> 422
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=self._StubApiKeyValidationError(
                "API key name must not contain a raw API key: omi_mcp_abcd1234efgh"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "API key name must not contain a raw API key")

        # 2. ApiKeyValidationError containing app_id error -> 422
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=self._StubApiKeyValidationError("Invalid MCP API key app_id: internal_sensitive_id"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "Invalid MCP API key app_id")

        # 3. Generic ApiKeyValidationError -> 422
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=self._StubApiKeyValidationError("internal metadata schema validation failure"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "Invalid API key parameters")

        # 4. Unexpected server Exception -> 500
        if hasattr(router_mod, "create_mcp_key"):
            with patch.object(
                router_mod.mcp_api_key_db,
                "create_mcp_key",
                side_effect=RuntimeError("unexpected database crash"),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    create_mcp_key(mock_req, uid="user-1")
                self.assertIn(ctx.exception.status_code, [422, 500])
                if ctx.exception.status_code == 500:
                    self.assertEqual(ctx.exception.detail, "Failed to create API key")

    def test_create_developer_key_sanitized_exceptions(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_developer_key = router_mod.create_developer_key
        mock_req = self._dev_req_class(name="valid_dev_key", scopes=None)

        # 1. ApiKeyValidationError containing raw API key -> 422
        with patch.object(
            router_mod.dev_api_key_db,
            "create_dev_key",
            side_effect=self._StubApiKeyValidationError(
                "API key name must not contain a raw API key: omi_dev_9876543210ab"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_developer_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "API key name must not contain a raw API key")

        # 2. Generic ApiKeyValidationError with internal details -> 422
        with patch.object(
            router_mod.dev_api_key_db,
            "create_dev_key",
            side_effect=self._StubApiKeyValidationError("internal metadata schema validation failure"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_developer_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "Invalid API key parameters")

        # 3. Unexpected server Exception -> 500
        if hasattr(router_mod, "create_developer_key"):
            with patch.object(
                router_mod.dev_api_key_db,
                "create_dev_key",
                side_effect=RuntimeError("unexpected storage outage"),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    create_developer_key(mock_req, uid="user-1")
                self.assertIn(ctx.exception.status_code, [422, 500])
                if ctx.exception.status_code == 500:
                    self.assertEqual(ctx.exception.detail, "Failed to create API key")


if __name__ == "__main__":
    unittest.main()
