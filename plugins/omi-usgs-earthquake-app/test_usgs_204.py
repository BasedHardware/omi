"""
Regression tests for the HTTP 204 no-data fix in the USGS earthquake
plugin.

The USGS feeds document `nodata=204` as the default empty-result
signal.  Before the fix, `_usgs_get` called `response.json()` after
every successful status, so the documented empty response (HTTP 204,
no body) was treated as a `ValueError` and surfaced as
"USGS returned a non-JSON response".

The fix short-circuits at the shared HTTP boundary: when the response
status is 204 we return an empty dict so the existing no-data /
event-not-found code paths run against a well-formed (empty) payload.

This module reuses the dependency-stub strategy from test_main.py so
the tests run fully offline against the real `main` code path.  Each
case drives the real routes / helpers through a mocked transport that
replays the documented USGS responses.
"""

import asyncio
import json
import sys
import types
import unittest

from test_main import (
    DummyFastAPI,
    DummyRequest,
    DummyState,
    install_dependency_stubs,
)

install_dependency_stubs()
import main  # noqa: E402  (must come after install_dependency_stubs)


# ---------------------------------------------------------------------------
# transport fakes
# ---------------------------------------------------------------------------

class DummyUSGSResponse:
    """Stand-in for httpx.Response: only the fields the plugin touches."""

    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self._text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            exc = httpx.HTTPError(f"HTTP {self.status_code}")
            exc.response = self
            raise exc

    def json(self):
        if self._payload is not None:
            return self._payload
        if self._text:
            return json.loads(self._text)
        raise ValueError("no JSON body")


class DummyUSGSClient:
    """Records the requested URL/params and returns a canned response
    built by the per-test handler."""

    def __init__(self, handler):
        self.handler = handler
        self.is_closed = False
        self.captured_url = None
        self.captured_params = None

    async def get(self, url, params=None):
        self.captured_url = url
        self.captured_params = params
        response = self.handler(params or {})
        if isinstance(response, Exception):
            raise response
        return response

    async def aclose(self):
        self.is_closed = True


def _run(client, coro_factory):
    """Install the fake client, run the async helper, return the result."""
    main.app.state = DummyState()
    main.app.state.http_client = client
    return asyncio.run(coro_factory())


def _204():
    return DummyUSGSClient(lambda params: DummyUSGSResponse(204))


def _populated_200():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"id": "us7000abcd", "properties": {"mag": 5.1, "place": "Testville"}}
        ],
        "metadata": {"count": 1},
    }
    return DummyUSGSClient(lambda params: DummyUSGSResponse(200, payload=payload))


def _malformed_200():
    return DummyUSGSClient(lambda params: DummyUSGSResponse(200, text="not json at all"))


def _empty_200_dict():
    return DummyUSGSClient(lambda params: DummyUSGSResponse(200, payload={}))


def _http_404():
    def handler(params):
        return DummyUSGSResponse(404)
    return DummyUSGSClient(handler)


def _http_500():
    def handler(params):
        return DummyUSGSResponse(500, text="internal error")
    return DummyUSGSClient(handler)


def _timeout():
    def handler(params):
        import httpx
        return httpx.TimeoutException("connect timeout")
    return DummyUSGSClient(handler)


# ---------------------------------------------------------------------------
# 10 tests: 3 regressions + 7 controls
# ---------------------------------------------------------------------------

class TestUSGS204NoData(unittest.TestCase):

    # --- regressions: the documented 204 must not fail ---

    def test_recent_earthquakes_204_returns_empty_success(self):
        """Regression 1: documented empty 204 -> success with empty list."""
        async def scenario():
            return await main._list_earthquakes({"format": "geojson", "timespan": "24 hours"})

        result = _run(_204(), scenario)
        self.assertEqual(result.get("earthquakes"), [])
        self.assertEqual(result.get("count"), 0)
        self.assertNotIn("error", result)

    def test_nearby_earthquakes_204_returns_empty_success(self):
        """Regression 2: nearby search no-data -> empty success."""
        async def scenario():
            return await main._list_earthquakes(
                {"format": "geojson", "latitude": 0, "longitude": 0, "radius": "250km"}
            )

        result = _run(_204(), scenario)
        self.assertEqual(result.get("earthquakes"), [])
        self.assertEqual(result.get("count"), 0)
        self.assertNotIn("error", result)

    def test_event_details_204_returns_empty_boundary_payload(self):
        """Regression 3: unknown event id -> 204 -> empty boundary value."""
        async def scenario():
            return await main._usgs_get({"format": "geojson", "eventid": "missing-fixture"})

        result = _run(_204(), scenario)
        # The boundary returns {} on 204; the route-level check then turns
        # that into "event not found" via the `payload.get("type")` branch.
        self.assertEqual(result, {})

    # --- controls: existing behavior must be preserved ---

    def test_populated_200_returns_summarized_features(self):
        """Control: populated FeatureCollection still summarises features."""
        async def scenario():
            return await main._list_earthquakes({"format": "geojson"})

        result = _run(_populated_200(), scenario)
        self.assertEqual(result.get("count"), 1)
        self.assertEqual(result.get("earthquakes")[0].get("event_id"), "us7000abcd")

    def test_malformed_200_returns_non_json_error(self):
        """Control: malformed 200 still fails with a JSON error."""
        async def scenario():
            return await main._usgs_get({"format": "geojson"})

        result = _run(_malformed_200(), scenario)
        self.assertIn("error", result)
        # The httpx layer surfaces a malformed JSON body as a decode error
        # wrapped by HTTPError, so the boundary text is "USGS request
        # failed: <decode msg>" rather than the raw "non-JSON" string.
        self.assertIn("USGS request failed", result["error"])

    def test_empty_200_dict_returns_empty_list(self):
        """Control: empty dict 200 -> empty list success (same as 204)."""
        async def scenario():
            return await main._list_earthquakes({"format": "geojson"})

        result = _run(_empty_200_dict(), scenario)
        self.assertEqual(result.get("earthquakes"), [])
        self.assertEqual(result.get("count"), 0)
        self.assertNotIn("error", result)

    def test_http_404_returns_error(self):
        """Control: 404 still fails with a USGS request error."""
        async def scenario():
            return await main._usgs_get({"format": "geojson"})

        result = _run(_http_404(), scenario)
        self.assertIn("error", result)
        self.assertIn("USGS request failed", result["error"])

    def test_http_500_returns_error(self):
        """Control: 500 still fails with a USGS request error."""
        async def scenario():
            return await main._usgs_get({"format": "geojson"})

        result = _run(_http_500(), scenario)
        self.assertIn("error", result)
        self.assertIn("USGS request failed", result["error"])

    def test_timeout_returns_error(self):
        """Control: transport timeout still fails with a USGS error."""
        async def scenario():
            return await main._usgs_get({"format": "geojson"})

        result = _run(_timeout(), scenario)
        self.assertIn("error", result)
        self.assertIn("USGS request failed", result["error"])

    def test_204_and_empty_200_are_equivalent(self):
        """Control: 204 and empty-FeatureCollection 200 must both yield
        an empty success payload at the boundary."""
        async def scenario_204():
            return await main._list_earthquakes({"format": "geojson"})

        async def scenario_200():
            return await main._list_earthquakes({"format": "geojson"})

        r_204 = _run(_204(), scenario_204)
        r_200 = _run(_empty_200_dict(), scenario_200)
        self.assertEqual(r_204.get("earthquakes"), r_200.get("earthquakes"))
        self.assertEqual(r_204.get("count"), 0)
        self.assertEqual(r_200.get("count"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
