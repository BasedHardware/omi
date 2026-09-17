"""Hermetic regression tests: create_fact must post to the Integration Import API
route the backend actually serves, `POST /v2/integrations/{app_id}/user/memories?uid=...`
(backend/routers/integration.py). It posted to `/user/facts`, which is not a route
(404 in production), so every Notion/Composio memory sync failed.

Run: python3 plugins/composio/test_omi_api_route.py
"""

import importlib.util
import os
import sys
import types
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
MODULE_PATH = SRC_DIR / "omi_api.py"
PKG = "composio_src_under_test"


def _identity_decorator(*args, **kwargs):
    def wrap(fn):
        return fn

    return wrap


def _install_stubs():
    """Stub fastapi/pydantic/requests/dotenv and the sibling .db module so omi_api imports offline."""
    fastapi = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        get = post = put = delete = staticmethod(_identity_decorator)

    class _HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.APIRouter = _APIRouter
    fastapi.HTTPException = _HTTPException
    fastapi.Depends = lambda dep=None: dep
    fastapi.Request = object
    fastapi.status = types.SimpleNamespace(HTTP_200_OK=200)

    pydantic = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    pydantic.BaseModel = _BaseModel

    posts = []
    requests_mod = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

    def _post(url, headers=None, json=None, **kwargs):
        posts.append({"url": url, "headers": headers, "json": json})
        return _Response()

    requests_mod.post = _post
    requests_mod.exceptions = types.SimpleNamespace(RequestException=_RequestException)

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **kw: None

    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(SRC_DIR)]
    db = types.ModuleType(PKG + ".db")
    db.get_pending_memories = lambda *a, **kw: []
    db.update_memory_status = lambda *a, **kw: None
    db.get_all_memories = lambda *a, **kw: []

    for name, module in {
        "fastapi": fastapi,
        "pydantic": pydantic,
        "requests": requests_mod,
        "dotenv": dotenv,
        PKG: pkg,
        PKG + ".db": db,
    }.items():
        sys.modules[name] = module
    return posts


def _load_module():
    os.environ["OMI_APP_ID"] = "app123"
    os.environ["OMI_API_KEY"] = "secret-key"
    spec = importlib.util.spec_from_file_location(PKG + ".omi_api", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PKG
    sys.modules[PKG + ".omi_api"] = module
    spec.loader.exec_module(module)
    return module


def test_create_fact_posts_to_v2_user_memories_route(mod, posts):
    posts.clear()
    ok = mod.create_fact("user-42", "Prefers async updates over meetings", source="notion", source_spec="page")
    assert ok is True
    assert len(posts) == 1, posts
    assert posts[0]["url"] == "https://api.omi.me/v2/integrations/app123/user/memories?uid=user-42", posts[0]["url"]
    assert posts[0]["headers"]["Authorization"] == "Bearer secret-key", posts[0]["headers"]
    assert posts[0]["json"] == {
        "text": "Prefers async updates over meetings",
        "text_source": "notion",
        "text_source_spec": "page",
    }, posts[0]["json"]


def test_retired_facts_route_is_never_used(mod, posts):
    posts.clear()
    mod.create_fact("u", "some text")
    assert "/user/facts" not in posts[0]["url"], posts[0]["url"]
    assert "/user/memories?uid=u" in posts[0]["url"], posts[0]["url"]


def test_missing_credentials_raise_without_request(mod, posts):
    posts.clear()
    saved = mod.APP_ID
    mod.APP_ID = None
    try:
        try:
            mod.create_fact("u", "text")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError when OMI credentials are missing")
    finally:
        mod.APP_ID = saved
    assert posts == [], posts


def main():
    posts = _install_stubs()
    mod = _load_module()
    tests = [
        test_create_fact_posts_to_v2_user_memories_route,
        test_retired_facts_route_is_never_used,
        test_missing_credentials_raise_without_request,
    ]
    failures = 0
    for test in tests:
        try:
            test(mod, posts)
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
