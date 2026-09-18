"""Hermetic regression tests for the Shopify OAuth callback signature checks.

Before this fix, /auth/shopify/callback accepted any caller-supplied
``code``, ``state``, ``shop`` and ``hmac`` without verifying Shopify's
HMAC or that the state was issued by our own /auth/shopify initiation.
A forged callback could bind an attacker's shop grant to an arbitrary
uid and aim the code exchange at a hostile host. Runs under stdlib
unittest without third-party dependencies.
"""

import asyncio
import hashlib
import hmac as hmac_module
import importlib.util
from pathlib import Path
import sys
import types
import unittest
import urllib.parse
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get
    mount = lambda *args, **kwargs: None


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


stubs = {
    "requests": module("requests", RequestException=OSError),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi",
        **{
            name: Framework
            for name in ("FastAPI", "HTTPException", "Request", "Query", "Form")
        },
    ),
    "fastapi.responses": module(
        "fastapi.responses",
        **{
            name: Framework
            for name in ("HTMLResponse", "RedirectResponse", "JSONResponse")
        },
    ),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "db": module(
        "db",
        **{
            name: Mock()
            for name in (
                "store_shopify_tokens",
                "get_shopify_tokens",
                "delete_shopify_tokens",
                "store_default_store",
                "get_default_store",
                "get_user_settings",
            )
        },
    ),
    "models": module(
        "models",
        **{
            name: Response
            for name in (
                "ChatToolResponse",
                "ShopifyOrder",
                "ShopifyCustomer",
                "ShopifyLineItem",
                "ShopifyAnalytics",
                "ShopifyShop",
            )
        },
    ),
}

spec = importlib.util.spec_from_file_location(
    "shopify_main_tested_hmac", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


TEST_SECRET = "test-client-secret"


def sign_query(secret: str, **params) -> str:
    """Build a Shopify-style signed query string and return it."""
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    digest = hmac_module.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    params["hmac"] = digest
    return urllib.parse.urlencode(params)


def mock_request(query: str):
    req = Mock()
    req.url = Mock()
    req.url.query = query
    return req


class CallbackHmacTest(unittest.TestCase):
    def setUp(self):
        self.secret_patcher = patch.object(
            shopify, "SHOPIFY_CLIENT_SECRET", TEST_SECRET
        )
        self.secret_patcher.start()
        self.addCleanup(self.secret_patcher.stop)

        self.templates_patcher = patch.object(shopify, "templates")
        self.mock_templates = self.templates_patcher.start()
        self.addCleanup(self.templates_patcher.stop)

        self.post_patcher = patch.object(shopify.requests, "post", create=True)
        self.mock_post = self.post_patcher.start()
        self.addCleanup(self.post_patcher.stop)

        self.get_patcher = patch.object(shopify.requests, "get", create=True)
        self.mock_get = self.get_patcher.start()
        self.addCleanup(self.get_patcher.stop)

    def run_callback(self, query: str, **params):
        kwargs = {
            "code": "code1",
            "state": "uid1",
            "shop": "shop1.myshopify.com",
            "hmac": None,
            "error": None,
            "error_description": None,
        }
        kwargs.update(params)
        return asyncio.run(
            shopify.shopify_callback(mock_request(query), **kwargs)
        )

    def test_forged_hmac_is_rejected_before_token_exchange(self):
        query = "code=code1&state=uid1&shop=evil.example.com&hmac=deadbeef"
        self.run_callback(query, hmac="deadbeef", shop="evil.example.com")
        self.mock_post.assert_not_called()
        template = self.mock_templates.TemplateResponse.call_args
        self.assertEqual(
            template.kwargs.get("error") or template[0][1]["error"],
            "Invalid OAuth signature",
        )

    def test_missing_hmac_is_rejected(self):
        query = "code=code1&state=uid1&shop=shop1.myshopify.com"
        self.run_callback(query, hmac=None)
        self.mock_post.assert_not_called()

    def test_signed_state_rejects_uid_rebinding(self):
        # Attacker's own completed OAuth flow supplies a valid Shopify hmac,
        # but the signed state for uid1 was never issued with this binding.
        state = "uid1:00000000000000000000000000000000"
        query = sign_query(
            TEST_SECRET,
            code="code1",
            state=state,
            shop="attacker.myshopify.com",
        )
        params = dict(urllib.parse.parse_qsl(query))
        self.run_callback(query, **params)
        self.mock_post.assert_not_called()

    def test_valid_signature_and_state_reach_token_exchange(self):
        state = shopify._oauth_state_for("uid1")
        query = sign_query(
            TEST_SECRET,
            code="code1",
            state=state,
            shop="shop1.myshopify.com",
        )
        params = dict(urllib.parse.parse_qsl(query))
        self.mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"access_token": "tok", "scope": "s"}),
        )
        self.mock_get.return_value = Mock(status_code=500)
        self.run_callback(query, **params)
        self.mock_post.assert_called_once()
        token_url = self.mock_post.call_args[0][0]
        self.assertTrue(token_url.startswith("https://shop1.myshopify.com/"))
        shopify.store_shopify_tokens = Mock()
        # state round-trip: issued uid is what gets bound
        self.assertEqual(shopify._oauth_state_uid(state), "uid1")

    def test_state_round_trip_and_tamper(self):
        state = shopify._oauth_state_for("uid1")
        self.assertEqual(shopify._oauth_state_uid(state), "uid1")
        # Tampered uid or truncated signature must not resolve.
        self.assertIsNone(shopify._oauth_state_uid("uid2" + state[4:]))
        self.assertIsNone(shopify._oauth_state_uid(state[:-2] + "00"))
        self.assertIsNone(shopify._oauth_state_uid("uid1"))
        self.assertIsNone(shopify._oauth_state_uid(":abc"))


if __name__ == "__main__":
    unittest.main()
