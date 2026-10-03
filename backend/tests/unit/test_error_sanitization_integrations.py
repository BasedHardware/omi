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

from fastapi import HTTPException, UploadFile
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

_STUB_MODULES = [
    "pinecone",
    "typesense",
    "stripe",
    "redis",
    "redis.asyncio",
    "numpy",
    "dotenv",
    "pytz",
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "google",
    "google.oauth2",
    "google.api_core",
    "google.api_core.exceptions",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud",
    "google.cloud.exceptions",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.cloud.storage",
    "google.cloud.tasks_v2",
    "database._client",
    "database.redis_db",
    "database.import_jobs",
    "database.apps",
    "database.user_usage",
    "services.integrations",
    "services.updates",
    "utils.apps",
    "utils.subscription",
    "utils.other.storage",
    "utils.imports.limitless",
    "utils.retrieval.tools",
    "utils.retrieval.tools.google_utils",
]

integrations_router = None
updates_router = None
imports_router = None


@pytest.fixture(scope="module", autouse=True)
def _isolate_dependencies():
    fakes = {name: AutoMockModule(name) for name in _STUB_MODULES}
    for name in ["google", "google.cloud", "google.cloud.firestore_v1", "firebase_admin", "redis"]:
        if name in fakes:
            fakes[name].__path__ = []

    fakes["dotenv"].load_dotenv = lambda *args, **kwargs: None
    fakes["langchain_core.tools"].tool = lambda fn: fn
    fakes["langchain_core.runnables"].RunnableConfig = object
    fakes["utils.retrieval.tools.google_utils"].GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
    fakes["utils.retrieval.tools.google_utils"].GOOGLE_INTEGRATION_KEY = "google"

    with stub_modules(fakes):
        from routers import integrations as _integrations_router
        from routers import updates as _updates_router
        from routers import imports as _imports_router

        mod = sys.modules[__name__]
        mod.integrations_router = _integrations_router
        mod.updates_router = _updates_router
        mod.imports_router = _imports_router
        yield


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
