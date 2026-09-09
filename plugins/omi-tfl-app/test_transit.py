"""Hermetic production-tool and HTTP-transport tests; no runtime dependencies."""

import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

from transit import ATTRIBUTION, MAX_RESPONSE_BYTES, TfLClient, ToolError, execute

NOW = datetime(2026, 9, 9, 8, tzinfo=timezone.utc)


class FakeAPI:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self.response


def arrival(expected, reported="2026-09-09T07:59:45Z"):
    return {
        "lineName": "Victoria",
        "destinationName": "Brixton",
        "platformName": "Southbound - Platform 5",
        "timestamp": reported,
        "expectedArrival": expected,
        "timeToStation": 9999,
    }


class TransitToolsTests(unittest.TestCase):
    def test_status_preserves_disruptions_and_marks_missing_requested_lines(self):
        api = FakeAPI(
            [
                {
                    "id": "victoria",
                    "name": "Victoria",
                    "lineStatuses": [
                        {"statusSeverityDescription": "Minor Delays", "reason": "Signal failure at Oxford Circus."},
                        {"statusSeverityDescription": "Part Closure", "reason": "Engineering work."},
                    ],
                },
            ]
        )
        response = execute("get_line_status", {"line_ids": ["Victoria", "central", "victoria"]}, api, NOW)
        self.assertEqual(api.calls, [("/Line/victoria,central/Status", None)])
        self.assertIn("Signal failure", response["result"])
        self.assertIn("Part Closure", response["result"])
        self.assertIn("central. Those lines' status is unknown", response["result"])
        self.assertIn(ATTRIBUTION, response["result"])

    def test_default_status_only_queries_tube_and_never_invents_good_service(self):
        api = FakeAPI([{"id": "victoria", "name": "Victoria", "lineStatuses": []}])
        result = execute("get_line_status", {}, api, NOW)["result"]
        self.assertEqual(api.calls[0][0], "/Line/Mode/tube/Status")
        self.assertIn("London Underground", result)
        self.assertIn("status not supplied", result)
        self.assertNotIn("Good Service", result)
        self.assertIn("error", execute("get_line_status", {}, FakeAPI([]), NOW))

    def test_search_returns_disambiguation_ids_and_does_not_forward_omi_identity(self):
        api = FakeAPI(
            {
                "total": 2,
                "matches": [
                    {"id": "940GZZLUOXC", "name": "Oxford Circus Underground Station", "modes": ["tube"]},
                    {"id": "490000175A", "name": "Oxford Circus Station", "modes": ["bus"]},
                ],
            }
        )
        result = execute(
            "find_stops", {"query": "Oxford Circus", "limit": 1, "uid": "private", "mode": "tube"}, api, NOW
        )
        self.assertEqual(
            api.calls,
            [
                (
                    "/StopPoint/Search",
                    {
                        "query": "Oxford Circus",
                        "maxResults": 1,
                        "includeHubs": "false",
                        "modes": "tube",
                    },
                )
            ],
        )
        self.assertIn("940GZZLUOXC", result["result"])
        self.assertNotIn("490000175A", result["result"])
        self.assertIn("Refine the query", result["result"])

    def test_arrivals_sort_absolute_times_keep_source_time_and_remove_expired_predictions(self):
        api = FakeAPI(
            [
                arrival("2026-09-09T08:10:00Z"),
                arrival("2026-09-09T08:01:00Z"),
                arrival("2026-09-09T08:59:00+01:00"),
            ]
        )
        result = execute("get_arrivals", {"stop_id": "940GZZLUOXC", "limit": 1}, api, NOW)["result"]
        self.assertIn("2026-09-09T08:01:00+00:00", result)
        self.assertIn("2026-09-09T07:59:45+00:00", result)
        self.assertNotIn("08:10", result)
        self.assertNotIn("9999", result)
        self.assertEqual(api.calls, [("/StopPoint/940GZZLUOXC/Arrivals", None)])

    def test_no_predictions_does_not_mean_no_service(self):
        for predictions in ([], [arrival("2026-09-09T07:59:00Z")]):
            with self.subTest(predictions=predictions):
                result = execute("get_arrivals", {"stop_id": "940GZZLUOXC"}, FakeAPI(predictions), NOW)
                self.assertIn("does not establish whether service is running", result["result"])

    def test_provider_expiry_and_deletions_override_a_future_arrival(self):
        expired = {**arrival("2026-09-09T08:10:00Z"), "timeToLive": "2026-09-09T07:59:59Z"}
        deleted = {**arrival("2026-09-09T08:10:00Z"), "operationType": 2}
        current = {**arrival("2026-09-09T08:05:00Z"), "timeToLive": "2026-09-09T08:04:00Z", "operationType": 1}
        api = FakeAPI([expired, deleted, current])
        result = execute("get_arrivals", {"stop_id": "940GZZLUOXC"}, api, NOW)["result"]
        self.assertIn("08:05", result)
        self.assertNotIn("08:10", result)
        only_expired = execute("get_arrivals", {"stop_id": "940GZZLUOXC"}, FakeAPI([expired, deleted]), NOW)
        self.assertIn("no upcoming arrival predictions", only_expired["result"])

    def test_bad_input_fails_before_any_provider_call(self):
        cases = [
            ("get_arrivals", {"stop_id": "../Line/victoria"}),
            ("get_arrivals", {"stop_id": "940GZZLUOXC", "limit": True}),
            ("get_line_status", {"line_ids": "victoria"}),
            ("get_line_status", {"line_ids": ["victoria?detail=true"]}),
            ("find_stops", {"query": " "}),
            ("find_stops", {"query": "Oxford", "mode": "aircraft"}),
            ("find_stops", []),
        ]
        for name, payload in cases:
            with self.subTest(name=name, payload=payload):
                api = FakeAPI({})
                self.assertIn("error", execute(name, payload, api, NOW))
                self.assertEqual(api.calls, [])

    def test_malformed_provider_responses_return_tool_errors(self):
        cases = [
            ("get_line_status", {}, {"message": "not a line list"}),
            ("get_line_status", {}, [{"id": "victoria", "name": "Victoria", "lineStatuses": [{}]}]),
            ("find_stops", {"query": "Oxford"}, {"matches": None}),
            (
                "find_stops",
                {"query": "Oxford"},
                {
                    "total": "unknown",
                    "matches": [
                        {"id": "940GZZLUOXC", "name": "Oxford", "modes": []},
                    ],
                },
            ),
            ("get_arrivals", {"stop_id": "940GZZLUOXC"}, [arrival("2026-09-09T08:10:00")]),
        ]
        for name, payload, response in cases:
            with self.subTest(name=name, response=response):
                self.assertIn("error", execute(name, payload, FakeAPI(response), NOW))

    def test_manifest_examples_invoke_real_production_tools(self):
        manifest = json.loads(Path(__file__).with_name("omi-tools.json").read_text())
        examples = {
            "get_line_status": {},
            "find_stops": {"query": "Oxford"},
            "get_arrivals": {"stop_id": "940GZZLUOXC"},
        }
        for tool in manifest["tools"]:
            with self.subTest(tool=tool["name"]):
                result = execute(tool["name"], examples[tool["name"]], FakeAPI([]), NOW)
                self.assertNotEqual(result.get("error"), "Unknown transit tool.")
                self.assertEqual(tool["endpoint"], f"/tools/{tool['name']}")
                self.assertEqual(tool["method"], "POST")
                self.assertFalse(tool["auth_required"])


