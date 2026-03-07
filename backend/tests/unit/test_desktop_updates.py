"""Tests for desktop update system (appcast XML, channel filtering, download endpoint)."""
import sys
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Stub heavy dependencies before importing the module under test
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('firebase_admin.messaging', MagicMock())
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())
sys.modules.setdefault('google.auth', MagicMock())
sys.modules.setdefault('google.auth.transport.requests', MagicMock())

from fastapi import FastAPI

from routers.updates import (
    VALID_CHANNELS,
    _format_changelog_html,
    _generate_appcast_xml,
    _get_dmg_download_url,
    _get_sparkle_zip_download_url,
    _parse_changelog_to_changes,
    _parse_desktop_version,
    _xml_attr,
    router as updates_router,
)

# Minimal test app mounting only the updates router
_test_app = FastAPI()
_test_app.include_router(updates_router)


# --- _parse_desktop_version ---

class TestParseDesktopVersion:
    def test_standard_macos_tag(self):
        result = _parse_desktop_version("v1.0.77+464-macos")
        assert result is not None
        assert result["version"] == "1.0.77+464"
        assert result["build"] == "464"

    def test_desktop_cm_tag(self):
        result = _parse_desktop_version("v0.11.45+11045-desktop-cm")
        assert result is not None
        assert result["major"] == "0"
        assert result["minor"] == "11"
        assert result["patch"] == "45"

    def test_macos_auto_tag(self):
        result = _parse_desktop_version("v1.2.3+100-macos-auto")
        assert result is not None
        assert result["version"] == "1.2.3+100"

    def test_desktop_auto_tag(self):
        result = _parse_desktop_version("v1.2.3+100-desktop-auto")
        assert result is not None

    def test_invalid_tag(self):
        assert _parse_desktop_version("v1.0.0-ios") is None
        assert _parse_desktop_version("not-a-version") is None
        assert _parse_desktop_version("") is None

    def test_no_v_prefix(self):
        result = _parse_desktop_version("1.0.0+100-macos")
        assert result is not None


# --- _parse_changelog_to_changes ---

class TestParseChangelog:
    def test_structured_changelog(self):
        changes = _parse_changelog_to_changes(["Fixed a crash on startup", "Added dark mode"], "")
        assert len(changes) == 2
        assert changes[0]["type"] == "fix"
        assert changes[1]["type"] == "feature"

    def test_whats_changed_fallback(self):
        body = "## What's Changed\n* Fixed login bug by @user\n* Improved performance\n\n## New Contributors"
        changes = _parse_changelog_to_changes([], body)
        assert len(changes) == 2
        assert changes[0]["type"] == "fix"
        assert changes[1]["type"] == "improvement"

    def test_default_fallback(self):
        changes = _parse_changelog_to_changes([], "")
        assert len(changes) == 1
        assert changes[0]["message"] == "New version available"

    def test_empty_items_skipped(self):
        changes = _parse_changelog_to_changes(["", "  ", "Real change"], "")
        assert len(changes) == 1


# --- _xml_attr ---

class TestXmlAttr:
    def test_escapes_quotes(self):
        assert '&quot;' in _xml_attr('value with "quotes"')

    def test_escapes_ampersand(self):
        assert '&amp;' in _xml_attr('a&b')

    def test_escapes_angle_brackets(self):
        result = _xml_attr('<script>')
        assert '<' not in result or '&lt;' in result


# --- _generate_appcast_xml ---

class TestGenerateAppcastXml:
    def _make_item(self, channel="beta", version="1.0.0+100", url="https://example.com/Omi.zip"):
        return {
            "version": version,
            "shortVersion": "100",
            "changes": [{"type": "feature", "message": "New feature"}],
            "date": "2026-03-01T00:00:00Z",
            "mandatory": False,
            "url": url,
            "platform": "macos",
            "edSignature": "abc123",
            "channel": channel,
        }

    def test_beta_gets_channel_tag(self):
        xml = _generate_appcast_xml([self._make_item(channel="beta")], "macos")
        assert "<sparkle:channel>beta</sparkle:channel>" in xml

    def test_stable_has_no_channel_tag(self):
        xml = _generate_appcast_xml([self._make_item(channel="stable")], "macos")
        assert "<sparkle:channel>" not in xml

    def test_mandatory_gets_critical_update(self):
        item = self._make_item()
        item["mandatory"] = True
        xml = _generate_appcast_xml([item], "macos")
        assert "<sparkle:criticalUpdate />" in xml

    def test_missing_url_skipped(self):
        xml = _generate_appcast_xml([self._make_item(url="")], "macos")
        assert "<item>" not in xml

    def test_valid_xml_output(self):
        xml = _generate_appcast_xml([self._make_item()], "macos")
        # Should parse without error
        ET.fromstring(xml)

    def test_cdata_safety(self):
        item = self._make_item()
        item["changes"] = [{"type": "feature", "message": "Contains ]]> sequence"}]
        xml = _generate_appcast_xml([item], "macos")
        # Should still be valid XML
        ET.fromstring(xml)

    def test_quotes_in_signature(self):
        item = self._make_item()
        item["edSignature"] = 'sig"with"quotes'
        xml = _generate_appcast_xml([item], "macos")
        ET.fromstring(xml)

    def test_both_channels_in_feed(self):
        items = [self._make_item(channel="beta"), self._make_item(channel="stable", version="0.9.0+90")]
        xml = _generate_appcast_xml(items, "macos")
        assert xml.count("<item>") == 2
        assert "<sparkle:channel>beta</sparkle:channel>" in xml


