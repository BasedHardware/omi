"""Hermetic regression for ms365 list_upcoming calendarView pagination (#13913).

Graph pages every collection: $top is a page size, not a result cap, and the
remainder is only reachable through @odata.nextLink. list_upcoming used to read
one page of 50 and silently drop every later event in the window.

Runs on a plain python3 + stdlib interpreter: third-party deps (fastapi,
httpx, msal, redis, itsdangerous) and the plugin's own config module are
stubbed in sys.modules before importing main.py; the real services/* code —
GraphClient.get_all, calendar.list_upcoming, tool_dispatch — is exercised.
"""
import asyncio
import json
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class _Framework:
    """FastAPI stand-in: decorators return the function unchanged."""

    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class _Response:
    def __init__(self, content=None, *args, **kwargs):
        self.content = content
        self.status_code = kwargs.get("status_code", 200)


class _URLSafeSerializer:
    def __init__(self, *args, **kwargs):
        pass

    def dumps(self, payload):
        return json.dumps(payload)

    def loads(self, payload):
        return json.loads(payload)


class FakeAsyncClient:
    """Replaces httpx.AsyncClient. Tests assign `responder` and read `calls`."""

    responder = None  # callable(method, url, params) -> FakeGraphResponse
    calls = []        # (method, url, params) per request

    def __init__(self, *args, **kwargs):
        pass

    async def request(self, method, url, headers=None, params=None, json=None):
        FakeAsyncClient.calls.append((method, url, params))
        return FakeAsyncClient.responder(method, url, params)

    async def get(self, url, headers=None):
        FakeAsyncClient.calls.append(("GET", url, None))
        return FakeAsyncClient.responder("GET", url, None)

    async def aclose(self):
        return None


class FakeGraphResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


def _module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


_settings = types.SimpleNamespace(
    microsoft_client_id="test-client",
    microsoft_client_secret="test-secret",
    microsoft_tenant_id="common",
    microsoft_redirect_uri="http://localhost:8080/auth/microsoft/callback",
    app_base_url="http://localhost:8080",
    session_secret="test-session-secret",
    redis_url=None,
    log_level="INFO",
    authority="https://login.microsoftonline.com/common",
)

_redis_asyncio = _module("redis.asyncio", Redis=_Framework, from_url=lambda *a, **k: _Framework())

_STUBS = {
    "httpx": _module("httpx", AsyncClient=FakeAsyncClient),
    "fastapi": _module(
        "fastapi",
        FastAPI=_Framework,
        HTTPException=_HTTPException,
        Query=lambda *a, **k: k.get("default"),
        Request=_Framework,
    ),
    "fastapi.responses": _module(
        "fastapi.responses",
        HTMLResponse=_Response,
        JSONResponse=_Response,
        RedirectResponse=_Response,
    ),
    "itsdangerous": _module(
        "itsdangerous", BadSignature=Exception, URLSafeSerializer=_URLSafeSerializer
    ),
    "msal": _module(
        "msal",
        ConfidentialClientApplication=_Framework,
        SerializableTokenCache=_Framework,
    ),
    "redis": _module("redis", asyncio=_redis_asyncio),
    "redis.asyncio": _redis_asyncio,
    "config": _module(
        "config", get_settings=lambda: _settings, GRAPH_SCOPES=["User.Read"]
    ),
}

with patch.dict(sys.modules, _STUBS):
    import main  # noqa: E402 — plugin entrypoint under stubbed deps
    # patch.dict restores sys.modules on exit; keep direct module refs so the
    # tests can patch their seams (the stubs stay bound inside the modules).
    graph_client = sys.modules["services.graph_client"]
    auth_svc = sys.modules["services.auth"]

cal = main.cal


def _event(n):
    return {
        "id": f"ev-{n}",
        "subject": f"Event {n}",
        "start": {"dateTime": f"2026-01-01T{n % 24:02d}:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": f"2026-01-01T{n % 24:02d}:30:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": "Room"},
        "organizer": {"emailAddress": {"address": "org@example.com"}},
        "isOnlineMeeting": False,
        "webLink": f"https://outlook.example.com/ev-{n}",
    }


def _page(start, count, next_url=None):
    payload = {"value": [_event(n) for n in range(start, start + count)]}
    if next_url:
        payload["@odata.nextLink"] = next_url
    return FakeGraphResponse(payload)


class _Responder:
    """Maps request URL -> FakeGraphResponse; records nothing extra itself."""

    def __init__(self, pages):
        self.pages = pages

    def __call__(self, method, url, params):
        assert method == "GET", f"unexpected method {method}"
        if url not in self.pages:
            raise AssertionError(f"unexpected URL fetched: {url}")
        return self.pages[url]


