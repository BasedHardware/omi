"""Tests for desktop update system (appcast XML, channel filtering, download endpoint)."""

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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
from database.desktop_update_policy import get_desktop_update_policy

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

    def test_two_component_version_macos(self):
        # Newer release tags omit the patch component (e.g. v11.0+11000-macos).
        result = _parse_desktop_version("v11.0+11000-macos")
        assert result is not None
        assert result["major"] == "11"
        assert result["minor"] == "0"
        assert result["patch"] == "0"
        assert result["build"] == "11000"
        assert result["version"] == "11.0.0+11000"

    def test_two_component_version_desktop_cm(self):
        result = _parse_desktop_version("v11.3+11003-desktop-cm")
        assert result is not None
        assert result["version"] == "11.3.0+11003"
        assert result["build"] == "11003"

    # --- Regression anchor for issue #5285 ---
    #
    # https://github.com/BasedHardware/omi/issues/5285 — the appcast endpoint
    # silently dropped newer 2-component release tags (e.g. ``v11.0+11000-macos``)
    # because the patch group was mandatory, breaking desktop auto-updates. The
    # fix made the patch component optional (defaulting to "0"). These cases pin
    # that behavior so the regex can never regress to requiring a patch component
    # while still accepting the legacy 3-component form.
    @pytest.mark.parametrize(
        "tag, expected_version, expected_patch",
        [
            # The exact 2-component tags called out in issue #5285 (patch omitted).
            ("v11.0+11000-macos", "11.0.0+11000", "0"),
            ("v11.3+11003-macos", "11.3.0+11003", "0"),
            # The legacy 3-component form must keep parsing (guard vs. over-correction).
            ("v1.0.77+464-desktop-cm", "1.0.77+464", "77"),
        ],
    )
    def test_issue_5285_supported_tags_parse(self, tag, expected_version, expected_patch):
        result = _parse_desktop_version(tag)
        assert result is not None, f"expected {tag!r} to parse (issue #5285)"
        assert result["version"] == expected_version
        assert result["patch"] == expected_patch

    @pytest.mark.parametrize(
        "tag",
        [
            "v11+11000-macos",  # missing minor component
            "v11.0-macos",  # missing +build component
            "v11.0+11000",  # missing platform suffix
            "v11.0+11000-ios",  # unsupported platform
            "not-a-version",
            "",
        ],
    )
    def test_issue_5285_malformed_tags_return_none(self, tag):
        # Making patch optional must not loosen the rest of the grammar.
        assert _parse_desktop_version(tag) is None


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


# --- _get_legacy_live_desktop_releases ---


class TestGetLiveDesktopReleases:
    @pytest.mark.asyncio
    async def test_empty_releases(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=[]) as mock_releases:
            result = await get_releases("macos")
        assert result == []
        _, kwargs = mock_releases.await_args
        assert kwargs["tag_filter"].match("v0.12.0+12000-macos")

    @pytest.mark.asyncio
    async def test_filters_non_desktop_tags(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-ios", body_kv={"isLive": "true"}),
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, assets=[_zip_asset()]),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert len(result) == 1
        assert result[0]["version_info"]["build"] == "100"


def _pointer_release(channel="beta", build=200):
    return {
        "pointer": {
            "platform": "macos",
            "channel": channel,
            "release_id": f"v1.0.0+{build}-macos",
            "generation": 1,
            "updated_at": "2026-03-01T00:00:00Z",
        },
        "manifest": {
            "release_id": f"v1.0.0+{build}-macos",
            "platform": "macos",
            "version": f"1.0.0+{build}",
            "build_number": build,
            "zip_url": f"https://example.com/{build}/Omi.zip",
            "dmg_url": f"https://example.com/{build}/Omi.dmg",
            "ed_signature": "signature",
            "published_at": "2026-03-01T00:00:00Z",
            "changelog": ["Qualified release"],
            "mandatory": False,
            "source_sha": "a" * 40,
            "zip_sha256": None,
            "dmg_sha256": None,
            "qualification": {"tier": "T2", "passed": True},
        },
    }


