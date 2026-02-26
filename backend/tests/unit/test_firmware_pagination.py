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

from routers.firmware import get_omi_github_releases, FIRMWARE_TAG_PATTERN, MAX_PAGES


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
        # Verify cache was set
        mock_set_cache.assert_called_once()

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
        mock_set.assert_called_once_with("test_key", [], ttl=300)
