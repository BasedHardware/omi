"""Tests for firmware endpoint GitHub releases pagination.

Verifies that get_omi_github_releases correctly paginates through pages
when a tag_filter is provided (firmware), and returns a single page when
no filter is provided (desktop). Also tests the cache-miss fix for empty lists.
"""

import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401

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

from routers.firmware import (
    get_omi_github_releases,
    FIRMWARE_TAG_PATTERN,
    MAX_PAGES,
    _parse_firmware_version,
    _find_candidate_releases,
)


def _make_release(tag_name, draft=False, published_at="2026-01-30T00:00:00Z"):
    return {"tag_name": tag_name, "draft": draft, "published_at": published_at}


def _desktop_releases(n):
    """Generate n desktop-style releases."""
    return [_make_release(f"v1.0.{i}+{i}-macos") for i in range(n)]


def _firmware_releases():
    """Generate a small set of firmware releases."""
    return [
        _make_release("Omi_CV1_v3.0.15"),
        _make_release("Omi_CV1_v3.0.14"),
        _make_release("Omi_DK2_v2.0.10"),
        _make_release("OmiGlass_v2.3.2"),
        _make_release("Friend_v1.0.4"),
    ]


class TestFirmwareTagPattern:
    """Verify FIRMWARE_TAG_PATTERN matches expected tags and rejects desktop tags."""

    @pytest.mark.parametrize(
        "tag",
        [
            "Omi_CV1_v3.0.15",
            "Omi_DK2_v2.0.10",
            "OmiGlass_v2.3.2",
            "OpenGlass_v1.0",
            "Friend_v1.0.4",
        ],
    )
    def test_matches_firmware_tags(self, tag):
        assert FIRMWARE_TAG_PATTERN.match(tag)

    @pytest.mark.parametrize(
        "tag",
        [
            "v1.0.77+464-macos-cm",
            "v0.6.4+6004-macos",
            "v1.0.524+614-desktop-auto",
            "pr-4440-cpu-profiling",
            "",
        ],
    )
    def test_rejects_non_firmware_tags(self, tag):
        assert not FIRMWARE_TAG_PATTERN.match(tag)


class TestPagination:
    """Test that pagination works correctly when firmware is buried past page 1."""

    @pytest.mark.asyncio
    async def test_paginates_to_find_firmware(self):
        """Firmware on page 2 is found when tag_filter is provided."""
        page1 = _desktop_releases(100)  # Full page of desktop releases
        page2 = _desktop_releases(50) + _firmware_releases()

        mock_response_page1 = MagicMock()
        mock_response_page1.status_code = 200
        mock_response_page1.json.return_value = page1

        mock_response_page2 = MagicMock()
        mock_response_page2.status_code = 200
        mock_response_page2.json.return_value = page2

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[mock_response_page1, mock_response_page2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', return_value=None), patch(
            'routers.firmware.set_generic_cache'
        ) as mock_set_cache, patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key", tag_filter=FIRMWARE_TAG_PATTERN)

        assert len(result) == 5
        tags = {r["tag_name"] for r in result}
        assert "Omi_CV1_v3.0.15" in tags
        assert "Omi_DK2_v2.0.10" in tags
        # Verify no desktop releases leaked through
        assert not any("macos" in r["tag_name"] for r in result)
        # Verify both short cache (5min) and last-known-good cache (24h)
        # were set on a successful non-empty fetch.
        cache_keys_set = [call.args[0] for call in mock_set_cache.call_args_list]
        assert "test_key" in cache_keys_set
        assert "test_key:lkg" in cache_keys_set
        assert mock_set_cache.call_count == 2

    @pytest.mark.asyncio
    async def test_no_pagination_without_filter(self):
        """Without tag_filter, only one page is fetched (desktop use case)."""
        page1 = _desktop_releases(100)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = page1

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', return_value=None), patch(
            'routers.firmware.set_generic_cache'
        ), patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        # Should return all 100 desktop releases unfiltered
        assert len(result) == 100
        # Should only have made 1 API call (no pagination)
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_pagination_safety_cap(self):
        """Pagination stops at MAX_PAGES even if no firmware is found."""
        full_page = _desktop_releases(100)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = full_page

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', return_value=None), patch(
            'routers.firmware.set_generic_cache'
        ), patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key", tag_filter=FIRMWARE_TAG_PATTERN)

        assert len(result) == 0
        assert mock_client.get.call_count == MAX_PAGES


