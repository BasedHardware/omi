"""Tests for X OAuth success_redirect_url allowlist.

Proves https://evil.example is rejected and native deep links
(omi://, omi-computer-dev://) are accepted — same policy as auth redirect_uri.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _ensure_package(name, path):
    module = sys.modules.get(name)
    if module is None or not hasattr(module, "__path__"):
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _install_module(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    parent_name, _, attr_name = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr_name, module)
    return module


# Lightweight stubs so routers.x_connector imports without heavy deps.
_ensure_package("database", BACKEND_DIR / "database")
_ensure_package("utils", BACKEND_DIR / "utils")
_ensure_package("routers", BACKEND_DIR / "routers")

x_posts_stub = _install_module("database.x_posts")
x_posts_stub.KIND_TWEET = "tweet"
x_posts_stub.KIND_BOOKMARK = "bookmark"
x_posts_stub.KIND_LIKE = "like"

x_connector_util_stub = _install_module("utils.x_connector")
executors_stub = _install_module("utils.executors")
executors_stub.start_background_task = lambda *a, **k: None
_ensure_package("utils.other", BACKEND_DIR / "utils" / "other")
endpoints_stub = _install_module("utils.other.endpoints")
endpoints_stub.get_current_user_uid = lambda: "uid"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.x_connector import (  # noqa: E402
    DEFAULT_DEEP_LINK,
    _validated_success_redirect,
    is_allowed_success_redirect_url,
)


@pytest.mark.parametrize(
    "uri",
    [
        "omi://x/callback",
        "omi-computer-dev://x/callback",
        "omi-computer://x/callback",
        "http://127.0.0.1:8765/callback",
        "http://localhost:3000/cb",
    ],
)
def test_allowed_success_redirect_urls(uri):
    assert is_allowed_success_redirect_url(uri) is True


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.example",
        "https://evil.example/steal",
        "http://attacker.example.com/cb",
        "javascript:alert(1)",
        "data:text/html,hi",
        "",
        "://missing-scheme",
    ],
)
def test_rejected_success_redirect_urls(uri):
    assert is_allowed_success_redirect_url(uri) is False


def test_callback_falls_back_to_default_for_https_evil():
    assert _validated_success_redirect("https://evil.example") == DEFAULT_DEEP_LINK


def test_callback_keeps_omi_deep_link():
    assert _validated_success_redirect("omi://x/callback") == "omi://x/callback"


def test_callback_keeps_dev_scheme():
    uri = "omi-computer-dev://auth/x"
    assert _validated_success_redirect(uri) == uri


def test_empty_falls_back_to_default():
    assert _validated_success_redirect(None) == DEFAULT_DEEP_LINK
    assert _validated_success_redirect("") == DEFAULT_DEEP_LINK
