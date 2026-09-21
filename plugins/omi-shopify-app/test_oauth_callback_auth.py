"""Hermetic regression tests for Shopify OAuth callback authentication (#14442).

Covers the two holes in `/auth/shopify/callback`: the Shopify HMAC was computed
but never checked, and `state` was the raw uid, so a valid foreign grant could
be rebound onto any account.

Runs under standard library unittest without third-party dependencies.
"""

import hashlib
import hmac as hmac_mod
import importlib.util
from pathlib import Path
import sys
import types
import unittest
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
    "shopify_main_oauth_tested", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


SECRET = "shpss_test_secret"
PLACEHOLDER = "YOUR_CLIENT_SECRET_HERE"


def sign(query_string, secret=SECRET):
    """Shopify's documented scheme: decoded pairs, sorted, '&'-joined."""
    import urllib.parse

    params = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    params.pop("hmac", None)
    message = "&".join(
        f"{key}={','.join(values)}" for key, values in sorted(params.items())
    )
    return hmac_mod.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class TestVerifyShopifyHmac(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.object(shopify, "SHOPIFY_CLIENT_SECRET", SECRET)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_accepts_genuine_signature(self):
        qs = "code=abc123&shop=demo.myshopify.com&state=u1%3Asig&timestamp=1700000000"
        self.assertTrue(shopify.verify_shopify_hmac(qs, sign(qs)))

    def test_rejects_forged_signature(self):
        qs = "code=abc123&shop=demo.myshopify.com&state=u1%3Asig"
        self.assertFalse(shopify.verify_shopify_hmac(qs, "0" * 64))

    def test_rejects_missing_signature(self):
        qs = "code=abc123&shop=demo.myshopify.com"
        self.assertFalse(shopify.verify_shopify_hmac(qs, ""))
        self.assertFalse(shopify.verify_shopify_hmac(qs, None))

    def test_rejects_tampered_parameter(self):
        qs = "code=abc123&shop=demo.myshopify.com&timestamp=1700000000"
        signature = sign(qs)
        tampered = qs.replace("demo.myshopify.com", "evil.myshopify.com")
        self.assertFalse(shopify.verify_shopify_hmac(tampered, signature))

    def test_blank_values_are_part_of_signed_message(self):
        # parse_qs drops blank values unless keep_blank_values=True; Shopify
        # signs them, so dropping them rejects legitimate callbacks.
        qs = "code=abc123&note=&shop=demo.myshopify.com"
        self.assertTrue(shopify.verify_shopify_hmac(qs, sign(qs)))

    def test_signature_uses_decoded_pairs_not_urlencode(self):
        # state carries a ':' which urlencode would escape to %3A, changing the
        # signed message and rejecting every real callback.
        qs = "shop=demo.myshopify.com&state=uid123%3Aabcdef"
        expected = hmac_mod.new(
            SECRET.encode("utf-8"),
            b"shop=demo.myshopify.com&state=uid123:abcdef",
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(shopify.verify_shopify_hmac(qs, expected))


class TestFailsClosedWithoutSecret(unittest.TestCase):
    def test_placeholder_secret_rejects_even_matching_signature(self):
        qs = "code=abc123&shop=demo.myshopify.com"
        forged = sign(qs, secret=PLACEHOLDER)
        with patch.object(shopify, "SHOPIFY_CLIENT_SECRET", PLACEHOLDER):
            # The placeholder is public in this repo, so anyone could compute a
            # matching digest. Verification must refuse to run at all.
            self.assertFalse(shopify.verify_shopify_hmac(qs, forged))

    def test_empty_secret_rejects(self):
        qs = "code=abc123&shop=demo.myshopify.com"
        with patch.object(shopify, "SHOPIFY_CLIENT_SECRET", ""):
            self.assertFalse(shopify.verify_shopify_hmac(qs, sign(qs, secret="")))

    def test_state_signing_refuses_without_secret(self):
        with patch.object(shopify, "SHOPIFY_CLIENT_SECRET", PLACEHOLDER):
            with self.assertRaises(Exception):
                shopify._oauth_state_for("uid123")
            self.assertIsNone(shopify._oauth_state_uid("uid123:whatever"))


class TestOAuthState(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.object(shopify, "SHOPIFY_CLIENT_SECRET", SECRET)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_round_trip(self):
        state = shopify._oauth_state_for("uid123")
        self.assertTrue(state.startswith("uid123:"))
        self.assertEqual(shopify._oauth_state_uid(state), "uid123")

    def test_raw_uid_is_rejected(self):
        # The pre-fix behaviour: state == uid. Must no longer be accepted.
        self.assertIsNone(shopify._oauth_state_uid("uid123"))

    def test_tampered_uid_is_rejected(self):
        state = shopify._oauth_state_for("uid123")
        forged = state.replace("uid123:", "victim:")
        self.assertIsNone(shopify._oauth_state_uid(forged))

    def test_tampered_signature_is_rejected(self):
        state = shopify._oauth_state_for("uid123")
        self.assertIsNone(shopify._oauth_state_uid("uid123:" + "0" * 64))

    def test_empty_and_malformed_states_are_rejected(self):
        for bad in ("", ":", ":sig", None):
            self.assertIsNone(shopify._oauth_state_uid(bad))

    def test_uid_containing_colon_round_trips(self):
        state = shopify._oauth_state_for("tenant:uid123")
        self.assertEqual(shopify._oauth_state_uid(state), "tenant:uid123")


class TestCallbackRefusesUnverifiedGrants(unittest.IsolatedAsyncioTestCase):
    """The callback must not exchange the code unless both checks pass."""

    def setUp(self):
        self.patcher = patch.object(shopify, "SHOPIFY_CLIENT_SECRET", SECRET)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _request(self, query_string):
        req = Mock()
        req.url = Mock()
        req.url.query = query_string
        req.json = AsyncMock(return_value={})
        return req

    async def _call(self, query_string, hmac_value, state, shop="demo.myshopify.com"):
        posted = Mock()
        with patch.object(shopify, "templates", Mock()), patch.object(
            shopify, "requests", Mock(post=posted)
        ):
            await shopify.shopify_callback(
                request=self._request(query_string),
                code="abc123",
                state=state,
                shop=shop,
                hmac_value=hmac_value,
            )
        return posted

    async def test_forged_hmac_does_not_exchange_code(self):
        state = shopify._oauth_state_for("uid123")
        qs = f"code=abc123&shop=demo.myshopify.com&state={state}"
        posted = await self._call(qs, "0" * 64, state)
        posted.assert_not_called()

    async def test_foreign_state_does_not_exchange_code(self):
        # Attacker completes a genuine Shopify OAuth for their own shop, then
        # points the state at a victim uid. HMAC is valid; state is not ours.
        qs = "code=abc123&shop=demo.myshopify.com&state=victim"
        signature = sign(qs)
        posted = await self._call(qs, signature, "victim")
        posted.assert_not_called()

    async def test_valid_callback_exchanges_code(self):
        state = shopify._oauth_state_for("uid123")
        qs = f"code=abc123&shop=demo.myshopify.com&state={state}"
        posted = await self._call(qs, sign(qs), state)
        posted.assert_called_once()


if __name__ == "__main__":
    unittest.main()
