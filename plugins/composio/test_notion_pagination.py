"""Hermetic regression tests for plugins/composio/src/notion.py pagination.

Standard library only: requests, fastapi, pydantic, and the src.db /
src.omi_api siblings are replaced with minimal stubs before importing the
module under test so the suite runs without site-packages (the manifest
lane runs plain python3). Stubs and the imported `src.notion` module are
scoped to a context manager so pytest collection cannot leak fakes.
"""

import asyncio
import os
import sys
import types
import unittest
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "requests",
    "requests.exceptions",
    "requests.utils",
    "fastapi",
    "fastapi.responses",
    "fastapi.templating",
    "pydantic",
    "src.db",
    "src.omi_api",
)


def _install_module_stubs():
    requests = types.ModuleType("requests")

    class _RequestException(Exception):
        pass

    exceptions = types.ModuleType("requests.exceptions")
    exceptions.RequestException = _RequestException
    exceptions.HTTPError = type("HTTPError", (_RequestException,), {})
    requests.exceptions = exceptions
    requests.post = lambda *a, **k: None
    requests.get = lambda *a, **k: None
    utils = types.ModuleType("requests.utils")
    utils.quote = lambda s, safe="": s
    requests.utils = utils
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = exceptions
    sys.modules["requests.utils"] = utils

    fastapi = types.ModuleType("fastapi")

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class HTTPException(Exception):
        pass

    class Request:
        pass

    def Form(default=None, **kwargs):
        return default

    def Depends(dependency=None, **kwargs):
        return dependency

    class BackgroundTasks:
        pass

    status = types.SimpleNamespace(HTTP_200_OK=200)

    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Request = Request
    fastapi.Form = Form
    fastapi.Depends = Depends
    fastapi.BackgroundTasks = BackgroundTasks
    fastapi.status = status
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _Resp:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _Resp
    responses.RedirectResponse = _Resp
    sys.modules["fastapi.responses"] = responses

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = lambda *a, **k: types.SimpleNamespace(TemplateResponse=lambda *a, **k: None)
    sys.modules["fastapi.templating"] = templating

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *a, **k: (k["default_factory"]() if "default_factory" in k else k.get("default"))
    sys.modules["pydantic"] = pydantic

    db = types.ModuleType("src.db")
    db.store_notion_credentials = lambda *a, **k: None
    db.get_notion_credentials = lambda *a, **k: None
    db.store_memory = lambda *a, **k: None
    sys.modules["src.db"] = db

    omi_api = types.ModuleType("src.omi_api")

    async def store_fact(*a, **k):
        return {"success": True}

    omi_api.store_fact = store_fact
    sys.modules["src.omi_api"] = omi_api


@contextmanager
def _isolated_notion_import():
    saved = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
    saved_notion = sys.modules.get("src.notion")
    _install_module_stubs()
    try:
        import src.notion as notion_mod  # noqa: E402

        yield notion_mod
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        if saved_notion is None:
            sys.modules.pop("src.notion", None)
        else:
            sys.modules["src.notion"] = saved_notion


_PAGE = {"id": "page-1", "properties": {"title": {"title": [{"plain_text": "Doc"}]}}}
_BLOCK = {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "hello world of testing"}]}}


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _run(notion, children_pages, captured_facts=None):
    """Run extract_all_pages with canned children pages; count GET calls.

    children_pages: list of payloads returned in order by requests.get.
    """
    get_calls = []

    def fake_get(url, params=None, headers=None):
        get_calls.append(params)
        if len(get_calls) > len(children_pages):
            raise AssertionError(f"unbounded pagination: {len(get_calls)} children requests")
        return _Resp(children_pages[len(get_calls) - 1])

    def fake_post(url, json=None, headers=None):
        return _Resp({"results": [_PAGE]})

    async def capture_fact(uid, fact_text, **kwargs):
        if captured_facts is not None:
            captured_facts.append(fact_text)
        return {"success": True}

    with mock.patch.object(notion.requests, "post", side_effect=fake_post), mock.patch.object(
        notion.requests, "get", side_effect=fake_get
    ), mock.patch.object(notion, "store_fact", side_effect=capture_fact), mock.patch.object(
        notion.asyncio, "sleep", new=mock.AsyncMock()
    ):
        return asyncio.run(notion.extract_all_pages("tok", "u1")), get_calls


class NotionPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cm = _isolated_notion_import()
        cls.notion = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def test_single_page_no_more(self):
        facts, calls = _run(self.notion, [{"results": [_BLOCK], "has_more": False, "next_cursor": None}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(facts, 1)

    def test_two_pages_then_done(self):
        facts, calls = _run(
            self.notion,
            [
                {"results": [_BLOCK], "has_more": True, "next_cursor": "c2"},
                {"results": [_BLOCK], "has_more": False, "next_cursor": None},
            ],
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].get("start_cursor"), "c2")
        # Both fetched blocks merge into a single stored chunk.
        self.assertEqual(facts, 1)

    def test_has_more_without_cursor_stops(self):
        # Old code re-requested page one forever.
        facts, calls = _run(self.notion, [{"results": [_BLOCK], "has_more": True, "next_cursor": None}])
        self.assertEqual(len(calls), 1)
        self.assertEqual(facts, 1)

    def test_repeating_cursor_stops_without_duplicating_blocks(self):
        captured = []
        facts, calls = _run(
            self.notion,
            [
                {"results": [_BLOCK], "has_more": True, "next_cursor": "c2"},
                {"results": [_BLOCK], "has_more": True, "next_cursor": "c2"},
            ],
            captured_facts=captured,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(facts, 1)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].count("hello world of testing"), 1)


class NotionImportIsolationTests(unittest.TestCase):
    def test_src_notion_is_dropped_when_the_context_exits(self):
        self.assertNotIn("src.notion", sys.modules)
        with _isolated_notion_import() as mod:
            self.assertIsNotNone(mod)
            self.assertIn("src.notion", sys.modules)
        self.assertNotIn("src.notion", sys.modules)


if __name__ == "__main__":
    unittest.main()
