"""Hermetic regression tests for plugins/iq_rating/main.py.

Stubs are scoped with patch.dict; the module is loaded under a unique name
so a shared test runner cannot bind a leftover `main` or leak fastapi/requests.
IQ_RATING_DB_PATH lives in a TemporaryDirectory that is removed on exit.
time.sleep is patched, so no network and no real waits.

Covers the unbounded 429 retry loop: fetch_all_memories and
fetch_all_conversations retried `continue` forever on persistent 429s.
They now raise RateLimitExhausted after RATE_LIMIT_MAX_RETRIES consecutive
failures, and load_and_process_user_data does not persist a partial fetch.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self):
        return self._payload


def _module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _APIRouter:
    def __init__(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        return lambda f: f

    def get(self, *args, **kwargs):
        return lambda f: f

    def on_event(self, *args, **kwargs):
        return lambda f: f


class _FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def include_router(self, *args, **kwargs):
        pass


class _R:
    def __init__(self, *args, **kwargs):
        pass


_TMPDIR = tempfile.TemporaryDirectory(prefix="iq-rating-test-")
atexit.register(_TMPDIR.cleanup)
os.environ["IQ_RATING_DB_PATH"] = os.path.join(_TMPDIR.name, "test.db")

_stubs = {
    "requests": _module("requests", get=lambda *a, **k: _Resp(500), post=lambda *a, **k: _Resp(500)),
    "fastapi": _module(
        "fastapi",
        APIRouter=_APIRouter,
        FastAPI=_FastAPI,
        HTTPException=_HTTPException,
        Query=lambda default=None, **kwargs: default,
    ),
    "fastapi.responses": _module("fastapi.responses", HTMLResponse=_R, JSONResponse=_R),
}

_spec = importlib.util.spec_from_file_location(
    "iq_rating_under_test", Path(__file__).with_name("main.py")
)
main = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, _stubs):
    _spec.loader.exec_module(main)


class RateLimitRetryTests(unittest.TestCase):
    def setUp(self):
        self._sleep = mock.patch.object(main.time, "sleep", lambda s: None)
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    def test_memories_gives_up_after_bounded_429s(self):
        calls = []

        def always_429(*args, **kwargs):
            calls.append(args)
            return _Resp(429)

        with mock.patch.object(main.requests, "get", always_429):
            with self.assertRaises(main.RateLimitExhausted):
                main.fetch_all_memories("u1")
        self.assertEqual(len(calls), 1 + main.RATE_LIMIT_MAX_RETRIES)

    def test_conversations_gives_up_after_bounded_429s(self):
        calls = []

        def always_429(*args, **kwargs):
            calls.append(args)
            return _Resp(429)

        with mock.patch.object(main.requests, "get", always_429):
            with self.assertRaises(main.RateLimitExhausted):
                main.fetch_all_conversations("u1")
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

    def test_memories_does_not_return_partial_page_on_exhaustion(self):
        calls = []

        def first_page_then_429(*args, **kwargs):
            calls.append(kwargs["params"]["offset"])
            if kwargs["params"]["offset"] == 0 and calls.count(0) == 1:
                return _Resp(200, [{"id": i} for i in range(100)])
            return _Resp(429)

        with mock.patch.object(main.requests, "get", first_page_then_429):
            with self.assertRaises(main.RateLimitExhausted):
                main.fetch_all_memories("u1")

    def test_memories_resets_retry_budget_after_successful_page(self):
        calls = []

        def page_then_intermittent_429(*args, **kwargs):
            offset = kwargs["params"]["offset"]
            calls.append(offset)
            if offset == 0:
                return _Resp(200, [{"id": i} for i in range(100)])
            # Three consecutive 429s on page 2, then a short page.
            page2_attempts = calls.count(100)
            if page2_attempts <= 3:
                return _Resp(429)
            return _Resp(200, [{"id": 100}])

        with mock.patch.object(main.requests, "get", page_then_intermittent_429):
            result = main.fetch_all_memories("u1")
        self.assertEqual(len(result), 101)

    def test_load_and_process_does_not_persist_on_exhaustion(self):
        uid = "no-persist-u"

        def always_429(*args, **kwargs):
            return _Resp(429)

        with mock.patch.object(main.requests, "get", always_429):
            self.assertEqual(main.load_and_process_user_data(uid), [])
        self.assertFalse(main.has_user_data(uid))

    def test_load_and_process_does_not_persist_partial_pages(self):
        uid = "partial-u"
        calls = []

        def first_page_then_429(*args, **kwargs):
            calls.append(kwargs["params"]["offset"])
            if kwargs["params"]["offset"] == 0 and calls.count(0) == 1:
                return _Resp(200, [{"id": i} for i in range(100)])
            return _Resp(429)

        with mock.patch.object(main.requests, "get", first_page_then_429):
            self.assertEqual(main.load_and_process_user_data(uid), [])
        self.assertFalse(main.has_user_data(uid))


if __name__ == "__main__":
    unittest.main()
