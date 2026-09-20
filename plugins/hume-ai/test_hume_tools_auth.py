"""Hermetic regression tests for the auth guard on the uid-keyed hume-ai routes.

Before this fix, `POST /audio`, `POST /save-emotion-memory` and
`POST /force-send-notification` took `uid` from the query string with no caller
authentication, so anyone could write emotion memories into any Omi account
with the app's `OMI_API_KEY` and push notifications to any user. Every one of
those routes must now carry `require_hume_tools_auth`, which fails closed (503)
when `HUME_TOOLS_SECRET` is unset and rejects missing/wrong tokens with 401.

The FastAPI layer, uvicorn, dotenv and the Hume SDK are stubbed so the suite
runs on the standard library only.

Run: python3 plugins/hume-ai/test_hume_tools_auth.py
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parent
MAIN_PATH = APP_DIR / "main.py"

SECRET = "test-hume-tools-secret"

# Routes that act on a caller-supplied uid and must be guarded.
GUARDED_ROUTES = ("/audio", "/save-emotion-memory", "/force-send-notification")

# Routes that must stay reachable without the shared secret.
PUBLIC_ROUTES = ("/", "/status", "/analyze-text", "/emotion-config", "/reset-stats", "/health")

_APP_INSTANCES = []


class HTTPException(Exception):
    """Stand-in for fastapi.HTTPException."""

    def __init__(self, status_code=None, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Depends:
    """Stand-in for fastapi.Depends that keeps the callable it wraps."""

    def __init__(self, dependency=None, **kwargs):
        self.dependency = dependency


class _RecordingApp:
    """Minimal FastAPI stand-in that records each route's dependencies."""

    def __init__(self, *args, **kwargs):
        self.title = kwargs.get("title")
        self.routes = {}
        _APP_INSTANCES.append(self)

    def _record(self, method, path, kwargs):
        self.routes[(method, path)] = list(kwargs.get("dependencies") or [])

        def decorator(func):
            return func

        return decorator

    def post(self, path, **kwargs):
        return self._record("POST", path, kwargs)

    def get(self, path, **kwargs):
        return self._record("GET", path, kwargs)

    def on_event(self, event):
        def decorator(func):
            return func

        return decorator


def _install_stubs():
    """Stub every third-party import reached while loading main.py."""
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = _RecordingApp
    fastapi.Request = object
    fastapi.Query = lambda *args, **kwargs: None
    fastapi.HTTPException = HTTPException
    fastapi.Depends = Depends

    responses = types.ModuleType("fastapi.responses")
    responses.JSONResponse = lambda *args, **kwargs: None
    responses.HTMLResponse = object
    fastapi.responses = responses

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *args, **kwargs: None
    fastapi.templating = templating

    uvicorn = types.ModuleType("uvicorn")
    uvicorn.run = lambda *args, **kwargs: None

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    # Hume SDK: app.py imports the client and stream types at module scope.
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

    for name, module in {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.templating": templating,
        "uvicorn": uvicorn,
        "dotenv": dotenv,
        "hume": hume,
        "hume.expression_measurement": expression,
        "hume.expression_measurement.stream": stream,
        "hume.expression_measurement.stream.stream": stream_stream,
        "hume.expression_measurement.stream.stream.types": stream_types,
    }.items():
        sys.modules[name] = module


def _load_main():
    sys.path.insert(0, str(APP_DIR))
    try:
        spec = importlib.util.spec_from_file_location("hume_ai_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(APP_DIR))
    app = _APP_INSTANCES[-1]
    return module, app


class _FakeRequest:
    def __init__(self, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


def _guarded_dependencies(app, method, path):
    deps = app.routes.get((method, path))
    assert deps is not None, f"{method} {path} is not registered"
    return [getattr(d, "dependency", d) for d in deps]


def test_uid_keyed_routes_require_the_shared_secret(main, app):
    assert hasattr(main, "require_hume_tools_auth"), "main.py does not wire the shared-secret guard"
    guard = main.require_hume_tools_auth
    for path in GUARDED_ROUTES:
        dependencies = _guarded_dependencies(app, "POST", path)
        assert guard in dependencies, f"POST {path} is missing the auth guard: {dependencies}"


def test_root_audio_route_is_guarded_too(main, app):
    # `/audio` ingests caller audio under a victim uid with send_notification=true,
    # so it is part of the same defect class as the two explicit routes.
    dependencies = _guarded_dependencies(app, "POST", "/audio")
    assert main.require_hume_tools_auth in dependencies, dependencies


def test_read_only_routes_stay_public(main, app):
    for method, path in (("GET", "/"), ("GET", "/status"), ("GET", "/health"), ("GET", "/emotion-config")):
        dependencies = _guarded_dependencies(app, method, path)
        assert main.require_hume_tools_auth not in dependencies, f"{method} {path} must stay public"


def test_unconfigured_secret_fails_closed(main, app):
    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            main.require_hume_tools_auth(_FakeRequest())
        except HTTPException as exc:
            assert exc.status_code == 503, exc.status_code
        else:
            raise AssertionError("expected 503 when HUME_TOOLS_SECRET is unset")


def test_blank_secret_fails_closed(main, app):
    with mock.patch.dict(os.environ, {"HUME_TOOLS_SECRET": "   "}, clear=True):
        try:
            main.require_hume_tools_auth(_FakeRequest())
        except HTTPException as exc:
            assert exc.status_code == 503, exc.status_code
        else:
            raise AssertionError("expected 503 when HUME_TOOLS_SECRET is blank")


def test_missing_and_wrong_tokens_rejected(main, app):
    with mock.patch.dict(os.environ, {"HUME_TOOLS_SECRET": SECRET}, clear=True):
        for request in (
            _FakeRequest(),
            _FakeRequest(headers={"Authorization": "Bearer wrong"}),
            _FakeRequest(headers={"Authorization": f"Token {SECRET}"}),
            _FakeRequest(query_params={"hume_tools_token": "wrong"}),
        ):
            try:
                main.require_hume_tools_auth(request)
            except HTTPException as exc:
                assert exc.status_code == 401, exc.status_code
            else:
                raise AssertionError(f"expected 401 for {request.headers} {request.query_params}")


def test_bearer_and_query_tokens_accepted(main, app):
    with mock.patch.dict(os.environ, {"HUME_TOOLS_SECRET": SECRET}, clear=True):
        assert main.require_hume_tools_auth(_FakeRequest(headers={"Authorization": f"Bearer {SECRET}"})) is None
        assert main.require_hume_tools_auth(_FakeRequest(query_params={"hume_tools_token": SECRET})) is None


def main():
    _install_stubs()
    module, app = _load_main()
    tests = [
        test_uid_keyed_routes_require_the_shared_secret,
        test_root_audio_route_is_guarded_too,
        test_read_only_routes_stay_public,
        test_unconfigured_secret_fails_closed,
        test_blank_secret_fails_closed,
        test_missing_and_wrong_tokens_rejected,
        test_bearer_and_query_tokens_accepted,
    ]
    failures = 0
    for test in tests:
        try:
            test(module, app)
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - report every failure, never crash the runner
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