class TestCacheBehavior:
    """Test cache hit/miss behavior."""

    @pytest.mark.asyncio
    async def test_cached_empty_list_is_cache_hit(self):
        """An empty list in cache should NOT trigger a re-fetch."""
        with patch('routers.firmware.get_generic_cache', return_value=[]) as mock_get:
            result = await get_omi_github_releases("test_key", tag_filter=FIRMWARE_TAG_PATTERN)

        assert result == []
        mock_get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_cache_none_triggers_fetch(self):
        """None from cache means cache miss — should fetch from GitHub."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', return_value=None), patch(
            'routers.firmware.set_generic_cache'
        ) as mock_set, patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        assert result == []
        # Empty fetch with no LKG fallback caches with the SHORT TTL (60s)
        # so the next request retries GitHub soon, instead of poisoning
        # the cache with empty for the full 5-minute success TTL.
        mock_set.assert_called_once_with("test_key", [], ttl=60)


class TestLastKnownGoodFallback:
    """When GitHub returns empty / errors, serve the previous good cache."""

    @pytest.mark.asyncio
    async def test_empty_fetch_falls_back_to_lkg(self):
        """If GitHub returns [] but we have an LKG, return the LKG instead."""
        lkg = _desktop_releases(3)

        # First call (short key) misses; second call (LKG key) hits.
        cache_calls = []

        def fake_get(key):
            cache_calls.append(key)
            return None if key == "test_key" else lkg

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # GitHub outage signature

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', side_effect=fake_get), patch(
            'routers.firmware.set_generic_cache'
        ) as mock_set, patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        assert result == lkg
        # Both keys were consulted
        assert "test_key" in cache_calls and "test_key:lkg" in cache_calls
        # LKG was re-cached under the short key with a short TTL so we
        # retry GitHub soon, but service stays up.
        mock_set.assert_called_once_with("test_key", lkg, ttl=60)

    @pytest.mark.asyncio
    async def test_500_response_falls_back_to_lkg(self):
        """If GitHub returns a non-200, fall back to LKG instead of raising 500."""
        lkg = _desktop_releases(2)

        def fake_get(key):
            return None if key == "test_key" else lkg

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', side_effect=fake_get), patch(
            'routers.firmware.set_generic_cache'
        ), patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        assert result == lkg

    @pytest.mark.asyncio
    async def test_exception_falls_back_to_lkg(self):
        """Network exception → LKG fallback (instead of bubbling)."""
        lkg = _desktop_releases(4)

        def fake_get(key):
            return None if key == "test_key" else lkg

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("connection reset"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', side_effect=fake_get), patch(
            'routers.firmware.set_generic_cache'
        ), patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        assert result == lkg

    @pytest.mark.asyncio
    async def test_successful_fetch_writes_both_caches(self):
        """Non-empty fetch refreshes both short cache (5min) and LKG (24h)."""
        releases = _desktop_releases(5)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = releases

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('routers.firmware.get_generic_cache', return_value=None), patch(
            'routers.firmware.set_generic_cache'
        ) as mock_set, patch('routers.firmware.httpx.AsyncClient', return_value=mock_client), patch.dict(
            'os.environ', {'GITHUB_TOKEN': 'test-token'}
        ):

            result = await get_omi_github_releases("test_key")

        assert result == releases
        ttl_by_key = {call.args[0]: call.kwargs.get("ttl") for call in mock_set.call_args_list}
        assert ttl_by_key["test_key"] == 300
        assert ttl_by_key["test_key:lkg"] == 86400


class TestParseFirmwareVersion:
    """`_parse_firmware_version` now returns None for unparseable input so callers can
    distinguish "unknown" from "very old". Treating unknown as (0,0,0) is what caused
    /v2/firmware/latest to recommend a stale legacy release to users with current
    firmware whose BLE characteristic read transiently failed."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("3.0.19", (3, 0, 19)),
            ("v3.0.19", (3, 0, 19)),
            ("V3.0.19", (3, 0, 19)),
            ("1.2", (1, 2, 0)),
            ("1", (1, 0, 0)),
            ("0.0.0", (0, 0, 0)),
        ],
    )
    def test_parses_valid_versions(self, value, expected):
        assert _parse_firmware_version(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "unknown",
            "Unknown",
            "abc",
            "1.x.0",
            "1..2",
        ],
    )
    def test_returns_none_for_invalid(self, value):
        assert _parse_firmware_version(value) is None


class TestFindCandidateReleasesGuardsAgainstBadMetadata:
    """Defense-in-depth: releases with garbled `release_firmware_version` in their body
    are skipped instead of crashing the comparison, and garbled `minimum_firmware_required`
    is treated as "no requirement" (matches the missing-key behavior).
    """

    @staticmethod
    def _release(tag, body, published_at="2026-01-30T00:00:00Z"):
        return {
            "tag_name": tag,
            "body": body,
            "draft": False,
            "prerelease": False,
            "published_at": published_at,
        }

    def test_skips_release_with_unparseable_release_firmware_version(self):
        releases = [
            self._release(
                "Omi_CV1_v3.0.19",
                "<!-- KEY_VALUE_START\nrelease_firmware_version:not-a-version\nKEY_VALUE_END -->",
            ),
            self._release(
                "Omi_CV1_v3.0.18",
                "<!-- KEY_VALUE_START\nrelease_firmware_version:3.0.18\nKEY_VALUE_END -->",
            ),
        ]
        candidates = _find_candidate_releases(releases, "Omi_CV1", (3, 0, 17))
        tags = [c["tag_name"] for c in candidates]
        assert tags == ["Omi_CV1_v3.0.18"]

    def test_treats_unparseable_min_req_as_unset(self):
        releases = [
            self._release(
                "Omi_CV1_v3.0.19",
                "<!-- KEY_VALUE_START\nrelease_firmware_version:3.0.19\nminimum_firmware_required:garbage\nKEY_VALUE_END -->",
            ),
        ]
        # User on 1.0.0 — would normally be blocked by minimum_firmware_required:3.0.6.
        # With garbled min_req, treat as no requirement (same as missing key).
        candidates = _find_candidate_releases(releases, "Omi_CV1", (1, 0, 0))
        assert len(candidates) == 1


class TestGetLatestVersionRejectsUnknownCurrent:
    """`/v2/firmware/latest` must refuse to recommend an upgrade when it can't trust
    the caller's reported current firmware. Without this, an empty / garbled
    firmware_revision matched every legacy release and surfaced stale upgrade
    prompts to up-to-date users."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("firmware_revision", ["", "unknown", "abc"])
    async def test_invalid_current_firmware_returns_400(self, firmware_revision):
        from routers.firmware import get_latest_version
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_latest_version(
                device_model="Omi CV 1",
                firmware_revision=firmware_revision,
                hardware_revision="1",
                manufacturer_name="Omi",
            )
        assert exc.value.status_code == 400