class TestResolveDesktopReleases:
    @pytest.mark.asyncio
    async def test_explicit_pointers_are_primary(self):
        from routers.updates import _get_live_desktop_releases

        def resolve(_platform, channel):
            return _pointer_release(channel), "pointer", None

        with (
            patch("routers.updates.resolve_pointer_release", side_effect=resolve),
            patch("routers.updates.random.random", return_value=1.0),
            patch("routers.updates._get_legacy_live_desktop_releases", new_callable=AsyncMock) as legacy,
        ):
            result = await _get_live_desktop_releases("macos")

        assert {entry["channel"] for entry in result} == {"stable", "beta"}
        assert all(entry["source"] == "pointer" for entry in result)
        legacy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_pointer_falls_back_only_to_same_legacy_channel(self):
        from routers.updates import _get_live_desktop_releases

        def resolve(_platform, channel):
            if channel == "beta":
                return _pointer_release(channel), "pointer", None
            return None, "none", "pointer_missing"

        legacy_stable = {
            "channel": "stable",
            "release": {"published_at": "2026-02-01T00:00:00Z", "assets": [_zip_asset(), _dmg_asset()]},
            "version_info": {"version": "0.12.0+12000", "build": "12000"},
            "metadata": {"edSignature": "legacy"},
        }
        with (
            patch("routers.updates.resolve_pointer_release", side_effect=resolve),
            patch(
                "routers.updates._get_legacy_live_desktop_releases",
                new_callable=AsyncMock,
                return_value=[legacy_stable],
            ),
        ):
            result = await _get_live_desktop_releases("macos")

        by_channel = {entry["channel"]: entry for entry in result}
        assert by_channel["stable"]["source"] == "legacy_fallback"
        assert by_channel["beta"]["source"] == "pointer"

    @pytest.mark.asyncio
    async def test_validated_lkg_precedes_legacy(self):
        from routers.updates import _get_live_desktop_releases

        def resolve(_platform, channel):
            return _pointer_release(channel), "pointer_lkg", "pointer_invalid"

        with (
            patch("routers.updates.resolve_pointer_release", side_effect=resolve),
            patch("routers.updates.random.random", return_value=1.0),
            patch("routers.updates._get_legacy_live_desktop_releases", new_callable=AsyncMock) as legacy,
        ):
            result = await _get_live_desktop_releases("macos")

        assert all(entry["source"] == "pointer_lkg" for entry in result)
        legacy.assert_not_awaited()


