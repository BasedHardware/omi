"""Hermetic regression: hume-ai create_omi_memory() must POST to the v2
user-import route the backend actually serves.

The plugin posted to /v1/integrations/{app_id}/memories, a route the
backend does not register, so every emotion-memory creation failed with
404 {"detail":"Not Found"} and the "create memory from detected
emotion" path was dead in production (issue #14340). The backend
registers POST /v2/integrations/{app_id}/user/memories among the
integration import routes; a missing route 404s while a live one asks
for the API key, which is how the dead path was confirmed.

The suite loads the plugin's app.py with the hume SDK stubbed, drives
the real create_omi_memory() through a capturing fake httpx client,
and pins the exact route. No network, no keys.

Run: python3 plugins/test_hume_omi_memory_route.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent


def _permissive(name):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.MagicMock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    return module


def _load_app():
    # app.py imports the hume SDK at module load; stub that whole tree.
    # httpx is imported inside create_omi_memory(); it is stubbed per-test.
    with mock.patch.dict(sys.modules, {
        "hume": _permissive("hume"),
        "hume.expression_measurement": _permissive("hume.expression_measurement"),
        "hume.expression_measurement.stream": _permissive("hume.expression_measurement.stream"),
        "hume.expression_measurement.stream.stream": _permissive("hume.expression_measurement.stream.stream"),
        "hume.expression_measurement.stream.stream.types": _permissive("hume.expression_measurement.stream.stream.types"),
    }):
        plugin_dir = str(PLUGINS_DIR / "hume-ai")
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)
        spec = importlib.util.spec_from_file_location(
            "hume_ai_app_under_test", PLUGINS_DIR / "hume-ai" / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class _CaptureClient:
    """Fake httpx.AsyncClient that records the request instead of sending it."""

    last_request = None

    def __init__(self, status_code=200):
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None, timeout=None):
        type(self).last_request = {
            "url": url,
            "headers": headers,
            "json": json,
        }
        return types.SimpleNamespace(status_code=self.status_code, text="ok")


def run():
    module = _load_plugin_app()

    # 1. The route must be the served v2 user-import route.
    client = _CaptureClient(status_code=200)
    with mock.patch.dict(sys.modules, {"httpx": types.SimpleNamespace(AsyncClient=lambda *a, **k: client)}):
        result = asyncio.run(
            module.create_omi_memory(uid="u1", text="t", app_id="app_x", api_key="k")
        )
    req = _CaptureClient.last_request
    assert req["url"] == (
        "https://api.omi.me/v2/integrations/app_x/user/memories?uid=u1"
    ), f"wrong route: {req['url']}"
    assert result.get("success") is True, result
    assert req["json"]["text"] == "t"
    assert req["headers"]["Authorization"] == "Bearer k"
    print(f"PASS route pinned: {req['url']}")

    # 2. The dead v1 route must be gone.
    assert "/v1/integrations/" not in req["url"], "dead v1 route still in use"
    assert "/memories?uid=" in req["url"]
    print("PASS dead v1 route no longer used")

    # 3. The error path still reports failures (non-2xx -> success False).
    client404 = _CaptureClient(status_code=404)
    with mock.patch.dict(sys.modules, {"httpx": types.SimpleNamespace(AsyncClient=lambda *a, **k: client404)}):
        result404 = asyncio.run(
            module.create_omi_memory(uid="u1", text="t", app_id="app_x", api_key="k")
        )
    assert result404.get("success") is False, result404
    print("PASS non-2xx still reported as failure")

    print("\n3 checks passed")


def _load_plugin_app():
    return _load_app()


if __name__ == "__main__":
    run()
