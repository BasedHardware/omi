"""
Unit tests for omi-notion-app security, UID sanitization, and XSS prevention.
"""

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

import main


class NotionSecuritySanitizationTests(unittest.TestCase):
    """Verify UID validation, HTML escaping, and XSS prevention in Notion plugin."""

    def test_sanitize_uid_valid(self):
        self.assertEqual(main._sanitize_uid("test_user_123"), "test_user_123")
        self.assertEqual(main._sanitize_uid("user-abc-99"), "user-abc-99")
        self.assertEqual(main._sanitize_uid("123456789"), "123456789")
        self.assertEqual(main._sanitize_uid("a" * 128), "a" * 128)

    def test_sanitize_uid_invalid_and_injection_payloads(self):
        self.assertIsNone(main._sanitize_uid(""))
        self.assertIsNone(main._sanitize_uid(None))
        self.assertIsNone(main._sanitize_uid("<script>alert(1)</script>"))
        self.assertIsNone(main._sanitize_uid('"><script src=//evil.com/x.js>'))
        self.assertIsNone(main._sanitize_uid("javascript:alert(1)"))
        self.assertIsNone(main._sanitize_uid("../../etc/passwd"))
        self.assertIsNone(main._sanitize_uid("user name with spaces"))
        self.assertIsNone(main._sanitize_uid("a" * 129))

    def test_notion_auth_rejects_malformed_uid(self):
        import asyncio

        with self.assertRaises(HTTPException) as cm:
            asyncio.run(main.notion_auth(uid='"><script>alert(1)</script>'))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "Invalid user ID format")

    def test_setup_returns_false_for_malformed_uid(self):
        import asyncio

        res = asyncio.run(main.check_setup(uid='"><script>alert(1)</script>'))
        self.assertEqual(res, {"is_setup_completed": False})

    def test_disconnect_handles_malformed_uid_gracefully(self):
        import asyncio

        res = asyncio.run(main.disconnect(uid='"><script>alert(1)</script>'))
        self.assertEqual(res.status_code, 307)
        self.assertEqual(res.headers["location"], "/")

    def test_root_escapes_uid_and_neutralizes_xss(self):
        import asyncio

        # Valid UID renders escaped link
        with patch.object(main, "get_notion_tokens", return_value=None):
            res = asyncio.run(main.root(uid="valid-user-123"))
            self.assertIsInstance(res, HTMLResponse)
            self.assertIn("/auth/notion?uid=valid-user-123", res.body.decode("utf-8"))

        # Malformed / XSS payload UID returns default metadata JSON without rendering HTML
        res_xss = asyncio.run(main.root(uid='"><script>alert(1)</script>'))
        self.assertIsInstance(res_xss, dict)
        self.assertEqual(res_xss["app"], "Notion Omi Integration")


if __name__ == "__main__":
    unittest.main()
