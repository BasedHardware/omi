import asyncio
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure required env vars are present before config load
os.environ["MICROSOFT_CLIENT_ID"] = "dummy-client-id"
os.environ["MICROSOFT_CLIENT_SECRET"] = "dummy-client-secret"
os.environ["SESSION_SECRET"] = "dummy-session-secret-key-12345"

# Hermetic service stubs so the test runs without external network or credentials
class AnyHandlers(types.ModuleType):
    def __getattr__(self, name):
        async def handler(user_id, **kwargs):
            return {}
        return handler

services = types.ModuleType("services")
for name in ("auth", "mail", "profile", "calendar", "teams", "sharepoint"):
    sub = AnyHandlers(f"services.{name}")
    setattr(services, name, sub)
    sys.modules[f"services.{name}"] = sub

services.auth.AuthError = type("AuthError", (Exception,), {})
services.auth.build_auth_url = MagicMock(return_value="https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=test")
services.auth.exchange_code_for_token = AsyncMock()
services.auth.get_access_token = AsyncMock(return_value="valid-token")
services.auth.disconnect = AsyncMock()
sys.modules["services"] = services

# Ensure plugins/omi-ms365-app is in path
ms365_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(ms365_dir))

import main
from fastapi import HTTPException


class TestMS365SettingsPageEncoding(unittest.TestCase):
    def test_setup_page_escapes_and_quotes_uid(self):
        html_content = asyncio.run(main.setup_page(uid='user"123<script>'))
        self.assertIn('href="/auth/microsoft?uid=user%22123%3Cscript%3E"', html_content)
        self.assertNotIn('href="/auth/microsoft?uid=user"123<script>"', html_content)

    def test_setup_page_normal_uid(self):
        html_content = asyncio.run(main.setup_page(uid="user_abc123"))
        self.assertIn('href="/auth/microsoft?uid=user_abc123"', html_content)

    def test_auth_callback_escapes_error_and_description(self):
        response = asyncio.run(
            main.auth_callback(
                error='<script>alert("err")</script>',
                error_description="<b>Fail</b>",
            )
        )
        self.assertEqual(response.status_code, 400)
        body = response.body.decode()
        self.assertIn("&lt;script&gt;alert(&quot;err&quot;)&lt;/script&gt;: &lt;b&gt;Fail&lt;/b&gt;", body)
        self.assertNotIn('<script>alert("err")</script>', body)
        self.assertNotIn("<b>Fail</b>", body)

    def test_auth_callback_escapes_error_without_description(self):
        response = asyncio.run(
            main.auth_callback(
                error='access_denied<img src=x onerror=1>',
                error_description=None,
            )
        )
        self.assertEqual(response.status_code, 400)
        body = response.body.decode()
        self.assertIn("access_denied&lt;img src=x onerror=1&gt;: None", body)
        self.assertNotIn("<img src=x onerror=1>", body)

    def test_auth_callback_missing_code_or_state(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(main.auth_callback(code=None, state=None))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_auth_callback_successful_exchange(self):
        with patch.object(main._signer, "loads", return_value={"uid": "user_123"}):
            response = asyncio.run(main.auth_callback(code="valid_code", state="valid_state"))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn("✓ Connected", body)
            main.auth.exchange_code_for_token.assert_awaited_once_with("valid_code", "user_123")

    def test_auth_start_redirects_safely(self):
        response = asyncio.run(main.auth_start(uid="user_123"))
        self.assertEqual(response.status_code, 307)
        self.assertTrue(response.headers["location"].startswith("https://login.microsoftonline.com/"))


if __name__ == "__main__":
    unittest.main()