# --- Asset URL helpers ---

class TestAssetHelpers:
    def test_sparkle_zip_found(self):
        release = {"assets": [{"name": "Omi.zip", "browser_download_url": "https://example.com/Omi.zip"}]}
        assert _get_sparkle_zip_download_url(release) == "https://example.com/Omi.zip"

    def test_sparkle_zip_missing(self):
        release = {"assets": [{"name": "other.zip", "browser_download_url": "https://example.com/other.zip"}]}
        assert _get_sparkle_zip_download_url(release) is None

    def test_dmg_found(self):
        release = {"assets": [{"name": "Omi Beta.dmg", "browser_download_url": "https://example.com/Omi.dmg"}]}
        assert _get_dmg_download_url(release) == "https://example.com/Omi.dmg"

    def test_dmg_missing(self):
        release = {"assets": [{"name": "Omi.zip", "browser_download_url": "https://example.com/Omi.zip"}]}
        assert _get_dmg_download_url(release) is None

    def test_empty_assets(self):
        assert _get_sparkle_zip_download_url({}) is None
        assert _get_dmg_download_url({}) is None


# --- Channel validation ---

class TestFormatChangelogHtml:
    def test_empty_changes(self):
        html = _format_changelog_html([])
        assert html == "<p>Bug fixes and improvements</p>"

    def test_feature_icon(self):
        html = _format_changelog_html([{"type": "feature", "message": "New thing"}])
        assert "&#10024;" in html
        assert "New thing" in html

    def test_fix_icon(self):
        html = _format_changelog_html([{"type": "fix", "message": "Fixed crash"}])
        assert "&#128027;" in html

    def test_html_escaping_in_message(self):
        html = _format_changelog_html([{"type": "feature", "message": "<script>alert(1)</script>"}])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# --- Channel validation ---

class TestChannelValidation:
    def test_valid_channels(self):
        assert "beta" in VALID_CHANNELS
        assert "stable" in VALID_CHANNELS

    def test_staging_not_valid(self):
        assert "staging" not in VALID_CHANNELS


# --- Fixtures for endpoint tests ---

def _make_github_release(tag, body_kv=None, assets=None, published_at="2026-03-01T00:00:00Z", draft=False):
    """Build a mock GitHub release dict."""
    body = ""
    if body_kv:
        lines = "\n".join(f"{k}: {v}" for k, v in body_kv.items())
        body = f"<!-- KEY_VALUE_START\n{lines}\nKEY_VALUE_END -->"
    return {
        "tag_name": tag,
        "draft": draft,
        "published_at": published_at,
        "body": body,
        "assets": assets or [],
    }


def _zip_asset(url="https://example.com/Omi.zip"):
    return {"name": "Omi.zip", "browser_download_url": url}


def _dmg_asset(url="https://example.com/Omi.dmg"):
    return {"name": "Omi Beta.dmg", "browser_download_url": url}


# --- _get_live_desktop_releases ---

