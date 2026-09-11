"""Hermetic production tool/client tests. Run with Python 3.11+; no packages needed."""

import asyncio
from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from inaturalist import (
    API_ORIGIN,
    MAX_RESPONSE_BYTES,
    INaturalistTools,
    NoRedirect,
    ToolError,
    manifest,
    public_get,
)


TAXON = {"id": 48662, "name": "Danaus plexippus", "preferred_common_name": "Monarch", "rank": "species"}
PLACE = {"id": 29, "display_name": "Michigan, US"}


class FakeClock:
    now = 100.0

    def __call__(self):
        return self.now


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.calls = []
        self.rows = [TAXON]
        self.status = 200
        self.headers = {}
        self.raw = None
        self.sleeps = []

        async def fetch(path, params):
            self.calls.append((path, params))
            return (
                self.status,
                self.headers,
                self.raw if self.raw is not None else json.dumps({"results": self.rows}).encode(),
            )

        async def sleep(delay):
            self.sleeps.append(delay)
            self.clock.now += delay

        self.tools = INaturalistTools(fetch, self.clock, lambda: 1_700_000_000.0, sleep)

    async def test_taxon_search_preserves_ambiguity_rank_and_result_limit(self):
        self.rows = [{"id": 48663, "name": "Danaus", "rank": "genus"}, TAXON]
        result = await self.tools.run("search_inaturalist_taxa", {"query": " monarch ", "limit": 1})
        self.assertEqual(set(result), {"result"})
        self.assertIn("rank: genus", result["result"])
        self.assertIn("No common name supplied", result["result"])
        self.assertNotIn("Danaus plexippus", result["result"])
        self.assertEqual(self.calls, [("/taxa", {"q": "monarch", "per_page": 1})])

    async def test_exact_taxon_and_taxonomy(self):
        self.rows = [{**TAXON, "ancestors": [{"name": "Animalia"}, {"name": "Arthropoda"}]}]
        result = await self.tools.run("get_inaturalist_taxon", {"taxon_id": 48662})
        self.assertIn("Monarch (Danaus plexippus)", result["result"])
        self.assertIn("Taxonomy: Animalia > Arthropoda", result["result"])
        self.assertEqual(self.calls, [("/taxa/48662", {})])

    async def test_exact_taxon_rejects_wrong_id_and_missing_record(self):
        for rows in ([{**TAXON, "id": 7}], []):
            with self.subTest(rows=rows):
                self.rows = rows
                self.tools.cache.clear()
                self.clock.now += 2
                result = await self.tools.run("get_inaturalist_taxon", {"taxon_id": 48662})
                self.assertEqual(set(result), {"error"})

    async def test_place_search_uses_full_display_name(self):
        self.rows = [PLACE]
        result = await self.tools.run("search_inaturalist_places", {"query": "Michigan"})
        self.assertIn("Michigan, US; ID: 29", result["result"])
        self.assertIn("https://www.inaturalist.org/places/29", result["result"])
        self.assertEqual(self.calls, [("/places/autocomplete", {"q": "Michigan"})])

    async def test_observed_taxa_filter_counts_and_interpretation(self):
        self.rows = [{"count": 0, "taxon": TAXON}]
        result = await self.tools.run("get_inaturalist_observed_taxa", {"place_id": 29, "taxon_id": 47158, "month": 9})
        self.assertIn("observations: 0", result["result"])
        self.assertIn("not population size", result["result"])
        self.assertIn("month 9, across all years", result["result"])
        self.assertEqual(
            self.calls,
            [
                (
                    "/observations/species_counts",
                    {
                        "place_id": 29,
                        "taxon_id": 47158,
                        "month": 9,
                        "quality_grade": "research",
                        "per_page": 5,
                        "page": 1,
                    },
                )
            ],
        )

    async def test_no_observations_does_not_assert_absence(self):
        self.rows = []
        result = await self.tools.run("get_inaturalist_observed_taxa", {"place_id": 29})
        self.assertIn("does not establish absence", result["result"])

    async def test_empty_search_is_distinct_from_upstream_failure(self):
        self.rows = []
        result = await self.tools.run("search_inaturalist_taxa", {"query": "no match"})
        self.assertIn("No matches found", result["result"])
        self.status = 503
        self.clock.now += 2
        self.assertEqual(set(await self.tools.run("search_inaturalist_taxa", {"query": "other"})), {"error"})

    # Caller contract: backend/utils/retrieval/tools/app_tools.py:157-162 makes
    # optional schema fields nullable with None defaults; :315-320 and :350-355
    # forwards tool kwargs as JSON. An omitted optional can therefore arrive as null.
    async def test_caller_null_search_limits_use_documented_default(self):
        for name, row, query, expected_call in (
            ("search_inaturalist_taxa", TAXON, "Monarch", ("/taxa", {"q": "Monarch", "per_page": 5})),
            ("search_inaturalist_places", PLACE, "Michigan", ("/places/autocomplete", {"q": "Michigan"})),
        ):
            with self.subTest(name=name):
                self.rows = [row] * 6
                payload = {
                    "query": query,
                    "limit": None,
                    "uid": "synthetic-user",
                    "app_id": "synthetic-app",
                    "tool_name": name,
                }
                response = await self.tools.run(name, payload)
                self.assertEqual(set(response), {"result"}, response)
                self.assertEqual(response["result"].count("\n- "), 5)
                self.assertEqual(self.calls[-1], expected_call)
                omitted = await self.tools.run(name, {"query": query})
                self.assertEqual(response, omitted)

    async def test_caller_null_observation_options_match_omission(self):
        self.rows = [{"count": 123, "taxon": TAXON}]
        response = await self.tools.run(
            "get_inaturalist_observed_taxa",
            {
                "place_id": 29,
                "taxon_id": None,
                "month": None,
                "limit": None,
                "uid": "synthetic-user",
                "app_id": "synthetic-app",
                "tool_name": "get_inaturalist_observed_taxa",
            },
        )
        self.assertEqual(set(response), {"result"}, response)
        self.assertIn("observations: 123", response["result"])
        self.assertEqual(
            self.calls,
            [
                (
                    "/observations/species_counts",
                    {
                        "place_id": 29,
                        "quality_grade": "research",
                        "per_page": 5,
                        "page": 1,
                    },
                )
            ],
        )
        self.assertEqual(response, await self.tools.run("get_inaturalist_observed_taxa", {"place_id": 29}))
        self.assertEqual(len(self.calls), 1)

    async def test_invalid_inputs_do_not_send_requests(self):
        cases = [
            ("search_inaturalist_taxa", {"query": "   "}),
            ("search_inaturalist_taxa", {"query": "x" * 101}),
            ("search_inaturalist_taxa", {"query": 10}),
            ("search_inaturalist_taxa", {"query": "a\nb"}),
            ("search_inaturalist_taxa", {"query": "owl", "limit": True}),
            ("search_inaturalist_taxa", {"query": "owl", "limit": 0}),
            ("search_inaturalist_taxa", {"query": "owl", "limit": 11}),
            ("search_inaturalist_taxa", {"query": None}),
            ("search_inaturalist_taxa", {"query": "owl", "url": "https://example.invalid"}),
            ("get_inaturalist_taxon", {"taxon_id": "../private"}),
            ("get_inaturalist_taxon", {"taxon_id": 0}),
            ("get_inaturalist_taxon", {"taxon_id": 1.5}),
            ("get_inaturalist_taxon", {"taxon_id": None}),
            ("get_inaturalist_observed_taxa", {"place_id": -1}),
            ("get_inaturalist_observed_taxa", {"place_id": None}),
            ("get_inaturalist_observed_taxa", {"place_id": 29, "taxon_id": 0}),
            ("get_inaturalist_observed_taxa", {"place_id": 29, "taxon_id": True}),
            ("get_inaturalist_observed_taxa", {"place_id": 29, "month": 0}),
            ("get_inaturalist_observed_taxa", {"place_id": 29, "month": True}),
            ("get_inaturalist_observed_taxa", {"place_id": 29, "month": 13}),
            ("search_inaturalist_places", {"query": None}),
            ("search_inaturalist_places", {}),
            ("search_inaturalist_places", []),
        ]
        for name, payload in cases:
            with self.subTest(name=name, payload=payload):
                self.assertEqual(set(await self.tools.run(name, payload)), {"error"})
        self.assertEqual(self.calls, [])

    async def test_omi_context_is_not_forwarded_or_cached(self):
        payload = {
            "query": "Monarch",
            "uid": "synthetic-user",
            "app_id": "synthetic-app",
            "tool_name": "unused",
            "geolocation": {"latitude": 0, "longitude": 0},
        }
        result = await self.tools.run("search_inaturalist_taxa", payload)
        self.assertIn("Monarch", result["result"])
        self.assertEqual(self.calls, [("/taxa", {"q": "Monarch", "per_page": 5})])
        self.assertNotIn("synthetic", repr(self.tools.cache))

    async def test_bad_upstream_shapes_and_counts_are_errors(self):
        for raw in (b"not json", b"[]", b"{}", b'{"results":null}', b'{"results":[null]}'):
            with self.subTest(raw=raw):
                self.raw = raw
                self.clock.now += 2
                self.assertEqual(set(await self.tools.run("get_inaturalist_taxon", {"taxon_id": 48662})), {"error"})
        self.raw = None
        self.rows = [{"count": -1, "taxon": TAXON}]
        self.clock.now += 2
        self.assertEqual(set(await self.tools.run("get_inaturalist_observed_taxa", {"place_id": 29})), {"error"})

    async def test_missing_optional_taxon_metadata_stays_unknown(self):
        self.rows = [{"id": 48662}]
        result = await self.tools.run("get_inaturalist_taxon", {"taxon_id": 48662})
        self.assertIn("rank: Unknown", result["result"])
        self.assertIn("Taxonomy: Not supplied", result["result"])

    async def test_cache_reuses_response_and_original_fetch_time_then_expires(self):
        first = await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"})
        second = await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"})
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)
        self.clock.now += 301
        await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"})
        self.assertEqual(len(self.calls), 2)

    async def test_cache_is_bounded(self):
        for index in range(65):
            self.clock.now += 2
            await self.tools.run("search_inaturalist_taxa", {"query": str(index)})
        self.assertEqual(len(self.tools.cache), 64)
        self.assertNotIn(("/taxa", (("per_page", 5), ("q", "0"))), self.tools.cache)

    async def test_concurrent_requests_share_one_second_budget(self):
        results = await asyncio.gather(
            self.tools.run("search_inaturalist_taxa", {"query": "Monarch"}),
            self.tools.run("search_inaturalist_taxa", {"query": "Owl"}),
        )
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all("result" in result for result in results))
        self.assertEqual(self.sleeps, [1.0])

    async def test_search_then_detail_waits_for_pacing_and_succeeds(self):
        search = await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"})
        detail = await self.tools.run("get_inaturalist_taxon", {"taxon_id": 48662})
        self.assertIn("Monarch", search["result"])
        self.assertIn("Monarch", detail["result"])
        self.assertEqual(self.sleeps, [1.0])
        self.assertEqual(len(self.calls), 2)

    async def test_429_preserves_long_cooldown_and_does_not_retry(self):
        self.status = 429
        self.headers = {"Retry-After": "300"}
        self.assertIn("error", await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"}))
        self.clock.now += 60
        self.status = 200
        result = await self.tools.run("search_inaturalist_taxa", {"query": "Owl"})
        self.assertIn("240 seconds", result["error"])
        self.assertEqual(len(self.calls), 1)
        self.clock.now += 240
        self.assertIn("result", await self.tools.run("search_inaturalist_taxa", {"query": "Owl"}))

    async def test_http_date_and_invalid_retry_after(self):
        for header, delay in (
            (format_datetime(datetime.fromtimestamp(1_700_000_180, timezone.utc)), 180),
            ("invalid", 60),
            ("Infinity", 60),
        ):
            with self.subTest(header=header):
                self.status = 429
                self.headers = {"retry-after": header}
                self.clock.now = self.tools.cooldown_until + 1
                await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"})
                self.assertEqual(self.tools.cooldown_until - self.clock.now, delay)

    async def test_daily_request_budget_rolls_forward(self):
        self.tools.requests.extend([self.clock.now] * 10000)
        self.assertIn("daily", (await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"}))["error"])
        self.assertEqual(self.calls, [])
        self.clock.now += 86400
        self.assertIn("result", await self.tools.run("search_inaturalist_taxa", {"query": "Monarch"}))


class TransportAndManifestTests(unittest.TestCase):
    def test_manifest_advertises_four_relative_unauthenticated_post_tools(self):
        tools = manifest()["tools"]
        self.assertEqual(len(tools), 4)
        for tool in tools:
            self.assertEqual(tool["endpoint"], "/tools/" + tool["name"])
            self.assertEqual(tool["method"], "POST")
            self.assertFalse(tool["auth_required"])

    def test_transport_encodes_query_and_identifies_itself(self):
        response = io.BytesIO(b'{"results":[]}')
        response.status, response.headers = 200, {}
        with patch("inaturalist.build_opener") as opener:
            opener.return_value.open.return_value = response
            status, _, body = public_get("/taxa", {"q": "A&B / café"})
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, API_ORIGIN + "/taxa?q=A%26B+%2F+caf%C3%A9")
        self.assertEqual(request.get_header("User-agent"), "Omi-iNaturalist-Integration/1.0")
        self.assertEqual(opener.return_value.open.call_args.kwargs, {"timeout": 15})
        self.assertEqual((status, body), (200, b'{"results":[]}'))

    def test_transport_limits_response_bytes(self):
        response = io.BytesIO(b"x" * (MAX_RESPONSE_BYTES + 1))
        response.status, response.headers = 200, {}
        with patch("inaturalist.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ToolError, "too much data"):
                public_get("/taxa", {})

    def test_transport_sanitizes_errors_and_preserves_status_headers(self):
        with patch("inaturalist.build_opener") as opener:
            opener.return_value.open.side_effect = URLError("synthetic-sensitive-detail")
            with self.assertRaises(ToolError) as error:
                public_get("/taxa", {})
            self.assertNotIn("synthetic-sensitive", str(error.exception))
            opener.return_value.open.side_effect = HTTPError(
                API_ORIGIN, 429, "rate limited", {"Retry-After": "300"}, io.BytesIO()
            )
            self.assertEqual(public_get("/taxa", {}), (429, {"Retry-After": "300"}, b""))

    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://example.invalid"))


if __name__ == "__main__":
    unittest.main()