class TfLTransportTests(unittest.TestCase):
    def test_http_request_is_bounded_encoded_and_uses_the_official_origin(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return io.BytesIO(b'{"matches": []}')

        client = TfLClient(opener=opener)
        self.assertEqual(client.get("/StopPoint/Search", {"query": "King's Cross & Bank"}), {"matches": []})
        request, timeout = requests[0]
        self.assertEqual(request.full_url, "https://api.tfl.gov.uk/StopPoint/Search?query=King%27s+Cross+%26+Bank")
        self.assertEqual(timeout, 10)

    def test_provider_errors_and_large_responses_are_safe_and_not_retried(self):
        failures = [
            HTTPError("https://api.tfl.gov.uk/", code, "private upstream body", {}, None) for code in [404, 429, 500]
        ]
        failures.extend([URLError("private proxy detail"), TimeoutError("private timeout detail")])
        for failure in failures:
            calls = []

            def opener(request, timeout):
                calls.append(request)
                raise failure

            with self.subTest(failure=failure):
                result = execute("get_line_status", {}, TfLClient(opener=opener), NOW)
                self.assertIn("error", result)
                self.assertNotIn("private", result["error"])
                self.assertEqual(len(calls), 1)
        for raw in [b"not json", b"x" * (MAX_RESPONSE_BYTES + 1)]:
            with self.subTest(length=len(raw)):
                client = TfLClient(opener=lambda request, timeout: io.BytesIO(raw))
                self.assertIn("error", execute("get_line_status", {}, client, NOW))

    def test_anonymous_quota_recovers_without_network_or_sleep(self):
        current_time = [0]
        calls = []

        def opener(request, timeout):
            calls.append(request)
            return io.BytesIO(b"[]")

        client = TfLClient(opener=opener, clock=lambda: current_time[0])
        for _ in range(40):
            client.get("/Line/victoria/Status")
        with self.assertRaises(ToolError):
            client.get("/Line/victoria/Status")
        self.assertEqual(len(calls), 40)
        current_time[0] = 60
        client.get("/Line/victoria/Status")
        self.assertEqual(len(calls), 41)


if __name__ == "__main__":
    unittest.main()
