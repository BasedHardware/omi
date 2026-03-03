"""Tests for desktop update system (appcast XML, channel filtering, download endpoint)."""
import xml.etree.ElementTree as ET

import pytest

from routers.updates import (
    VALID_CHANNELS,
    _format_changelog_html,
    _generate_appcast_xml,
    _get_dmg_download_url,
    _get_sparkle_zip_download_url,
    _parse_changelog_to_changes,
    _parse_desktop_version,
    _xml_attr,
)


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

class TestChannelValidation:
    def test_valid_channels(self):
        assert "beta" in VALID_CHANNELS
        assert "stable" in VALID_CHANNELS

    def test_staging_not_valid(self):
        assert "staging" not in VALID_CHANNELS
