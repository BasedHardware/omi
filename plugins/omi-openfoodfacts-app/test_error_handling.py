"""Hermetic tests for error handling and sensitive exception leak prevention in Open Food Facts app."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

# --- Hermetic stubs for environments without FastAPI/Pydantic/Requests installed ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class DummyRequest:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi_mod.FastAPI = DummyFastAPI
    fastapi_mod.Request = DummyRequest
    sys.modules["fastapi"] = fastapi_mod

if "pydantic" not in sys.modules:
    pydantic_mod = ModuleType("pydantic")

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod.BaseModel = DummyBaseModel
    sys.modules["pydantic"] = pydantic_mod

if "starlette.concurrency" not in sys.modules:
    concurrency_mod = ModuleType("starlette.concurrency")

    async def run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    concurrency_mod.run_in_threadpool = run_in_threadpool
    sys.modules["starlette.concurrency"] = concurrency_mod

if "requests" not in sys.modules:
    requests_mod = ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_mod.RequestException = RequestException
    requests_mod.get = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_mod

import main


def _run(coro):
    return asyncio.run(coro)


class OpenFoodFactsErrorSanitizationTests(unittest.TestCase):
    def test_openfoodfacts_get_request_exception_sanitization(self):
        sensitive_msg = "Connection reset by peer at 10.0.0.12:443 (token=secret_key_999)"
        err = main.requests.RequestException(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            res = main._openfoodfacts_get("/test")

        self.assertIn("error", res)
        self.assertEqual(res["error"], "Open Food Facts request failed.")
        self.assertNotIn("10.0.0.12", res["error"])
        self.assertNotIn("secret_key_999", res["error"])

    def test_openfoodfacts_get_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database conn failed at postgres://user:secret@10.0.0.99:5432"
        err = RuntimeError(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            res = main._openfoodfacts_get("/test")

        self.assertIn("error", res)
        self.assertEqual(res["error"], "Unexpected error communicating with Open Food Facts.")
        self.assertNotIn("10.0.0.99", res["error"])
        self.assertNotIn("secret", res["error"])

    def test_tool_search_foods_network_failure(self):
        sensitive_msg = "Timeout accessing proxy http://corp-proxy.internal:8080"
        err = main.requests.RequestException(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            req = main.Request({"query": "oat milk"})
            resp = _run(main.tool_search_foods(req))

        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "Open Food Facts request failed.")
        self.assertNotIn("corp-proxy.internal", resp.message)
        self.assertNotIn("corp-proxy.internal", str(resp.data))

    def test_tool_lookup_barcode_network_failure(self):
        sensitive_msg = "SSLError at /var/secrets/cert.pem"
        err = main.requests.RequestException(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            req = main.Request({"barcode": "737628064502"})
            resp = _run(main.tool_lookup_barcode(req))

        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "Open Food Facts request failed.")
        self.assertNotIn("/var/secrets/cert.pem", resp.message)
        self.assertNotIn("/var/secrets/cert.pem", str(resp.data))

    def test_tool_compare_foods_network_failure(self):
        sensitive_msg = "ConnectTimeout to 192.168.1.1:8080 with api_key=priv_key_123"
        err = main.requests.RequestException(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            req = main.Request({"barcodes": ["737628064502"]})
            resp = _run(main.tool_compare_foods(req))

        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "no products found")
        self.assertNotIn("priv_key_123", str(resp.data))

    def test_tool_check_allergens_network_failure(self):
        sensitive_msg = "ConnectionRefused to internal-db.cluster.local"
        err = main.requests.RequestException(sensitive_msg)

        with patch.object(main.requests, "get", side_effect=err):
            req = main.Request({"barcode": "737628064502", "avoid": ["peanuts"]})
            resp = _run(main.tool_check_allergens(req))

        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "Open Food Facts request failed.")
        self.assertNotIn("internal-db.cluster.local", resp.message)


if __name__ == "__main__":
    unittest.main()
