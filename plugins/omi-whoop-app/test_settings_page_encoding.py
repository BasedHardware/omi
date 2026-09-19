import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure plugins/omi-whoop-app is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main


class TestWhoopSettingsPageEncoding(unittest.TestCase):
    def test_unauthenticated_root_page_escapes_uid(self):
        with patch.object(main, "get_whoop_tokens", return_value=None):
            response = asyncio.run(main.root(uid='user"123<script>'))
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/auth/whoop?uid=user%22123%3Cscript%3E"', response.body.decode())
            self.assertNotIn('href="/auth/whoop?uid=user"123<script>"', response.body.decode())

    def test_authenticated_root_page_escapes_disconnect_link(self):
        with patch.object(main, "get_whoop_tokens", return_value={"access_token": "valid"}):
            response = asyncio.run(main.root(uid='user"123<script>'))
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/disconnect?uid=user%22123%3Cscript%3E"', response.body.decode())
            self.assertNotIn('href="/disconnect?uid=user"123<script>"', response.body.decode())

    def test_callback_error_is_escaped(self):
        response = asyncio.run(main.whoop_callback(error='<script>alert("xss")</script>'))
        self.assertEqual(response.status_code, 400)
        body = response.body.decode()
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', body)
        self.assertNotIn('<script>alert("xss")</script>', body)

    def test_callback_success_escapes_continue_link(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"access_token": "token123", "expires_in": 3600}

        with patch.object(main, "get_uid_from_oauth_state", return_value='user"123<script>'), \
             patch.object(main, "delete_oauth_state"), \
             patch.object(main, "store_whoop_tokens"), \
             patch("requests.post", return_value=fake_response):
            response = asyncio.run(main.whoop_callback(code="code_123", state="state_123"))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('href="/?uid=user%22123%3Cscript%3E"', body)
            self.assertNotIn('href="/?uid=user"123<script>"', body)

    def test_callback_exception_escapes_error_message(self):
        with patch.object(main, "get_uid_from_oauth_state", return_value="user123"), \
             patch.object(main, "delete_oauth_state"), \
             patch("requests.post", side_effect=Exception('<script>broken</script>')):
            response = asyncio.run(main.whoop_callback(code="code_123", state="state_123"))
            self.assertEqual(response.status_code, 500)
            body = response.body.decode()
            self.assertIn('&lt;script&gt;broken&lt;/script&gt;', body)
            self.assertNotIn('<script>broken</script>', body)

    def test_disconnect_redirect_quotes_uid(self):
        with patch.object(main, "delete_whoop_tokens"):
            response = asyncio.run(main.disconnect(uid='user" 123&test=1'))
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers["location"], "/?uid=user%22%20123%26test%3D1")


if __name__ == "__main__":
    unittest.main()