class _Ms365TestCase(unittest.TestCase):
    def setUp(self):
        FakeAsyncClient.calls = []
        FakeAsyncClient.responder = None
        patches = [
            # graph_client._request resolves the token through the name it
            # imported; tool_dispatch's _auth_guard goes through services.auth.
            patch.object(graph_client, "get_access_token", AsyncMock(return_value="tok")),
            patch.object(auth_svc, "get_access_token", AsyncMock(return_value="tok")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def list_upcoming(self, **kwargs):
        return asyncio.run(cal.list_upcoming("user-1", **kwargs))


class ListUpcomingPaginationTests(_Ms365TestCase):
    def test_single_page_returns_all_events(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        FakeAsyncClient.responder = _Responder({url: _page(1, 3)})

        events = self.list_upcoming(days=1)

        self.assertEqual([e["id"] for e in events], ["ev-1", "ev-2", "ev-3"])
        self.assertEqual(len(FakeAsyncClient.calls), 1)
        method, req_url, params = FakeAsyncClient.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(req_url, url)
        self.assertEqual(params["$top"], cal.CALENDAR_PAGE_SIZE)
        self.assertEqual(params["$orderby"], "start/dateTime")
        start = datetime.fromisoformat(params["startDateTime"])
        end = datetime.fromisoformat(params["endDateTime"])
        self.assertEqual((end - start).days, 1)

    def test_follows_nextlink_until_collection_ends(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        next2 = f"{url}?$skiptoken=page2"
        next3 = f"{url}?$skiptoken=page3"
        FakeAsyncClient.responder = _Responder(
            {
                url: _page(1, 50, next_url=next2),
                next2: _page(51, 50, next_url=next3),
                next3: _page(101, 20),
            }
        )

        events = self.list_upcoming(days=7)

        # The pre-fix code returned only page 1 — 50 of 120 events.
        self.assertEqual(len(events), 120)
        self.assertEqual(events[0]["id"], "ev-1")
        self.assertEqual(events[-1]["id"], "ev-120")
        self.assertEqual([c[1] for c in FakeAsyncClient.calls], [url, next2, next3])
        # Query options ride the first request only — a nextLink already
        # carries them and repeating them is a Graph error.
        self.assertIsNotNone(FakeAsyncClient.calls[0][2])
        self.assertIsNone(FakeAsyncClient.calls[1][2])
        self.assertIsNone(FakeAsyncClient.calls[2][2])

    def test_limit_stops_paging_and_truncates(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        next2 = f"{url}?$skiptoken=page2"
        next3 = f"{url}?$skiptoken=page3"
        FakeAsyncClient.responder = _Responder(
            {
                url: _page(1, 50, next_url=next2),
                next2: _page(51, 50, next_url=next3),
                next3: _page(101, 50),
            }
        )

        events = self.list_upcoming(days=1, limit=60)

        self.assertEqual(len(events), 60)
        self.assertEqual(len(FakeAsyncClient.calls), 2)  # page 3 never fetched

    def test_max_pages_ceiling_stops_runaway_nextlinks(self):
        def responder(method, url, params):
            nxt = f"{GRAPH_BASE}/me/calendarView?$skip={len(FakeAsyncClient.calls)}"
            return _page(len(FakeAsyncClient.calls), 10, next_url=nxt)

        FakeAsyncClient.responder = responder

        async def run():
            async with graph_client.GraphClient("user-1") as g:
                return await g.get_all("/me/calendarView", params={"$top": 10})

        with self.assertLogs(graph_client.__name__, level="WARNING"):
            items = asyncio.run(run())

        self.assertEqual(len(FakeAsyncClient.calls), graph_client.MAX_PAGES)
        self.assertEqual(len(items), graph_client.MAX_PAGES * 10)

    def test_repeat_nextlink_does_not_loop(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        next2 = f"{url}?$skiptoken=page2"
        FakeAsyncClient.responder = _Responder(
            {
                url: _page(1, 50, next_url=next2),
                next2: _page(51, 50, next_url=next2),  # self-referencing link
            }
        )

        events = self.list_upcoming(days=1)

        self.assertEqual(len(events), 100)
        self.assertEqual(len(FakeAsyncClient.calls), 2)

    def test_cycle_back_to_first_url_stops(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        next2 = f"{url}?$skiptoken=page2"
        FakeAsyncClient.responder = _Responder(
            {
                url: _page(1, 50, next_url=next2),
                next2: _page(51, 50, next_url=url),  # cycle to page 1
            }
        )

        events = self.list_upcoming(days=1)

        self.assertEqual(len(events), 100)
        self.assertEqual(len(FakeAsyncClient.calls), 2)


class NullOptionalParamTests(_Ms365TestCase):
    def test_null_days_and_limit_fall_back_to_defaults(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        FakeAsyncClient.responder = _Responder({url: _page(1, 2)})

        events = self.list_upcoming(days=None, limit=None)

        self.assertEqual(len(events), 2)
        params = FakeAsyncClient.calls[0][2]
        start = datetime.fromisoformat(params["startDateTime"])
        end = datetime.fromisoformat(params["endDateTime"])
        self.assertEqual((end - start).days, 1)  # default days=1 window

    def test_blank_and_string_params_coerce(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        FakeAsyncClient.responder = _Responder({url: _page(1, 30)})

        events = self.list_upcoming(days="", limit="30")

        self.assertEqual(len(events), 30)

    def test_dispatch_with_explicit_null_args_does_not_400(self):
        """OMI tool calls carry JSON; a model emitting "days": null must get
        the default window, not a TypeError-turned-HTTP-400."""
        url = f"{GRAPH_BASE}/me/calendarView"
        FakeAsyncClient.responder = _Responder({url: _page(1, 4)})
        request = Mock(
            json=AsyncMock(return_value={"uid": "user-1", "args": {"days": None, "limit": None}}),
            query_params={},
        )

        result = asyncio.run(main.tool_dispatch("list_upcoming_events", request))

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)

    def test_limit_is_capped_at_max_upcoming_events(self):
        url = f"{GRAPH_BASE}/me/calendarView"
        next2 = f"{url}?$skiptoken=page2"
        FakeAsyncClient.responder = _Responder(
            {
                url: _page(1, 50, next_url=next2),
                next2: _page(51, 50),
            }
        )

        # limit=5000 must clamp to MAX_UPCOMING_EVENTS (500), and the walk
        # still stops when Graph runs out of pages.
        events = self.list_upcoming(days=1, limit=5000)

        self.assertEqual(len(events), 100)
        self.assertEqual(len(FakeAsyncClient.calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
