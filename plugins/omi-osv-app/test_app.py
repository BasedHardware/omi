"""Exercise Omi JSON endpoints against an in-process, network-free OSV API."""

import copy
import json
import sys
import unittest

import httpx
from fastapi.testclient import TestClient

from main import create_app
from osv_service import MAX_RESPONSE_BYTES, MAX_RESULT_CHARS

# Minimal OSV-schema fixtures, not claims about actual packages or releases.
ADVISORY = {
    "id": "GHSA-example-0001",
    "summary": "Example parsing issue",
    "aliases": ["CVE-2099-0001"],
    "affected": [
        {
            "package": {"ecosystem": "PyPI", "name": "demo-lib"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0"}]},
                {"type": "ECOSYSTEM", "events": [{"introduced": "3.0"}, {"fixed": "3.1"}]},
            ],
        },
        {
            "package": {"ecosystem": "npm", "name": "different-package"},
            "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "99.0"}]}],
        },
    ],
    "references": [{"type": "ADVISORY", "url": "https://example.org/advisory/1"}],
}
QUERY = {"ecosystem": "PyPI", "package_name": "demo-lib", "version": "1.0"}
QUERY_PATH = "/tools/query_package_vulnerabilities"
DETAIL_PATH = "/tools/get_vulnerability"


