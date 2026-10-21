"""Hermetic regression tests: create_omi_memory must POST to the v2 integration
import route the backend actually serves.

The backend exposes `POST /v2/integrations/{app_id}/user/memories?uid=...`
(backend/routers/integration.py). This plugin posted to
`/v1/integrations/{app_id}/memories`, which returns 404 in production, so every
emotion memory was dropped while the caller only saw a logged error.

Run: python3 plugins/hume-ai/test_create_omi_memory_route.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

APP_PATH = Path(__file__).resolve().parent / "app.py"

EXPECTED_ROUTE = "https://api.omi.me/v2/integrations/{app_id}/user/memories"


class _Response:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _install_stubs():
    """Stub the Hume SDK (network client) and httpx so app.py imports offline."""
    hume = types.ModuleType("hume")
    hume.AsyncHumeClient = mock.Mock()
    expression = types.ModuleType("hume.expression_measurement")
    stream = types.ModuleType("hume.expression_measurement.stream")
    stream.StreamLanguage = mock.Mock()
    stream_stream = types.ModuleType("hume.expression_measurement.stream.stream")
    stream_types = types.ModuleType("hume.expression_measurement.stream.stream.types")
    stream_types.Config = mock.Mock()
    hume.expression_measurement = expression
    expression.stream = stream
    stream.stream = stream_stream
    stream_stream.types = stream_types

    calls = []
    httpx = types.ModuleType("httpx")

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "headers": headers, "json": json})
            return _Response()

    httpx.AsyncClient = _AsyncClient

    for name, module in {
        "hume": hume,
        "hume.expression_measurement": expression,
        "hume.expression_measurement.stream": stream,
        "hume.expression_measurement.stream.stream": stream_stream,
        "hume.expression_measurement.stream.stream.types": stream_types,
        "httpx": httpx,
    }.items():
        sys.modules[name] = module
    return calls


def _load_app():
    spec = importlib.util.spec_from_file_location("hume_ai_app_under_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_posts_to_v2_user_memories_route(app, calls):
    calls.clear()
    result = asyncio.run(
        app.create_omi_memory(uid="user-1", text="felt calm today", app_id="app123", api_key="secret")
    )
    assert result.get("success") is True, result
    assert len(calls) == 1, calls
    url = calls[0]["url"]
    assert url.startswith(EXPECTED_ROUTE.format(app_id="app123") + "?uid=user-1"), url
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0]["json"]["text"] == "felt calm today"


def test_never_uses_retired_v1_route(app, calls):
    calls.clear()
    asyncio.run(app.create_omi_memory(uid="u", text="t", app_id="a", api_key="k"))
    url = calls[0]["url"]
    assert "/v1/integrations/" not in url, url
    assert "/user/memories" in url, url


def test_missing_config_returns_error_without_network(app, calls):
    calls.clear()
    with mock.patch.dict("os.environ", {}, clear=True):
        result = asyncio.run(app.create_omi_memory(uid="u", text="t", app_id=None, api_key=None))
    assert result.get("success") is False, result
    assert calls == [], calls


def main():
    calls = _install_stubs()
    app = _load_app()
    tests = [
        test_posts_to_v2_user_memories_route,
        test_never_uses_retired_v1_route,
        test_missing_config_returns_error_without_network,
    ]
    failures = 0
    for test in tests:
        try:
            test(app, calls)
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
