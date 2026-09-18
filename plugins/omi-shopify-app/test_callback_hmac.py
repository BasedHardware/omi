"""
Hermetic regression tests for Shopify OAuth callback signature checks (#14442).

Ensures /auth/shopify/callback verifies Shopify's HMAC signature and enforces
cryptographically signed state parameters to prevent forged callbacks and login CSRF.
"""

import hashlib
import hmac
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


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


class TemplateResponse:
    def __init__(self, template, context, **kwargs):
        self.template = template
        self.context = context


class TemplatesStub:
    def TemplateResponse(self, template, context, **kwargs):
        return TemplateResponse(template, context, **kwargs)


def module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


stubs = {
    "requests": module("requests", RequestException=OSError, post=Mock(), get=Mock()),
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
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=lambda *a, **kw: TemplatesStub()),
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
    "shopify_main_tested", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


class TestShopifyCallbackSecurity(unittest.TestCase):
    def setUp(self):
        self.secret = shopify.SHOPIFY_CLIENT_SECRET

    def test_state_signing_valid_roundtrip(self):
        uid = "user_valid_123"
        state = shopify._oauth_state_for(uid)
        recovered = shopify._verify_and_extract_state_uid(state)
        self.assertEqual(recovered, uid)

    def test_state_signing_tamper_detection(self):
        uid = "user_victim"
        state = shopify._oauth_state_for(uid)
        tampered = "user_attacker." + state.split(".", 1)[1]
        self.assertIsNone(shopify._verify_and_extract_state_uid(tampered))

    def test_state_signing_malformed_inputs(self):
        self.assertIsNone(shopify._verify_and_extract_state_uid("raw_unsigned_uid"))
        self.assertIsNone(shopify._verify_and_extract_state_uid(""))
        self.assertIsNone(shopify._verify_and_extract_state_uid(None))

    def test_verify_shopify_hmac_valid(self):
        query_params = {
            "code": "auth_code_123",
            "shop": "test-shop.myshopify.com",
            "state": "test_state",
            "timestamp": "1726650000"
        }
        sorted_keys = sorted(query_params.keys())
        msg = "&".join(f"{k}={query_params[k]}" for k in sorted_keys)
        valid_hmac = hmac.new(self.secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        full_query = "&".join(f"{k}={v}" for k, v in query_params.items()) + f"&hmac={valid_hmac}"

        self.assertTrue(shopify.verify_shopify_hmac(full_query, valid_hmac))

    def test_verify_shopify_hmac_tampered(self):
        query = "code=auth_code&shop=store.myshopify.com&state=test&hmac=tampered_signature"
        self.assertFalse(shopify.verify_shopify_hmac(query, "tampered_signature"))

    def test_verify_shopify_hmac_missing(self):
        self.assertFalse(shopify.verify_shopify_hmac("code=auth_code", ""))
        self.assertFalse(shopify.verify_shopify_hmac("code=auth_code", None))

    @patch.object(shopify.requests, "post")
    def test_callback_rejects_invalid_hmac(self, mock_post):
        req = Mock()
        req.url.query = "code=code123&shop=shop.myshopify.com&state=state123&hmac=fake_hmac"
        
        import asyncio
        resp = asyncio.run(
            shopify.shopify_callback(
                request=req,
                code="code123",
                state="state123",
                shop="shop.myshopify.com",
                hmac="fake_hmac"
            )
        )
        self.assertIn("Invalid HMAC signature", resp.context.get("error", ""))
        mock_post.assert_not_called()

    @patch.object(shopify.requests, "post")
    def test_callback_rejects_tampered_state(self, mock_post):
        # Valid HMAC over query, but unsigned/tampered state
        query_params = {
            "code": "code123",
            "shop": "shop.myshopify.com",
            "state": "unsigned_state"
        }
        sorted_keys = sorted(query_params.keys())
        msg = "&".join(f"{k}={query_params[k]}" for k in sorted_keys)
        valid_hmac = hmac.new(self.secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        full_query = "&".join(f"{k}={v}" for k, v in query_params.items()) + f"&hmac={valid_hmac}"

        req = Mock()
        req.url.query = full_query

        import asyncio
        resp = asyncio.run(
            shopify.shopify_callback(
                request=req,
                code="code123",
                state="unsigned_state",
                shop="shop.myshopify.com",
                hmac=valid_hmac
            )
        )
        self.assertIn("Invalid or tampered state", resp.context.get("error", ""))
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