class ToolTests(unittest.TestCase):
    def client(self, handler):
        # Every test installs MockTransport. An accidental HTTP request outside
        # this client cannot be hidden by a fixture returning preformatted text.
        return TestClient(create_app(transport=httpx.MockTransport(handler)))

    def test_manifest_is_discoverable_and_invocations_drop_omi_metadata(self):
        upstream = []

        def handler(request):
            upstream.append(request)
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "api.osv.dev")
            self.assertEqual(request.url.path, "/v1/query")
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                json.loads(request.content),
                {"package": {"ecosystem": "PyPI", "name": "demo-lib"}, "version": "1.0"},
            )
            return httpx.Response(200, json={"vulns": [ADVISORY]})

        with self.client(handler) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            tools = client.get("/.well-known/omi-tools.json").json()["tools"]
            self.assertEqual({tool["name"] for tool in tools}, {"query_package_vulnerabilities", "get_vulnerability"})
            for tool in tools:
                self.assertIs(tool["auth_required"], False)
                self.assertEqual(tool["method"], "POST")
                self.assertEqual(tool["parameters"]["type"], "object")
                self.assertNotIn("uid", tool["parameters"]["properties"])
            response = client.post(
                tools[0]["endpoint"],
                json={
                    **QUERY,
                    "ecosystem": " pypi ",
                    "uid": "private-user",
                    "app_id": "private-app",
                    "tool_name": tools[0]["name"],
                    "geolocation": {"latitude": 42},
                    "access_token": "private-canary",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"result"})
        result = response.json()["result"]
        self.assertIn("2.0", result)
        self.assertIn("3.1", result)
        self.assertIn("different release branches", result)
        self.assertNotIn("99.0", result)
        self.assertIn("https://osv.dev/vulnerability/GHSA-example-0001", result)
        self.assertNotIn("private-", result)
        self.assertEqual(len(upstream), 1)

    def test_exact_npm_scoped_package_is_not_rewritten(self):
        def handler(request):
            self.assertEqual(json.loads(request.content)["package"], {"ecosystem": "npm", "name": "@scope/pkg"})
            return httpx.Response(200, json={})

        with self.client(handler) as client:
            data = client.post(QUERY_PATH, json={**QUERY, "ecosystem": "npm", "package_name": "@scope/pkg"}).json()
        self.assertIn("unknown package/version", data["result"])

    def test_empty_success_does_not_assert_safety_or_package_existence(self):
        for body in ({}, {"vulns": []}):
            with self.subTest(body=body), self.client(lambda request: httpx.Response(200, json=body)) as client:
                result = client.post(QUERY_PATH, json=QUERY).json()["result"]
                self.assertIn("no matching advisory records", result)
                self.assertIn("unknown package/version", result)
                self.assertIn("not a confirmation", result)

    def test_limits_pagination_and_aliases_are_explicit(self):
        second = {**ADVISORY, "id": "PYSEC-example-0001"}
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"vulns": [ADVISORY, second], "next_page_token": "private-token"})

        with self.client(handler) as client:
            result = client.post(QUERY_PATH, json={**QUERY, "limit": 1}).json()["result"]
        self.assertIn("2 advisory record(s)", result)
        self.assertIn("not a count of unique vulnerabilities", result)
        self.assertIn("additional pages", result)
        self.assertNotIn("private-token", result)
        self.assertNotIn("PYSEC-example-0001", result)
        self.assertLessEqual(len(result), MAX_RESULT_CHARS)
        self.assertEqual(len(requests), 1)

    def test_detail_handles_withdrawn_missing_summary_and_no_fixed_version(self):
        record = copy.deepcopy(ADVISORY)
        record.pop("summary")
        record["details"] = "Advisory explanation"
        record["withdrawn"] = "2026-01-01T00:00:00Z"
        record["affected"][0]["ranges"] = [
            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"last_affected": "1.1"}]}
        ]
        record["references"] += [{"url": "https://user:secret@example.org/"}, {"url": "javascript:alert(1)"}]

        def handler(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(str(request.url), "https://api.osv.dev/v1/vulns/GHSA-example-0001")
            return httpx.Response(200, json=record)

        with self.client(handler) as client:
            data = client.post(DETAIL_PATH, json={"vulnerability_id": ADVISORY["id"]}).json()
        self.assertEqual(set(data), {"result"})
        self.assertIn("WITHDRAWN", data["result"])
        self.assertIn("Advisory explanation", data["result"])
        self.assertIn("No fixed marker reported", data["result"])
        self.assertIn("last_affected: 1.1", data["result"])
        self.assertIn("https://example.org/advisory/1", data["result"])
        self.assertNotIn("secret", data["result"])
        self.assertNotIn("javascript:", data["result"])

    def test_invalid_inputs_do_not_send_requests_or_echo_sensitive_values(self):
        def no_request(request):
            self.fail("Invalid tool input reached OSV")

        cases = [
            (QUERY_PATH, {**QUERY, "ecosystem": "private-canary"}),
            (QUERY_PATH, {**QUERY, "package_name": " "}),
            (QUERY_PATH, {**QUERY, "version": ">=1"}),
            (QUERY_PATH, {**QUERY, "limit": 11}),
            (QUERY_PATH, {**QUERY, "limit": True}),
            (DETAIL_PATH, {"vulnerability_id": "../../private-canary"}),
        ]
        with self.client(no_request) as client:
            for path, payload in cases:
                with self.subTest(path=path, payload=payload):
                    response = client.post(path, json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(set(response.json()), {"error"})
                    self.assertNotIn("private-canary", response.text)
            self.assertIn("error", client.post(QUERY_PATH, content=b'{"uid":"private-canary",').json())

    def test_status_and_transport_failures_are_errors_not_empty_results(self):
        for status, returned_status, expected in (
            (400, 400, "rejected"),
            (404, 404, "did not find"),
            (429, 429, "rate limiting"),
            (503, 502, "unavailable"),
            (302, 502, "unexpected status"),
        ):
            with self.subTest(status=status):
                calls = []

                def handler(request):
                    calls.append(request)
                    return httpx.Response(
                        status, text="private-canary", headers={"Location": "https://other.example/secret"}
                    )

                with self.client(handler) as client:
                    response = client.post(DETAIL_PATH, json={"vulnerability_id": ADVISORY["id"]})
                self.assertEqual(response.status_code, returned_status)
                self.assertEqual(set(response.json()), {"error"})
                self.assertIn(expected, response.json()["error"])
                self.assertNotIn("private-canary", response.text)
                self.assertEqual(len(calls), 1)
        for exception, returned_status, expected in (
            (httpx.ReadTimeout, 504, "timed out"),
            (httpx.ConnectError, 502, "Could not reach"),
        ):

            def handler(request):
                raise exception("private-canary", request=request)

            with self.subTest(exception=exception), self.client(handler) as client:
                response = client.post(QUERY_PATH, json=QUERY)
                self.assertEqual(response.status_code, returned_status)
                self.assertEqual(set(response.json()), {"error"})
                self.assertIn(expected, response.json()["error"])
                self.assertNotIn("private-canary", response.text)

    def test_invalid_utf8_body_uses_the_tool_error_contract(self):
        def no_request(request):
            self.fail("An undecodable body reached OSV")

        with self.client(no_request) as client:
            response = client.post(QUERY_PATH, content=b"\xff", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"error"})
        self.assertIn("UTF-8", response.json()["error"])

    def test_malformed_and_oversized_upstream_data_are_not_no_matches(self):
        for content in (
            b"not-json",
            b"[]",
            b'{"vulns":null}',
            b'{"message":"oops"}',
            b'{"vulns":[{}]}',
            b"x" * (MAX_RESPONSE_BYTES + 1),
        ):
            with self.subTest(size=len(content)), self.client(
                lambda request: httpx.Response(200, content=content)
            ) as client:
                response = client.post(QUERY_PATH, json=QUERY)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(set(response.json()), {"error"})
                self.assertNotIn("no matching", response.text)

    def test_deeply_nested_upstream_json_uses_the_error_contract(self):
        depth = sys.getrecursionlimit() + 100
        content = b'{"vulns":' + b"[" * depth + b'"provider-canary"' + b"]" * depth + b"}"
        self.assertLess(len(content), MAX_RESPONSE_BYTES)
        for path, payload in ((QUERY_PATH, QUERY), (DETAIL_PATH, {"vulnerability_id": ADVISORY["id"]})):
            with self.subTest(path=path), self.client(lambda request: httpx.Response(200, content=content)) as client:
                response = client.post(path, json=payload)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(set(response.json()), {"error"})
                self.assertIn("invalid response", response.json()["error"])
                self.assertNotIn("provider-canary", response.text)


if __name__ == "__main__":
    unittest.main()
