"""Hermetic regression tests for plugins/iq_rating/main.py.

Standard library only: requests, fastapi, and pydantic-free surfaces are
stubbed before importing the module under test; IQ_RATING_DB_PATH points
at a temp directory and time.sleep is patched out, so no network, no
sleeps, and no repo-tree side effects.

Covers the unbounded 429 retry loop: fetch_all_memories and
fetch_all_conversations retried `continue` forever on persistent 429s,
pinning the background thread that load_and_process_user_data spawns per
request. They now give up after RATE_LIMIT_MAX_RETRIES.
"""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ["IQ_RATING_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="iq-rating-test-"), "test.db"
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self):
        return self._payload


def _install_module_stubs():
    requests = types.ModuleType("requests")
    requests.get = requests.post = lambda *a, **k: _Resp(500)
    sys.modules["requests"] = requests

    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, *args, **kwargs):
            return lambda f: f

        def get(self, *args, **kwargs):
            return lambda f: f

        def on_event(self, *args, **kwargs):
            return lambda f: f

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def include_router(self, *args, **kwargs):
            pass

    fastapi.APIRouter = APIRouter
    fastapi.FastAPI = FastAPI
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class _R:
        def __init__(self, *args, **kwargs):
            pass

    responses.HTMLResponse = _R
    responses.JSONResponse = _R
    sys.modules["fastapi.responses"] = responses


_install_module_stubs()
import main  # noqa: E402


class RateLimitRetryTests(unittest.TestCase):
    def setUp(self):
        # No real sleeping: hermetic and fast.
        self._sleep = mock.patch.object(main.time, "sleep", lambda s: None)
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    def test_memories_gives_up_after_bounded_429s(self):
        calls = []

        def always_429(*args, **kwargs):
            calls.append(args)
            return _Resp(429)

        with mock.patch.object(main.requests, "get", always_429):
            self.assertEqual(main.fetch_all_memories("u1"), [])
        self.assertEqual(len(calls), 1 + main.RATE_LIMIT_MAX_RETRIES)

    def test_conversations_gives_up_after_bounded_429s(self):
        calls = []

        def always_429(*args, **kwargs):
            calls.append(args)
            return _Resp(429)

        with mock.patch.object(main.requests, "get", always_429):
            self.assertEqual(main.fetch_all_conversations("u1"), [])
        self.assertEqual(len(calls), 1 + main.RATE_LIMIT_MAX_RETRIES)

    def test_memories_recovers_when_429_clears(self):
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) < 3:
                return _Resp(429)
            return _Resp(200, [{"id": "m1"}])

        with mock.patch.object(main.requests, "get", flaky):
            self.assertEqual(main.fetch_all_memories("u1"), [{"id": "m1"}])
        self.assertEqual(len(calls), 3)

    def test_memories_paginates_until_short_page(self):
        pages = []

        def paged(*args, **kwargs):
            offset = kwargs["params"]["offset"]
            pages.append(offset)
            if offset == 0:
                return _Resp(200, [{"id": i} for i in range(100)])
            return _Resp(200, [{"id": 100}])

        with mock.patch.object(main.requests, "get", paged):
            result = main.fetch_all_memories("u1")
        self.assertEqual(len(result), 101)
        self.assertEqual(pages, [0, 100])


if __name__ == "__main__":
    unittest.main()
