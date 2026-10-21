"""Unit tests for the announcements router boundary hardening.

Covers the guarantees the router gives the store layer:

- Admin key verification refuses an unset or whitespace only ADMIN_KEY and
  compares the key in constant time.
- Announcement ids are validated before they reach Firestore as document ids.
- Query parameters are rejected or clamped instead of silently accepted.
- Every endpoint turns a store failure into a static HTTP 500 and scrubs the
  raw error out of the logs.

The module is imported with the same stubs the sibling admin key regression
test uses, so the tests stay hermetic: no Firestore, no network, no
application startup.
"""

import importlib
import logging
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

    mod = importlib.import_module("routers.announcements")
    yield mod

    sys.modules.pop("routers.announcements", None)
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


@pytest.fixture(autouse=True)
def _no_admin_key():
    """No test may pass on a leaked ADMIN_KEY from the environment."""
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ADMIN_KEY", None)
        yield


# --- admin key verification -------------------------------------------------


def test_admin_key_is_refused_when_env_is_missing(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router._verify_admin_key("anything")
    assert exc.value.status_code == 403


def test_admin_key_is_refused_when_env_is_whitespace_only(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "   "}):
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("   ")
    assert exc.value.status_code == 403


def test_admin_key_is_refused_when_env_is_empty(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": ""}):
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("")
    assert exc.value.status_code == 403


def test_admin_key_is_refused_for_a_wrong_key(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("wrong-key")
    assert exc.value.status_code == 403


def test_admin_key_is_accepted_for_the_exact_key(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        announcements_router._verify_admin_key("correct-horse")


def test_admin_key_comparison_is_constant_time(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        with mock.patch("routers.announcements.hmac.compare_digest", return_value=True) as spy:
            announcements_router._verify_admin_key("correct-horse")
    spy.assert_called_once_with("correct-horse", "correct-horse")


def test_admin_key_comparison_survives_non_ascii_keys(announcements_router):
    """compare_digest refuses non ASCII strings, the guard must not 500."""
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "ké"}):
        # the exact key is still accepted, the comparison must not raise
        announcements_router._verify_admin_key("ké")
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "ké"}):
        with pytest.raises(_HTTPException) as exc:
            announcements_router._verify_admin_key("ki")
    assert exc.value.status_code == 403


# --- announcement id validation ----------------------------------------------


def test_require_id_strips_surrounding_whitespace(announcements_router):
    assert announcements_router._require_announcement_id("  release-1  ") == "release-1"


def test_require_id_accepts_a_normal_id(announcements_router):
    assert announcements_router._require_announcement_id("release-1") == "release-1"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_require_id_rejects_blank_ids(announcements_router, value):
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id(value)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("value", [".", ".."])
def test_require_id_rejects_dot_segments(announcements_router, value):
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id(value)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("value", ["a/b", "../etc/passwd", "folder/"])
def test_require_id_rejects_path_traversal(announcements_router, value):
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id(value)
    assert exc.value.status_code == 400


def test_require_id_rejects_reserved_firestore_names(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id("__shallow__")
    assert exc.value.status_code == 400


def test_require_id_rejects_oversized_ids(announcements_router):
    oversized = "a" * (announcements_router.MAX_ANNOUNCEMENT_ID_BYTES + 1)
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id(oversized)
    assert exc.value.status_code == 400


def test_require_id_measures_bytes_not_characters(announcements_router):
    allowed = "é" * 700
    assert announcements_router._require_announcement_id(allowed) == allowed

    too_big = "é" * 751
    with pytest.raises(_HTTPException) as exc:
        announcements_router._require_announcement_id(too_big)
    assert exc.value.status_code == 400


# --- query parameter validation ----------------------------------------------


def test_features_rejects_an_unknown_version_type(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router.get_features(version="1.0.0", version_type="desktop", device_model=None)
    assert exc.value.status_code == 400


def test_features_rejects_a_blank_version(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router.get_features(version="   ", version_type="app", device_model=None)
    assert exc.value.status_code == 400


def test_features_routes_firmware_to_the_firmware_store(announcements_router):
    seen = {}

    def _firmware(version, device_model):
        seen["version"] = version
        seen["device_model"] = device_model
        return []

    with mock.patch.object(announcements_router, "get_firmware_features", _firmware):
        with mock.patch.object(
            announcements_router,
            "get_app_features",
            lambda version: pytest.fail("app features must not be used for version_type=firmware"),
        ):
            assert announcements_router.get_features(version="2.1.0", version_type="firmware", device_model="omi") == []
    assert seen == {"version": "2.1.0", "device_model": "omi"}


def test_pending_rejects_a_blank_app_version(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router.get_pending_announcements_endpoint(
            app_version="  ",
            platform="ios",
            trigger="app_launch",
            firmware_version=None,
            device_model=None,
            uid="user-1",
        )
    assert exc.value.status_code == 400


def test_changelogs_clamps_the_limit(announcements_router):
    seen = {}

    def _recent(limit=None, max_version=None):
        seen["limit"] = limit
        return []

    with mock.patch.object(announcements_router, "get_recent_changelogs", _recent):
        announcements_router.get_changelogs(from_version=None, to_version=None, max_version=None, limit=5000)
    assert seen["limit"] == announcements_router.MAX_CHANGELOG_LIMIT


def test_changelogs_rejects_a_limit_below_one(announcements_router):
    with pytest.raises(_HTTPException) as exc:
        announcements_router.get_changelogs(from_version=None, to_version=None, max_version=None, limit=0)
    assert exc.value.status_code == 422


# --- store error boundaries --------------------------------------------------


def test_store_failure_becomes_a_static_500_and_the_error_is_scrubbed(announcements_router, caplog):
    secret = "supersecrettoken123456789"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"firestore exploded with {secret}")

    with mock.patch.object(announcements_router, "get_general_announcements", _boom):
        caplog.set_level(logging.ERROR)
        with pytest.raises(_HTTPException) as exc:
            announcements_router.get_announcements(last_checked_at=None)

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to load announcements"
    assert secret not in str(exc.value.detail)
    assert secret not in caplog.text


def test_store_failure_on_an_admin_endpoint_is_a_static_500(announcements_router):
    def _boom(*args, **kwargs):
        raise RuntimeError("firestore exploded")

    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        with mock.patch.object(announcements_router, "get_all_announcements", _boom):
            with pytest.raises(_HTTPException) as exc:
                announcements_router.list_all_announcements(
                    secret_key="correct-horse",
                    announcement_type=None,
                    active_only=False,
                )

    assert exc.value.status_code == 500
    assert "firestore exploded" not in str(exc.value.detail)


def test_an_http_error_inside_the_boundary_is_not_rewritten(announcements_router):
    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        with mock.patch.object(announcements_router, "get_announcement_by_id", lambda announcement_id: None):
            with pytest.raises(_HTTPException) as exc:
                announcements_router.get_announcement(announcement_id="missing", secret_key="correct-horse")

    assert exc.value.status_code == 404


def test_an_invalid_id_never_reaches_the_store(announcements_router):
    def _boom(announcement_id):
        pytest.fail("the store must not be reached with an invalid id")

    with mock.patch.dict(os.environ, {"ADMIN_KEY": "correct-horse"}):
        with mock.patch.object(announcements_router, "get_announcement_by_id", _boom):
            with pytest.raises(_HTTPException) as exc:
                announcements_router.get_announcement(announcement_id="../escape", secret_key="correct-horse")

    assert exc.value.status_code == 400
