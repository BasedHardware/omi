import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure plugins/omi-dropbox-app and omi-plugin-sdk are in path
dropbox_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(dropbox_dir))
sys.path.insert(0, str(dropbox_dir.parent / "omi-plugin-sdk" / "src"))

import main


class TestDropboxSettingsPageEncoding(unittest.TestCase):
    def test_unauthenticated_home_page_escapes_uid(self):
        with patch.object(main, "get_dropbox_tokens", return_value=None):
            response = asyncio.run(main.home(uid='user"123<script>'))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('href="/auth/dropbox?uid=user%22123%3Cscript%3E"', body)
            self.assertNotIn('href="/auth/dropbox?uid=user"123<script>"', body)

    def test_authenticated_home_page_escapes_user_info_and_folder_name(self):
        tokens = {
            "display_name": "<script>alert('name')</script>",
            "email": "evil\"@example.com",
        }
        settings = {
            "folder_name": 'Omi" onfocus="alert(1)"',
        }
        with patch.object(main, "get_dropbox_tokens", return_value=tokens), \
             patch.object(main, "get_user_settings", return_value=settings):
            response = asyncio.run(main.home(uid='user"123'))
            self.assertEqual(response.status_code, 200)
            body = response.body.decode()
            self.assertIn('&lt;script&gt;alert(&#x27;name&#x27;)&lt;/script&gt;', body)
            self.assertNotIn("<script>alert('name')</script>", body)
            self.assertIn('evil&quot;@example.com', body)
            self.assertIn('value="Omi&quot; onfocus=&quot;alert(1)&quot;"', body)
            self.assertIn('action="/settings?uid=user%22123"', body)
            self.assertIn('href="/disconnect?uid=user%22123"', body)

    def test_callback_error_reflected_xss_prevention(self):
        response = asyncio.run(
            main.auth_callback(error="access_denied", error_description='<script>alert("xss")</script>')
        )
        self.assertEqual(response.status_code, 400)
        body = response.body.decode()
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', body)
        self.assertNotIn('<script>alert("xss")</script>', body)

    def test_callback_token_exchange_error_escaped(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "<b>Invalid Grant</b>"

        with patch.object(main, "get_oauth_state", return_value="u123:state123"), \
             patch.object(main, "delete_oauth_state"), \
             patch("requests.post", return_value=mock_resp):
            response = asyncio.run(main.auth_callback(code="code123", state="u123:state123"))
            self.assertEqual(response.status_code, 400)
            body = response.body.decode()
            self.assertIn('&lt;b&gt;Invalid Grant&lt;/b&gt;', body)
            self.assertNotIn("<b>Invalid Grant</b>", body)

    def test_callback_exception_escaped(self):
        with patch.object(main, "get_oauth_state", return_value="u123:state123"), \
             patch.object(main, "delete_oauth_state"), \
             patch("requests.post", side_effect=Exception("<script>broken</script>")):
            response = asyncio.run(main.auth_callback(code="code123", state="u123:state123"))
            self.assertEqual(response.status_code, 500)
            body = response.body.decode()
            self.assertIn('&lt;script&gt;broken&lt;/script&gt;', body)
            self.assertNotIn("<script>broken</script>", body)

    def test_disconnect_redirect_quotes_uid(self):
        with patch.object(main, "delete_dropbox_tokens"):
            response = asyncio.run(main.disconnect(uid='user" 123&test=1'))
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers["location"], "/?uid=user%22%20123%26test%3D1")


if __name__ == "__main__":
    unittest.main()
