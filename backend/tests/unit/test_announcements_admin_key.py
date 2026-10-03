"""Regression: announcements admin gate must compare secrets in constant time.

`_verify_admin_key` previously used `!=` on the ADMIN_KEY, diverging from the
`hmac.compare_digest` standard every sibling admin router follows
(fair_use_admin, feedback_admin, metrics, updates). Short-circuit comparison
leaks prefix length via timing; constant-time compare closes the side channel.
"""

import os
import sys
import types
import unittest.mock as mock

import pytest


class _HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _APIRouter:
    def __init__(self, *a, **k):
        self.routes = []

    def _dec(self, _m):
        def wrap(path, **kwargs):
            def decorator(func):
                self.routes.append((_m, path, kwargs, func))
                return func

            return decorator

        return wrap

    get = lambda self, *a, **k: self._dec("GET")(a[0], **k)  # noqa: E731
    post = lambda self, *a, **k: self._dec("POST")(a[0], **k)  # noqa: E731
    put = lambda self, *a, **k: self._dec("PUT")(a[0], **k)  # noqa: E731
    delete = lambda self, *a, **k: self._dec("DELETE")(a[0], **k)  # noqa: E731


def _identity(default=None, **_kwargs):
    return default


@pytest.fixture()
def announcements_router():
    saved = {}
    stubs = {}

    fastapi_stub = types.ModuleType("fastapi")
    fastapi_stub.APIRouter = _APIRouter
    fastapi_stub.Depends = _identity
    fastapi_stub.Header = _identity
    fastapi_stub.HTTPException = _HTTPException
    fastapi_stub.Query = _identity
    stubs["fastapi"] = fastapi_stub

    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kw):
            for kk, vv in kw.items():
                setattr(self, kk, vv)

    pydantic_stub.BaseModel = BaseModel
    stubs["pydantic"] = pydantic_stub

    for name in (
        "database.announcements",
        "models.announcement",
        "utils.other",
        "utils.other.endpoints",
    ):
        stubs[name] = mock.MagicMock()

    for name, mod in stubs.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = mod
    sys.modules.pop("routers.announcements", None)

    import importlib

    mod = importlib.import_module("routers.announcements")
    yield mod

    sys.modules.pop("routers.announcements", None)
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def test_admin_key_rejects_wrong_key(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "s3cr3t"}):
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("wrong")
        assert exc.value.status_code == 403


def test_admin_key_rejects_when_unset(announcements_router):
    with mock.patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ADMIN_KEY", None)
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("anything")
        assert exc.value.status_code == 403


def test_admin_key_accepts_exact_match(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "s3cr3t"}):
        announcements_router._verify_admin_key("s3cr3t")  # no raise


def test_admin_key_rejects_prefix_collision(announcements_router):
    """A shared-prefix guess must still fail — constant-time compare applied."""
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "s3cr3t-long-key"}):
        with pytest.raises(_HTTPException):
            announcements_router._verify_admin_key("s3cr3t")


def test_verify_uses_constant_time_compare(announcements_router):
    """Behavioral seam: hmac.compare_digest is the comparison primitive."""
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "s3cr3t"}):
        with mock.patch("routers.announcements.hmac.compare_digest", return_value=True) as spy:
            announcements_router._verify_admin_key("anything")
        spy.assert_called_once_with("anything", "s3cr3t")
