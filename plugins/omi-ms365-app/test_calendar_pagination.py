"""Hermetic regression tests for calendarView pagination in the MS365 plugin.

Standard library only: httpx and services.auth are replaced with minimal
stubs before importing the modules under test, so the suite runs without
site-packages (the manifest lane runs plain python3).

Covers the truncation in services.calendar.list_upcoming: it issued a single
GET /me/calendarView with $top=50 and read only that page's "value". Graph
pages every collection and returns the remainder through @odata.nextLink, so
a window holding more than 50 events silently lost every event after the
50th — and because the view is ordered by start, those were the later ones.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def aclose(self):
            pass

    httpx.AsyncClient = _AsyncClient
    sys.modules.setdefault("httpx", httpx)

    auth = types.ModuleType("services.auth")

    async def get_access_token(user_id):
        return "token"

    auth.get_access_token = get_access_token
    sys.modules.setdefault("services.auth", auth)


_install_module_stubs()

from services import calendar  # noqa: E402
from services.graph_client import GraphClient, MAX_PAGES  # noqa: E402


def _page(ids, next_link=None):
    body = {"value": [{"id": i, "subject": f"event {i}", "start": {"dateTime": f"2026-01-{i:02d}"}} for i in ids]}
    if next_link:
        body["@odata.nextLink"] = next_link
    return body


class _FakeGraph:
    """Stands in for GraphClient: serves scripted pages and records each GET."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, url, params=None):
        self.calls.append((url, params))
        return self.pages[url]

    # Reuse the real pagination logic under test.
    get_all = GraphClient.get_all


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class GetAllTests(unittest.TestCase):
    def test_follows_next_link_and_sends_params_once(self):
        g = _FakeGraph({
            "/me/calendarView": _page([1, 2], "https://graph.microsoft.com/v1.0/me/calendarView?$skip=2"),
            "https://graph.microsoft.com/v1.0/me/calendarView?$skip=2": _page([3], "https://graph.microsoft.com/v1.0/me/calendarView?$skip=3"),
            "https://graph.microsoft.com/v1.0/me/calendarView?$skip=3": _page([4]),
        })
        items = _run(g.get_all("/me/calendarView", params={"$top": 2}))
        self.assertEqual([i["id"] for i in items], [1, 2, 3, 4])
        # The nextLink already carries the query options; re-sending them is a Graph error.
        self.assertEqual(g.calls[0], ("/me/calendarView", {"$top": 2}))
        self.assertEqual([p for _, p in g.calls[1:]], [None, None])
        self.assertEqual(g.calls[1][0], "https://graph.microsoft.com/v1.0/me/calendarView?$skip=2")

    def test_max_items_stops_fetching(self):
        g = _FakeGraph({
            "/x": _page([1, 2], "https://g/x?2"),
            "https://g/x?2": _page([3, 4], "https://g/x?3"),
            "https://g/x?3": _page([5]),
        })
        items = _run(g.get_all("/x", max_items=3))
        self.assertEqual([i["id"] for i in items], [1, 2, 3])
        self.assertEqual(len(g.calls), 2, "must not request pages past the cap")

    def test_single_page_without_next_link(self):
        g = _FakeGraph({"/x": _page([7])})
        self.assertEqual([i["id"] for i in _run(g.get_all("/x"))], [7])
        self.assertEqual(len(g.calls), 1)

    def test_empty_or_missing_value_is_tolerated(self):
        g = _FakeGraph({"/x": {"value": None, "@odata.nextLink": "https://g/x?2"}, "https://g/x?2": {}})
        self.assertEqual(_run(g.get_all("/x")), [])

    def test_repeating_next_link_does_not_loop_forever(self):
        g = _FakeGraph({"/x": _page([1], "https://g/x?same"), "https://g/x?same": _page([2], "https://g/x?same")})
        items = _run(g.get_all("/x"))
        self.assertEqual([i["id"] for i in items], [1, 2])
        self.assertEqual(len(g.calls), 2)

    def test_page_ceiling(self):
        pages = {"/x": _page([0], "https://g/x?1")}
        for n in range(1, MAX_PAGES + 5):
            pages[f"https://g/x?{n}"] = _page([n], f"https://g/x?{n + 1}")
        g = _FakeGraph(pages)
        items = _run(g.get_all("/x"))
        self.assertEqual(len(g.calls), MAX_PAGES)
        self.assertEqual(len(items), MAX_PAGES)


class ListUpcomingTests(unittest.TestCase):
    def _events(self, n):
        return [{"id": f"e{i}", "subject": f"event {i}", "start": {"dateTime": f"2026-02-{(i % 28) + 1:02d}T09:00:00"}} for i in range(n)]

    def test_returns_events_past_the_first_page(self):
        events = self._events(120)
        first = "https://graph.microsoft.com/v1.0/me/calendarView?$skiptoken=a"
        second = "https://graph.microsoft.com/v1.0/me/calendarView?$skiptoken=b"
        g = _FakeGraph({
            "/me/calendarView": {"value": events[:50], "@odata.nextLink": first},
            first: {"value": events[50:100], "@odata.nextLink": second},
            second: {"value": events[100:]},
        })
        with mock.patch.object(calendar, "GraphClient", lambda uid: g):
            out = _run(calendar.list_upcoming("uid", days=30))
        self.assertEqual(len(out), 120, "every event in the window, not just the first page")
        self.assertEqual(out[0]["subject"], "event 0")
        self.assertEqual(out[-1]["subject"], "event 119")
        self.assertEqual(out[0]["id"], "e0")
        # First request carries the window and page size; nextLinks are followed as given.
        url, params = g.calls[0]
        self.assertEqual(url, "/me/calendarView")
        self.assertEqual(params["$top"], calendar.CALENDAR_PAGE_SIZE)
        self.assertEqual(params["$orderby"], "start/dateTime")
        self.assertIn("startDateTime", params)
        self.assertIn("endDateTime", params)
        self.assertEqual([c[0] for c in g.calls[1:]], [first, second])

    def test_limit_caps_results_and_page_size(self):
        events = self._events(60)
        nxt = "https://graph.microsoft.com/v1.0/me/calendarView?$skiptoken=a"
        g = _FakeGraph({
            "/me/calendarView": {"value": events[:10], "@odata.nextLink": nxt},
            nxt: {"value": events[10:60]},
        })
        with mock.patch.object(calendar, "GraphClient", lambda uid: g):
            out = _run(calendar.list_upcoming("uid", days=7, limit=10))
        self.assertEqual(len(out), 10)
        self.assertEqual(g.calls[0][1]["$top"], 10, "no point asking for a bigger page than the cap")
        self.assertEqual(len(g.calls), 1)

    def test_limit_is_clamped(self):
        g = _FakeGraph({"/me/calendarView": {"value": []}})
        with mock.patch.object(calendar, "GraphClient", lambda uid: g):
            _run(calendar.list_upcoming("uid", limit=10_000))
            self.assertEqual(g.calls[0][1]["$top"], calendar.CALENDAR_PAGE_SIZE)
            _run(calendar.list_upcoming("uid", limit=0))
            self.assertEqual(g.calls[1][1]["$top"], 1)

    def test_single_page_still_works(self):
        g = _FakeGraph({"/me/calendarView": {"value": self._events(3)}})
        with mock.patch.object(calendar, "GraphClient", lambda uid: g):
            out = _run(calendar.list_upcoming("uid"))
        self.assertEqual([e["subject"] for e in out], ["event 0", "event 1", "event 2"])
        self.assertEqual(len(g.calls), 1)


if __name__ == "__main__":
    unittest.main()
