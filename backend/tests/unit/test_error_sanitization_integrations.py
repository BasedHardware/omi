"""Unit tests for exception and information disclosure sanitization in backend routers.

Verifies that internal connection strings, hostnames, file paths, and environment variable
names are not leaked to API clients in HTTP 500 response bodies.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

# Set required environment variables before any imports
os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

class FlexibleModule(ModuleType):
    def __getattr__(self, name):
        val = MagicMock()
        setattr(self, name, val)
        return val

# Hermetic module stubs to avoid loading GCP / LangChain / external dependencies
google_mod = FlexibleModule("google")
google_mod.__path__ = []
google_cloud = FlexibleModule("google.cloud")
google_cloud.__path__ = []
google_cloud_exceptions = FlexibleModule("google.cloud.exceptions")
google_cloud_exceptions.__getattr__ = lambda name: type(name, (Exception,), {})
google_cloud_firestore = FlexibleModule("google.cloud.firestore")
google_cloud_firestore.transactional = lambda fn: fn
google_cloud_firestore.Client = MagicMock()
google_cloud_firestore_v1 = FlexibleModule("google.cloud.firestore_v1")
google_cloud_firestore_v1.__path__ = []
google_cloud_firestore_v1.FieldFilter = MagicMock()
google_cloud_firestore_v1.transactional = lambda fn: fn
base_query_mod = FlexibleModule("google.cloud.firestore_v1.base_query")
base_query_mod.FieldFilter = MagicMock()
google_cloud_firestore_v1.base_query = base_query_mod
sys.modules["google.cloud.firestore_v1.base_query"] = base_query_mod
google_cloud_storage = FlexibleModule("google.cloud.storage")
google_cloud_tasks_v2 = FlexibleModule("google.cloud.tasks_v2")
google_cloud_tasks_v2.CloudTasksClient = MagicMock()

google_cloud.exceptions = google_cloud_exceptions
google_cloud.firestore = google_cloud_firestore
google_cloud.firestore_v1 = google_cloud_firestore_v1
google_cloud.storage = google_cloud_storage
google_cloud.tasks_v2 = google_cloud_tasks_v2

google_oauth2 = sys.modules.get("google.oauth2") or ModuleType("google.oauth2")
google_oauth2.id_token = MagicMock()
google_oauth2.service_account = MagicMock()
google_oauth2.credentials = MagicMock()
setattr(google_mod, "oauth2", google_oauth2)

google_api_core = sys.modules.get("google.api_core") or ModuleType("google.api_core")
google_api_core.__path__ = []
google_api_core_exceptions = sys.modules.get("google.api_core.exceptions") or ModuleType("google.api_core.exceptions")
google_api_core_exceptions.__getattr__ = lambda name: type(name, (Exception,), {})
google_api_core.exceptions = google_api_core_exceptions

google_auth = sys.modules.get("google.auth") or ModuleType("google.auth")
google_auth_transport = sys.modules.get("google.auth.transport") or ModuleType("google.auth.transport")
google_auth_transport_requests = sys.modules.get("google.auth.transport.requests") or ModuleType("google.auth.transport.requests")
google_auth_transport_requests.Request = MagicMock()

firebase_admin = sys.modules.get("firebase_admin") or ModuleType("firebase_admin")
firebase_admin.__path__ = []
firebase_admin_auth = sys.modules.get("firebase_admin.auth") or ModuleType("firebase_admin.auth")
firebase_admin_auth.__getattr__ = lambda name: type(name, (Exception,), {})
firebase_admin.auth = firebase_admin_auth

for name, mod in [
    ("google", google_mod),
    ("google.cloud", google_cloud),
    ("google.cloud.exceptions", google_cloud_exceptions),
    ("google.cloud.firestore", google_cloud_firestore),
    ("google.cloud.firestore_v1", google_cloud_firestore_v1),
    ("google.cloud.storage", google_cloud_storage),
    ("google.cloud.tasks_v2", google_cloud_tasks_v2),
    ("google.oauth2", google_oauth2),
    ("google.api_core", google_api_core),
    ("google.api_core.exceptions", google_api_core_exceptions),
    ("google.auth", google_auth),
    ("google.auth.transport", google_auth_transport),
    ("google.auth.transport.requests", google_auth_transport_requests),
    ("firebase_admin", firebase_admin),
    ("firebase_admin.auth", firebase_admin_auth),
]:
    sys.modules[name] = mod

# Stub langchain, stripe, numpy, pinecone, dotenv
for p in ["langchain_core", "langchain_core.tools", "langchain_core.runnables", "stripe", "numpy", "pinecone", "dotenv"]:
    if p not in sys.modules:
        m = FlexibleModule(p)
        if "." not in p:
            m.__path__ = []
        sys.modules[p] = m
sys.modules["dotenv"].load_dotenv = lambda *args, **kwargs: None
sys.modules["langchain_core.tools"].tool = lambda fn: fn
sys.modules["langchain_core.runnables"].RunnableConfig = object

# Stub utils.retrieval.tools to avoid heavy database and LLM chains
google_utils_mod = FlexibleModule("utils.retrieval.tools.google_utils")
google_utils_mod.GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
google_utils_mod.GOOGLE_INTEGRATION_KEY = "google"
google_utils_mod.google_integration_has_scope = MagicMock()
sys.modules["utils.retrieval.tools.google_utils"] = google_utils_mod

tools_mod = FlexibleModule("utils.retrieval.tools")
tools_mod.__path__ = []
tools_mod.google_utils = google_utils_mod
sys.modules["utils.retrieval.tools"] = tools_mod

from fastapi import HTTPException, UploadFile
import pytest

from routers import integrations as integrations_router
from routers import updates as updates_router
from routers import imports as imports_router


def test_oauth_redis_failure_masks_internal_error(monkeypatch):
    """Ensure Redis connection/auth failure details are not leaked in get_oauth_url 500 response."""
    leak_text = "Connection refused to redis://prod-cluster.internal:6379 password=supersecretpass"

    mock_redis = MagicMock()
    mock_redis.setex.side_effect = RuntimeError(leak_text)
    monkeypatch.setattr(integrations_router.redis_db, "r", mock_redis)
    monkeypatch.setenv("BASE_API_URL", "https://api.omi.me")

    monkeypatch.setattr(
        integrations_router,
        "resolve_integration_provider",
        lambda app_key: ("github", {
            "name": "GitHub",
            "kind": "oauth",
            "oauth": {
                "client_id_env": "GITHUB_CLIENT_ID",
                "redirect_path": "/v1/integrations/github/callback"
            }
        })
    )

    with pytest.raises(HTTPException) as exc_info:
        integrations_router.get_oauth_url(app_key="github", uid="test_user")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to initialize OAuth flow"
    assert "prod-cluster.internal" not in exc_info.value.detail
    assert "supersecretpass" not in exc_info.value.detail


def test_oauth_unconfigured_client_id_masks_env_var(monkeypatch):
    """Ensure missing client ID does not leak internal environment variable names to callers."""
    mock_redis = MagicMock()
    monkeypatch.setattr(integrations_router.redis_db, "r", mock_redis)
    monkeypatch.setenv("BASE_API_URL", "https://api.omi.me")

    monkeypatch.setattr(
        integrations_router,
        "resolve_integration_provider",
        lambda app_key: ("notion", {
            "name": "Notion",
            "kind": "oauth",
            "oauth": {
                "client_id_env": "NOTION_INTERNAL_CLIENT_ID_SECRET",
                "redirect_path": "/v1/integrations/notion/callback"
            }
        })
    )

    monkeypatch.delenv("NOTION_INTERNAL_CLIENT_ID_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        integrations_router.get_oauth_url(app_key="notion", uid="test_user")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Notion integration is not configured"
    assert "NOTION_INTERNAL_CLIENT_ID_SECRET" not in exc_info.value.detail
    assert "missing" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_appcast_generation_masks_internal_error(monkeypatch):
    """Ensure XML generation errors do not leak internal filesystem paths or stack traces."""
    leak_text = "Parsing failed at /var/secrets/appcast_manifest.xml line 84: invalid token"

    monkeypatch.setattr(
        updates_router,
        "_get_live_desktop_releases",
        AsyncMock(side_effect=RuntimeError(leak_text))
    )

    with pytest.raises(HTTPException) as exc_info:
        await updates_router.get_desktop_appcast_xml(platform="macos", identity="stable")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Error generating appcast"
    assert "/var/secrets" not in exc_info.value.detail
    assert "line 84" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_import_save_failure_masks_file_path(monkeypatch):
    """Ensure disk I/O errors during limitless import do not leak filesystem paths."""
    leak_text = "[Errno 28] No space left on device: '/private/tmp/var/data/secret_archive.zip'"

    mock_file = AsyncMock(spec=UploadFile)
    mock_file.filename = "secret_archive.zip"
    mock_file.read.side_effect = OSError(leak_text)

    dummy_job = MagicMock()
    dummy_job.id = "job-123"

    async def mock_run_blocking(executor, fn, *args, **kwargs):
        if fn == imports_router.create_import_job:
            return dummy_job
        if fn == open:
            mock_f = MagicMock()
            mock_f.write = MagicMock()
            mock_f.close = MagicMock()
            return mock_f
        return MagicMock()

    monkeypatch.setattr(imports_router, "run_blocking", mock_run_blocking)

    with pytest.raises(HTTPException) as exc_info:
        await imports_router.import_limitless_data(file=mock_file, uid="test_uid")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save uploaded file"
    assert "/private/tmp/var/data" not in exc_info.value.detail
