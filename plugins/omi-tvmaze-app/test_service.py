"""Hermetic behavior tests against the real tool handlers and HTTP boundary."""

import io
import json
import unittest
from http.client import HTTPResponse
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import service


def show(show_id=1, **overrides):
    value = {
        "id": show_id,
        "name": "The Office",
        "premiered": "2005-03-24",
        "status": "Ended",
        "network": {"name": "NBC", "country": {"name": "United States"}},
    }
    return value | overrides


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class TVMazeToolsTest(unittest.TestCase):
    def test_search_preserves_same_name_shows_and_encodes_query(self):
        values = [
            {"show": show(1)},
            {"show": show(2, premiered="2001-07-09", network={"name": "BBC", "country": {"name": "United Kingdom"}})},
        ]
        with patch.object(service, "urlopen", return_value=response(values)) as transport:
            result = service.search_tv_shows({"query": " The Office & friends "})
        self.assertEqual(set(result), {"result"})
        self.assertIn("ID 1", result["result"])
        self.assertIn("ID 2", result["result"])
        self.assertIn("2001-07-09", result["result"])
        self.assertIn("United States", result["result"])
        self.assertIn("United Kingdom", result["result"])
        request = transport.call_args.args[0]
        self.assertEqual(urlparse(request.full_url).netloc, "api.tvmaze.com")
        self.assertEqual(parse_qs(urlparse(request.full_url).query), {"q": ["The Office & friends"]})
        self.assertEqual(transport.call_args.kwargs["timeout"], 10)

    def test_limit_reports_truncation_and_empty_search_is_not_an_error(self):
        with patch.object(service, "urlopen", return_value=response([{"show": show(1)}, {"show": show(2)}])):
            result = service.search_tv_shows({"query": "Office", "limit": 1})["result"]
        self.assertIn("Showing 1 of 2", result)
        self.assertNotIn("ID 2", result)
        with patch.object(service, "urlopen", return_value=response([])):
            result = service.search_tv_shows({"query": "not-a-known-show"})
        self.assertEqual(set(result), {"result"})
        self.assertIn("No matching shows", result["result"])
        self.assertIn("CC BY-SA", result["result"])

    def test_invalid_input_never_calls_provider(self):
        invalid_searches = [{}, {"query": " "}, {"query": 1}, {"query": "x" * 101}]
        invalid_searches += [{"query": "Office", "limit": value} for value in (0, 11, True, "5", 1.5)]
        with patch.object(service, "urlopen") as transport:
            for payload in invalid_searches:
                with self.subTest(payload=payload):
                    self.assertEqual(set(service.search_tv_shows(payload)), {"error"})
            for value in (None, 0, -1, True, "1", "../../etc", 1.5):
                with self.subTest(show_id=value):
                    self.assertEqual(set(service.get_tv_show({"show_id": value})), {"error"})
            transport.assert_not_called()

    def test_next_episode_preserves_offset_and_uses_exact_id(self):
        value = show(
            9,
            status="Running",
            _embedded={
                "nextepisode": {
                    "season": 3,
                    "number": 2,
                    "name": "A new episode",
                    "airstamp": "2026-09-10T20:00:00+09:00",
                }
            },
        )
        with patch.object(service, "urlopen", return_value=response(value)) as transport:
            result = service.get_tv_show({"show_id": 9})["result"]
        self.assertIn("Season 3, episode 2", result)
        self.assertIn("2026-09-10T20:00:00+09:00", result)
        self.assertIn("not converted to your timezone", result)
        self.assertIn("https://www.tvmaze.com/shows/9", result)
        self.assertEqual(transport.call_args.args[0].full_url, "https://api.tvmaze.com/shows/9?embed=nextepisode")

    def test_absent_next_episode_does_not_infer_cancellation(self):
        for embedded in ({}, {"nextepisode": None}, None):
            with self.subTest(embedded=embedded):
                with patch.object(
                    service, "urlopen", return_value=response(show(status="Running", _embedded=embedded))
                ):
                    result = service.get_tv_show({"show_id": 1})["result"]
                self.assertIn("Status: Running", result)
                self.assertIn("No next episode is currently listed", result)
                self.assertIn("does not by itself mean", result)

    def test_falsey_malformed_embedded_data_is_not_reported_as_absent(self):
        for embedded in ([], "", False, 0):
            with self.subTest(embedded=embedded):
                with patch.object(service, "urlopen", return_value=response(show(_embedded=embedded))):
                    result = service.get_tv_show({"show_id": 1})
                self.assertEqual(set(result), {"error"})
                self.assertIn("unexpected episode information", result["error"])

    def test_invalid_or_naive_provider_timestamps_are_not_presented_as_local_time(self):
        for timestamp in ("2026-09-10T20:00:00", "not-a-date", 42):
            with self.subTest(timestamp=timestamp):
                value = show(_embedded={"nextepisode": {"airstamp": timestamp}})
                with patch.object(service, "urlopen", return_value=response(value)):
                    self.assertEqual(set(service.get_tv_show({"show_id": 1})), {"error"})

    def test_date_only_and_nullable_episode_numbers_do_not_invent_airtime(self):
        value = show(_embedded={"nextepisode": {"season": 1, "number": None, "name": None, "airdate": "2026-09-10"}})
        with patch.object(service, "urlopen", return_value=response(value)):
            result = service.get_tv_show({"show_id": 1})["result"]
        self.assertIn("Next episode: title not announced", result)
        self.assertIn("exact timestamp not supplied", result)
        self.assertNotIn("00:00", result)

    def test_streaming_show_and_missing_channel_are_supported(self):
        value = show(network=None, webChannel={"name": "Netflix", "country": None})
        with patch.object(service, "urlopen", return_value=response(value)):
            self.assertIn("Netflix", service.get_tv_show({"show_id": 1})["result"])
        with patch.object(service, "urlopen", return_value=response(show(network=None))):
            self.assertIn("Channel not listed", service.get_tv_show({"show_id": 1})["result"])

    def test_provider_not_found_rate_limit_and_network_errors_are_distinct(self):
        errors = [
            (HTTPError("https://api.tvmaze.com/shows/1", 404, "missing", {}, None), "could not find"),
            (HTTPError("https://api.tvmaze.com/shows/1", 429, "limit", {}, None), "rate limiting"),
            (HTTPError("https://api.tvmaze.com/shows/1", 503, "down", {}, None), "temporarily unavailable"),
            (URLError("private transport detail"), "Could not reach"),
            (TimeoutError("private timeout detail"), "Could not reach"),
        ]
        for error, expected in errors:
            with self.subTest(error=type(error).__name__, expected=expected):
                with patch.object(service, "urlopen", side_effect=error):
                    result = service.get_tv_show({"show_id": 1})
                self.assertEqual(set(result), {"error"})
                self.assertIn(expected, result["error"])
                self.assertNotIn("private", result["error"])

    def test_malformed_and_oversized_provider_responses_are_errors(self):
        for body in (b"not json", b"\xff", b"x" * (service.MAX_RESPONSE_BYTES + 1)):
            with self.subTest(length=len(body)):
                with patch.object(service, "urlopen", return_value=io.BytesIO(body)):
                    self.assertEqual(set(service.get_tv_show({"show_id": 1})), {"error"})
        for value in ([], {}, show(2), show(_embedded="unexpected"), show(_embedded={"nextepisode": "unexpected"})):
            with self.subTest(value=value):
                with patch.object(service, "urlopen", return_value=response(value)):
                    self.assertEqual(set(service.get_tv_show({"show_id": 1})), {"error"})
        for value in ({"not": "a list"}, [{"show": None}]):
            with patch.object(service, "urlopen", return_value=response(value)):
                self.assertEqual(set(service.search_tv_shows({"query": "Office"})), {"error"})

    def test_truncated_chunked_body_returns_error_from_both_tools(self):
        class TruncatedSocket:
            def makefile(self, *args, **kwargs):
                return io.BytesIO(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nA\r\n{}")

        for handler, payload in (
            (service.search_tv_shows, {"query": "Office"}),
            (service.get_tv_show, {"show_id": 1}),
        ):
            with self.subTest(tool=handler.__name__):
                upstream = HTTPResponse(TruncatedSocket())
                upstream.begin()
                with patch.object(service, "urlopen", return_value=upstream):
                    result = handler(payload)
                self.assertEqual(set(result), {"error"})
                self.assertIn("Could not reach TVMaze", result["error"])
                self.assertTrue(upstream.isclosed())

    def test_manifest_exposes_json_post_tools_with_required_fields(self):
        self.assertEqual({tool["name"] for tool in service.TOOLS}, {"search_tv_shows", "get_tv_show"})
        for tool in service.TOOLS:
            self.assertEqual(tool["method"], "POST")
            self.assertFalse(tool["auth_required"])
            self.assertEqual(tool["endpoint"], "/tools/" + tool["name"])
            self.assertEqual(tool["parameters"]["type"], "object")
            self.assertTrue(tool["parameters"]["required"])


if __name__ == "__main__":
    unittest.main()
