"""Import stubs so the pinned checks run on the CI lane's bare `python3`.

The Hygiene lane installs only pyyaml, so `fastapi` and this app's siblings are
absent there. Tests that must exercise real app code register these stubs before
importing it. Each stub carries only the attributes the code under test touches
at import time or in an assertion -- deliberately not a fastapi emulation.
"""

from __future__ import annotations

import sys
from types import ModuleType


class StubResponse:
    """Records whatever a handler passed; the disconnect path builds these with kwargs."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class StubHTTPException(Exception):
    """Mirrors the two attributes the disconnect guard's callers read."""

    def __init__(self, status_code: int, detail: object = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def http_exception() -> type:
    """The real HTTPException when installed, else the stub above."""
    try:
        from fastapi import HTTPException

        return HTTPException
    except ImportError:
        return StubHTTPException


def _module(name: str, **attributes: object) -> ModuleType:
    value = ModuleType(name)
    value.__dict__.update(attributes)
    return value


def ensure_fastapi() -> None:
    """Register a minimal `fastapi` so modules doing `from fastapi import ...` load."""
    try:
        import fastapi  # noqa: F401

        return
    except ImportError:
        pass

    class _App:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    sys.modules["fastapi"] = _module(
        "fastapi",
        FastAPI=_App,
        Request=object,
        Query=lambda *a, **k: None,
        HTTPException=StubHTTPException,
    )
    sys.modules["fastapi.responses"] = _module(
        "fastapi.responses",
        HTMLResponse=StubResponse,
        RedirectResponse=StubResponse,
        JSONResponse=StubResponse,
    )


def app_module_stubs() -> dict:
    """Stubs for the sibling modules `main.py` imports, for `patch.dict(sys.modules, ...)`."""
    db = _module("db")
    for name in (
        "store_twitter_tokens",
        "get_twitter_tokens",
        "update_twitter_tokens",
        "delete_twitter_tokens",
        "store_oauth_state",
        "get_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    return {
        "dotenv": _module("dotenv", load_dotenv=lambda *a, **k: None),
        "requests": _module("requests"),
        "db": db,
        "models": _module("models", ChatToolResponse=ChatToolResponse),
    }


def load_main(app_dir: str):
    """Import `main.py` against stubs only, in any environment.

    Always stubs fastapi -- not just when it is missing -- because a real fastapi
    validates response models against the stubbed `models.ChatToolResponse` and
    rejects it. Stubbing both sides keeps this test identical on the CI lane and
    on a developer machine that has fastapi installed.
    """
    import importlib.util
    import os
    from unittest.mock import patch

    class _App:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    stubs = {
        "fastapi": _module(
            "fastapi",
            FastAPI=_App,
            Request=object,
            Query=lambda *a, **k: None,
            HTTPException=http_exception(),
        ),
        "fastapi.responses": _module(
            "fastapi.responses",
            HTMLResponse=StubResponse,
            RedirectResponse=StubResponse,
            JSONResponse=StubResponse,
        ),
        **app_module_stubs(),
    }
    spec = importlib.util.spec_from_file_location(
        "twitter_chat_tools_main_under_test", os.path.join(app_dir, "main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module