class TestLegacyDesktopReleaseFiltering:
    @pytest.mark.asyncio
    async def test_filters_draft_releases(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, draft=True),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_not_live(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "false"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result == []

    @pytest.mark.asyncio
    async def test_channel_defaults_to_beta(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result[0]["channel"] == "beta"

    @pytest.mark.asyncio
    async def test_invalid_channel_falls_back_to_beta(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true", "channel": "nightly"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result[0]["channel"] == "beta"

    @pytest.mark.asyncio
    async def test_stable_channel_preserved(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true", "channel": "stable"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result[0]["channel"] == "stable"

    @pytest.mark.asyncio
    async def test_sorted_newest_first(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-macos", body_kv={"isLive": "true"}, published_at="2026-01-01T00:00:00Z"),
            _make_github_release("v2.0.0+200-macos", body_kv={"isLive": "true"}, published_at="2026-03-01T00:00:00Z"),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
        assert result[0]["version_info"]["build"] == "200"
        assert result[1]["version_info"]["build"] == "100"

    @pytest.mark.asyncio
    async def test_desktop_cm_tag_accepted(self):
        from routers.updates import _get_legacy_live_desktop_releases as get_releases

        releases = [
            _make_github_release("v1.0.0+100-desktop-cm", body_kv={"isLive": "true"}),
        ]
        with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
            result = await get_releases("macos")
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
                "release": {
                    "published_at": "2026-03-02T00:00:00Z",
                    "body": "",
                    "assets": [_zip_asset("https://a.com/Omi.zip")],
                },
                "version_info": {"version": "2.0.0+200", "build": "200"},
                "metadata": {},
            },
            {
                "channel": "beta",
                "release": {
                    "published_at": "2026-03-01T00:00:00Z",
                    "body": "",
                    "assets": [_zip_asset("https://b.com/Omi.zip")],
                },
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
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "release": {"assets": [_dmg_asset("https://example.com/Omi-stable.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=stable")
        assert resp.status_code == 200
        assert "https://example.com/Omi-stable.dmg" in resp.text

    @pytest.mark.asyncio
    async def test_404_no_releases(self):
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=[]):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stable_never_falls_back_to_beta(self):
        mock_releases = [
            {
                "channel": "beta",
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "release": {"assets": [_dmg_asset("https://example.com/beta.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=stable")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_beta_never_falls_back_to_stable(self):
        mock_releases = [
            {
                "channel": "stable",
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "release": {"assets": [_dmg_asset("https://example.com/stable.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=beta")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_beta_uses_explicit_beta_release(self):
        mock_releases = [
            {
                "channel": "stable",
                "version_info": {"version": "2.0.0+200", "build": "200"},
                "release": {"assets": [_dmg_asset("https://example.com/latest.dmg")]},
            },
            {
                "channel": "beta",
                "version_info": {"version": "1.0.0+100", "build": "100"},
                "release": {"assets": [_dmg_asset("https://example.com/older-beta.dmg")]},
            },
        ]
        with patch("routers.updates._get_live_desktop_releases", new_callable=AsyncMock, return_value=mock_releases):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/download/latest?channel=beta")
        assert resp.status_code == 200
        assert "https://example.com/older-beta.dmg" in resp.text

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
        # Live caches are cleared; last-known-good entries remain available.
        cleared_keys = {call.args[0] for call in mock_delete.call_args_list}
        assert cleared_keys == {
            "github_releases_desktop",
            "desktop_update_pointer:macos:stable",
            "desktop_update_pointer:macos:beta",
            "desktop_update_pointer:windows:stable",
            "desktop_update_pointer:windows:beta",
            "desktop_update_pointer:linux:stable",
            "desktop_update_pointer:linux:beta",
        }

    @pytest.mark.asyncio
    async def test_missing_header_returns_422(self):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.post("/v2/desktop/clear-cache")
        assert resp.status_code == 422


class TestDesktopUpdateAdminEndpoints:
    @pytest.mark.asyncio
    async def test_registers_immutable_manifest(self):
        payload = _pointer_release()["manifest"]
        with (
            patch.dict("os.environ", {"ADMIN_KEY": "real-secret"}),
            patch("routers.updates.register_release_manifest", return_value=payload) as register,
        ):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.post(
                    "/v2/desktop/releases",
                    headers={"secret-key": "real-secret"},
                    json=payload,
                )

        assert resp.status_code == 201
        assert resp.json()["manifest"]["release_id"] == payload["release_id"]
        register.assert_called_once()

    @pytest.mark.asyncio
    async def test_manifest_mutation_conflict_is_reported(self):
        payload = _pointer_release()["manifest"]
        with (
            patch.dict("os.environ", {"ADMIN_KEY": "real-secret"}),
            patch("routers.updates.register_release_manifest", side_effect=ValueError("immutable metadata")),
        ):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.post(
                    "/v2/desktop/releases",
                    headers={"secret-key": "real-secret"},
                    json=payload,
                )

        assert resp.status_code == 409
        assert "immutable" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_promotes_pointer_and_clears_only_live_pointer_cache(self):
        pointer = {
            "platform": "macos",
            "channel": "beta",
            "release_id": "v1.0.0+200-macos",
            "generation": 2,
        }
        with (
            patch.dict("os.environ", {"ADMIN_KEY": "real-secret"}),
            patch("routers.updates.promote_channel", return_value=pointer) as promote,
            patch("routers.updates.delete_generic_cache") as delete_cache,
        ):
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.post(
                    "/v2/desktop/channels/promote",
                    headers={"secret-key": "real-secret"},
                    json={
                        "platform": "macos",
                        "channel": "beta",
                        "release_id": "v1.0.0+200-macos",
                        "expected_generation": 1,
                    },
                )

        assert resp.status_code == 200
        promote.assert_called_once_with("macos", "beta", "v1.0.0+200-macos", expected_generation=1)
        delete_cache.assert_called_once_with("desktop_update_pointer:macos:beta")


# --- Update policy endpoint ---


class TestDesktopUpdatePolicyEndpoint:
    @pytest.mark.asyncio
    async def test_returns_policy_for_current_build(self):
        policy = {
            "id": "force-legacy-4xx",
            "active": True,
            "severity": "required",
            "maximum_build_number": 11507,
            "latest_build_number": 11590,
            "title": "Update required",
            "message": "Install the latest Omi desktop app.",
            "cta_text": "Download latest",
            "download_url": "https://example.com/Omi.dmg",
            "can_dismiss": False,
        }
        with patch("routers.updates.get_desktop_update_policy", return_value=policy) as mock_policy:
            async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
                resp = await client.get("/v2/desktop/update-policy?platform=macos&current_build=11400")

        assert resp.status_code == 200
        assert resp.json()["id"] == "force-legacy-4xx"
        mock_policy.assert_called_once_with(current_build=11400, platform="macos")

    @pytest.mark.asyncio
    async def test_rejects_invalid_platform(self):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            resp = await client.get("/v2/desktop/update-policy?platform=ios")
        assert resp.status_code == 422


class TestDesktopUpdatePolicyDatabase:
    def _mock_doc(self, exists=True, data=None):
        doc = MagicMock()
        doc.exists = exists
        doc.to_dict.return_value = data or {}
        return doc

    def test_missing_doc_returns_inactive_default(self):
        doc = self._mock_doc(exists=False)
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        policy = get_desktop_update_policy(current_build=11400, firestore_client=mock_db)

        assert policy["active"] is False
        assert policy["severity"] == "none"
        assert policy["download_url"].endswith("/v2/desktop/download/latest?channel=stable")

    def test_required_policy_applies_through_maximum_build(self):
        doc = self._mock_doc(
            data={
                "id": "force-old-desktop",
                "active": True,
                "severity": "required",
                "maximum_build_number": 11507,
                "title": "Update required",
                "can_dismiss": False,
            }
        )
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        policy = get_desktop_update_policy(current_build=11507, firestore_client=mock_db)

        assert policy["id"] == "force-old-desktop"
        assert policy["active"] is True
        assert policy["severity"] == "required"
        assert policy["can_dismiss"] is False

    def test_policy_suppressed_above_maximum_build(self):
        doc = self._mock_doc(data={"active": True, "severity": "required", "maximum_build_number": 11507})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        policy = get_desktop_update_policy(current_build=11508, firestore_client=mock_db)

        assert policy["active"] is False
        assert policy["severity"] == "none"

    def test_policy_accepts_legacy_minimum_build_alias(self):
        doc = self._mock_doc(data={"active": True, "severity": "required", "minimum_build_number": 11507})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        policy = get_desktop_update_policy(current_build=11507, firestore_client=mock_db)

        assert policy["active"] is True
        assert policy["maximum_build_number"] == 11507
        assert "minimum_build_number" not in policy

    def test_policy_suppressed_for_other_platforms(self):
        doc = self._mock_doc(data={"active": True, "severity": "banner", "platforms": ["windows"]})
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        policy = get_desktop_update_policy(current_build=11400, platform="macos", firestore_client=mock_db)

        assert policy["active"] is False
