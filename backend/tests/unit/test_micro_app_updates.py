"""Hermetic tests for the catalog-driven public micro-app Sparkle feed."""

import xml.etree.ElementTree as ET

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routers import micro_app_updates as micro_app_router
from utils import micro_app_updates as micro_app_service

_test_app = FastAPI()
_test_app.include_router(micro_app_router.router)
_SPARKLE = {"sparkle": micro_app_service.SPARKLE_NAMESPACE}


def _release(
    *,
    tag="context-for-claude-v1.2.3",
    name="Context for Claude 1.2.3",
    prerelease=False,
    asset_name="ContextForClaude-1.2.3.zip",
    asset_url="https://github.com/BasedHardware/omi/releases/download/context-for-claude-v1.2.3/ContextForClaude-1.2.3.zip",
    signature="signed-context-artifact",
    body="Fixed a capture issue.",
    published_at="2026-08-01T12:00:00Z",
    metadata=None,
):
    release = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "published_at": published_at,
        "prerelease": prerelease,
        "draft": False,
        "assets": [],
    }
    if asset_name is not None:
        release["assets"] = [{"name": asset_name, "browser_download_url": asset_url}]
    if signature is not None:
        release["metadata"] = {"edSignature": signature}
    if metadata:
        release.setdefault("metadata", {}).update(metadata)
    return release


async def _get_feed(monkeypatch, releases, *, app_id="context-for-claude", channel="stable"):
    async def provider(config):
        assert config is micro_app_service.CONTEXT_FOR_CLAUDE
        return releases

    monkeypatch.setattr(micro_app_service, "fetch_micro_app_releases", provider)
    async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://testserver") as client:
        return await client.get(f"/v2/micro-apps/{app_id}/appcast.xml", params={"channel": channel})


@pytest.mark.asyncio
async def test_valid_sparkle_xml_contains_identity_metadata_and_signature(monkeypatch):
    response = await _get_feed(monkeypatch, [_release(metadata={"build": "42"})])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert response.headers["cache-control"] == "public, max-age=300"

    root = ET.fromstring(response.text)
    item = root.find("channel/item")
    assert item is not None
    assert item.findtext("title") == "Context for Claude 1.2.3"
    assert item.findtext("sparkle:version", namespaces=_SPARKLE) == "42"
    assert item.findtext("sparkle:shortVersionString", namespaces=_SPARKLE) == "1.2.3"
    assert item.findtext("pubDate") == "Sat, 01 Aug 2026 12:00:00 GMT"
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib[f"{{{micro_app_service.SPARKLE_NAMESPACE}}}edSignature"] == "signed-context-artifact"
    assert enclosure.attrib[f"{{{micro_app_service.SPARKLE_NAMESPACE}}}minimumSystemVersion"] == "14.4"
    assert item.findtext("sparkle:releaseNotesLink", namespaces=_SPARKLE) is None


@pytest.mark.asyncio
async def test_xml_escapes_release_values_and_cdata_terminator(monkeypatch):
    release = _release(
        name='Context & <Claude> "beta"',
        asset_url='https://example.com/ContextForClaude.zip?one=1&two="quoted"<x>',
        signature='sig&"<danger>',
        body='A <script>alert("x")</script> & a CDATA marker ]]>.',
    )
    release["html_url"] = "https://github.com/BasedHardware/omi/releases/tag/context-for-claude-v1.2.3?a=1&b=2"

    response = await _get_feed(monkeypatch, [release])

    assert response.status_code == 200
    root = ET.fromstring(response.text)
    item = root.find("channel/item")
    assert item is not None
    assert item.findtext("title") == 'Context & <Claude> "beta"'
    description = item.findtext("description") or ""
    assert "<script>" not in description
    assert "&lt;script&gt;" in description
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"] == 'https://example.com/ContextForClaude.zip?one=1&two="quoted"<x>'
    assert enclosure.attrib[f"{{{micro_app_service.SPARKLE_NAMESPACE}}}edSignature"] == 'sig&"<danger>'
    assert item.findtext("sparkle:releaseNotesLink", namespaces=_SPARKLE).endswith("a=1&b=2")


@pytest.mark.asyncio
async def test_channel_selection_is_strict_and_omits_desktop_identity(monkeypatch):
    releases = [
        _release(tag="context-for-claude-v1.2.3", name="stable", prerelease=False),
        _release(
            tag="context-for-claude-v1.3.0-beta.1",
            name="beta",
            prerelease=True,
            asset_name="ContextForClaude-1.3.0-beta.1.zip",
        ),
        _release(
            tag="v99.99.99+9999-macos",
            name="Omi Desktop",
            asset_name="Omi.zip",
            asset_url="https://example.com/Omi.zip",
        ),
    ]

    stable_response = await _get_feed(monkeypatch, releases, channel="stable")
    beta_response = await _get_feed(monkeypatch, releases, channel="beta")

    stable_root = ET.fromstring(stable_response.text)
    beta_root = ET.fromstring(beta_response.text)
    stable_items = stable_root.findall("channel/item")
    beta_items = beta_root.findall("channel/item")
    assert [item.findtext("title") for item in stable_items] == ["stable"]
    assert [item.findtext("title") for item in beta_items] == ["beta"]
    assert beta_items[0].findtext("sparkle:channel", namespaces=_SPARKLE) == "beta"
    assert stable_items[0].findtext("sparkle:channel", namespaces=_SPARKLE) is None
    assert "Omi Desktop" not in stable_response.text + beta_response.text


@pytest.mark.asyncio
async def test_unknown_app_fails_closed_without_calling_provider(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(micro_app_service, "fetch_micro_app_releases", provider)

    async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://testserver") as client:
        response = await client.get("/v2/micro-apps/omi-desktop/appcast.xml")

    assert response.status_code == 404
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_artifact_or_signature_returns_valid_empty_feed(monkeypatch):
    missing_signature = _release(signature=None)
    response = await _get_feed(monkeypatch, [missing_signature])
    root = ET.fromstring(response.text)
    assert response.status_code == 200
    assert root.findall("channel/item") == []

    missing_artifact = _release(asset_name="Omi.zip", signature="signed")
    response = await _get_feed(monkeypatch, [missing_artifact])
    root = ET.fromstring(response.text)
    assert response.status_code == 200
    assert root.findall("channel/item") == []


@pytest.mark.asyncio
async def test_provider_failure_is_not_cached_as_empty_feed(monkeypatch):
    async def provider(_config):
        raise RuntimeError("upstream details must not escape")

    monkeypatch.setattr(micro_app_service, "fetch_micro_app_releases", provider)
    async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://testserver") as client:
        response = await client.get("/v2/micro-apps/context-for-claude/appcast.xml")

    assert response.status_code == 503
    assert "upstream details" not in response.text