class TestGetLiveDesktopReleases:
    @pytest.mark.asyncio
    async def test_empty_releases(self):
        from routers.updates import _get_live_desktop_releases

        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=[]):
            result = await _get_live_desktop_releases("macos")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_non_desktop_tags(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-ios", body_kv={"isLive": "true"}),
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, assets=[_zip_asset()]),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert len(result) == 1
        assert result[0]["version_info"]["build"] == "100"

    @pytest.mark.asyncio
    async def test_filters_draft_releases(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, draft=True),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_not_live(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "false"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result == []

    @pytest.mark.asyncio
    async def test_channel_defaults_to_beta(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result[0]["channel"] == "beta"

    @pytest.mark.asyncio
    async def test_invalid_channel_falls_back_to_beta(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true", "channel": "nightly"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result[0]["channel"] == "beta"

    @pytest.mark.asyncio
    async def test_stable_channel_preserved(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true", "channel": "stable"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result[0]["channel"] == "stable"

    @pytest.mark.asyncio
    async def test_sorted_newest_first(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, published_at="2026-01-01T00:00:00Z"),
            _make_github_release("v2.0.0+200-macos", body_kv={"isLive": "true"}, published_at="2026-03-01T00:00:00Z"),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert result[0]["version_info"]["build"] == "200"
        assert result[1]["version_info"]["build"] == "100"

    @pytest.mark.asyncio
    async def test_desktop_cm_tag_accepted(self):
        from routers.updates import _get_live_desktop_releases

        releases = [
            _make_github_release("v1.0.0+100-desktop-cm", body_kv={"isLive": "true"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await _get_live_desktop_releases("macos")
        assert len(result) == 1


# --- Appcast XML endpoint ---

class TestAppcastEndpoint:
    @pytest.mark.asyncio
    async def test_returns_xml_with_items(self):
        mock_releases = [
            {
                "channel": "beta",
                "release": {
                    "published_at": "2026-03-01T00:00:00Z",
                    "body": "",
                    "assets": [_zip_asset()],
                },
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "metadata": {"edSignature": "sig123"},
            }
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/appcast.xml")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        assert "<item>" in resp.text
        assert "sparkle:channel>beta<" in resp.text

    @pytest.mark.asyncio
    async def test_404_when_no_releases(self):
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/appcast.xml")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deduplicates_by_channel(self):
        mock_releases = [
            {
                "channel": "beta",
                "release": {"published_at": "2026-03-02T00:00:00Z", "body": "", "assets": [_zip_asset("https://a.com/Omi.zip")]},
                "version_info": {"version": "2.0.0+200", "build": "200"},
                "metadata": {},
            },
            {
                "channel": "beta",
                "release": {"published_at": "2026-03-01T00:00:00Z", "body": "", "assets": [_zip_asset("https://b.com/Omi.zip")]},
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "metadata": {},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/appcast.xml")
        assert resp.status_code == 200
        assert resp.text.count("<item>") == 1

    @pytest.mark.asyncio
    async def test_skips_release_without_zip(self):
        mock_releases = [
            {
                "channel": "beta",
                "release": {"published_at": "2026-03-01T00:00:00Z", "body": "", "assets": [_dmg_asset()]},
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "metadata": {},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/appcast.xml")
        assert resp.status_code == 200
        assert "<item>" not in resp.text

    @pytest.mark.asyncio
    async def test_cache_control_header(self):
        mock_releases = [
            {
                "channel": "stable",
                "release": {"published_at": "2026-03-01T00:00:00Z", "body": "", "assets": [_zip_asset()]},
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "metadata": {},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/appcast.xml")
        assert resp.headers.get("cache-control") == "max-age=300"


# --- Download endpoint ---

class TestDownloadEndpoint:
    @pytest.mark.asyncio
    async def test_redirects_to_dmg(self):
        mock_releases = [
            {
                "channel": "stable",
                "release": {"assets": [_dmg_asset("https://example.com/Omi-stable.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test", follow_redirects=False) as client:
                resp = await client.get("/v2/desktop/download/latest?channel=stable")
        assert resp.status_code == 302
        assert resp.headers["location"] == "https://example.com/Omi-stable.dmg"

    @pytest.mark.asyncio
    async def test_404_no_releases(self):
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stable_fallback_to_beta(self):
        mock_releases = [
            {
                "channel": "beta",
                "release": {"assets": [_dmg_asset("https://example.com/beta.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test", follow_redirects=False) as client:
                resp = await client.get("/v2/desktop/download/latest?channel=stable")
        assert resp.status_code == 302
        assert "beta.dmg" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_beta_no_fallback(self):
        mock_releases = [
            {
                "channel": "stable",
                "release": {"assets": [_dmg_asset("https://example.com/stable.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=beta")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_when_no_dmg_asset(self):
        mock_releases = [
            {
                "channel": "stable",
                "release": {"assets": [_zip_asset()]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=stable")
        # Fallback loop also finds no DMG, so 404
        assert resp.status_code == 404


# --- Clear cache endpoint ---

class TestClearCacheEndpoint:
    @pytest.mark.asyncio
    async def test_forbidden_without_valid_key(self):
        with patch.dict("os.environ", {"ADMIN_KEY": "real-secret"}):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.post("/v2/desktop/clear-cache", headers={"secret-key": "wrong-key"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_success_with_valid_key(self):
        with (
            patch.dict("os.environ", {"ADMIN_KEY": "real-secret"}),
            patch("routers.updates.delete_generic_cache") as mock_delete,
        ):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.post("/v2/desktop/clear-cache", headers={"secret-key": "real-secret"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_delete.assert_called_once_with("github_releases_desktop")

    @pytest.mark.asyncio
    async def test_missing_header_returns_422(self):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.post("/v2/desktop/clear-cache")
        assert resp.status_code == 422
