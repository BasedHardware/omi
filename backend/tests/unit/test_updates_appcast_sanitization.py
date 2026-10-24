"""Unit tests for updates router appcast exception sanitization (CWE-209 mitigation).

Verifies that internal exceptions, GitHub release resolution errors, and raw
connection details during desktop appcast XML generation are masked and not
leaked in HTTP 500 response bodies, while preserving server-side logging.
"""

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

# Install hermetic test stubs for optional heavy external infrastructure
for _mod in ['google.cloud', 'google.cloud.firestore', 'redis', 'prometheus_client', 'typesense']:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import asyncio
from routers import updates as updates_routes


class TestUpdatesAppcastSanitization(unittest.TestCase):
    """Test suite ensuring sensitive exception details are masked in get_desktop_appcast_xml."""

    def test_appcast_generation_masks_internal_error_detail(self):
        """Ensure get_desktop_appcast_xml raises generic 500 without internal exception details."""
        sensitive_error = RuntimeError(
            "Connection refused to api.github.com:443: failed to resolve release tarball for "
            "/repos/BasedHardware/omi/releases/9921 with token ghp_SECRET_TOKEN_998877"
        )

        with patch.object(updates_routes, "_get_live_desktop_releases", new=AsyncMock(side_effect=sensitive_error)):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(updates_routes.get_desktop_appcast_xml(platform="macos", identity=None))

        exc = cm.exception
        self.assertEqual(exc.status_code, 500)
        self.assertEqual(exc.detail, "Failed to generate desktop appcast.")
        self.assertNotIn("api.github.com", exc.detail)
        self.assertNotIn("ghp_SECRET_TOKEN", exc.detail)
        self.assertNotIn("9921", exc.detail)

    def test_appcast_generation_masks_xml_serialization_error(self):
        """Ensure unexpected XML serialization or parsing failure detail is not leaked."""
        sample_releases = [
            {
                "channel": "stable",
                "release": {"body": "Release notes", "published_at": "2026-10-10T12:00:00Z"},
                "version_info": {"version": "1.0.0", "build": "100"},
                "metadata": {"changelog": []},
            }
        ]

        def failing_xml_generator(*args, **kwargs):
            raise ValueError("XML parsing failed: encoding invalid on /var/app/internal_secrets/appcast_sparkle.xml")

        with patch.object(updates_routes, "_get_live_desktop_releases", new=AsyncMock(return_value=sample_releases)), \
             patch.object(updates_routes, "_parse_changelog_to_changes", return_value="changes"), \
             patch.object(updates_routes, "_get_sparkle_zip_download_url", return_value="https://example.com/download.zip"), \
             patch.object(updates_routes, "_generate_appcast_xml", side_effect=failing_xml_generator):

            with self.assertRaises(HTTPException) as cm:
                asyncio.run(updates_routes.get_desktop_appcast_xml(platform="macos", identity=None))

        exc = cm.exception
        self.assertEqual(exc.status_code, 500)
        self.assertEqual(exc.detail, "Failed to generate desktop appcast.")
        self.assertNotIn("/var/app/internal_secrets", exc.detail)
        self.assertNotIn("appcast_sparkle.xml", exc.detail)

    def test_appcast_generation_preserves_not_found_http_exception(self):
        """Ensure standard 404 HTTPException propagates without being masked as 500."""
        with patch.object(updates_routes, "_get_live_desktop_releases", new=AsyncMock(return_value=[])):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(updates_routes.get_desktop_appcast_xml(platform="windows", identity=None))

        exc = cm.exception
        self.assertEqual(exc.status_code, 404)
        self.assertIn("No desktop releases found", exc.detail)


if __name__ == "__main__":
    unittest.main()
