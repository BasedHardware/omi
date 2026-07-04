"""GET /v2/desktop/whats-new: a JSON "what's new" changelog feed for the desktop app.

The backend already derives desktop release notes from GitHub releases but only exposes them as
Sparkle appcast XML (for the auto-updater). This adds a JSON feed an in-app "What's New" screen can
consume (issue #3474, milestone #10). It reuses _get_live_desktop_releases (same isLive/tag gating
as the appcast) and _parse_changelog_to_changes, and returns 200 with an empty list when nothing is
newer so the client can render "you're up to date".

Test isolation: routers.updates imports cleanly; the pure filter/mapping helpers are tested directly
and the async endpoint is driven via asyncio.run with get_omi_github_releases patched (no network).
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import asyncio
from unittest.mock import AsyncMock, patch

import routers.updates as updates


def _entry(
    build, channel="stable", version="1.0.0", changelog=None, mandatory=False, published_at="2026-01-01T00:00:00Z"
):
    """A live-release entry in the shape _get_live_desktop_releases yields."""
    return {
        "release": {"published_at": published_at, "body": ""},
        "version_info": {"version": version, "build": str(build)},
        "metadata": {"changelog": changelog or [], "mandatory": "true" if mandatory else "false"},
        "channel": channel,
    }


# --- pure helpers ---


def test_release_entry_shape():
    item = updates._release_entry_to_whats_new(
        _entry(464, "stable", version="1.0.77", changelog=["Fixed X"], mandatory=True)
    )
    assert item["version"] == "1.0.77"
    assert item["build"] == "464"
    assert item["mandatory"] is True
    assert item["channel"] == "stable"
    assert isinstance(item["changes"], list)


def test_filter_stable_excludes_beta():
    entries = [_entry(300, "beta"), _entry(200, "stable"), _entry(100, "beta")]
    assert [i["build"] for i in updates._filter_whats_new(entries, "stable", None, 10)] == ["200"]


def test_filter_beta_includes_both():
    entries = [_entry(300, "beta"), _entry(200, "stable")]
    assert [i["build"] for i in updates._filter_whats_new(entries, "beta", None, 10)] == ["300", "200"]


def test_filter_since_build_is_strictly_greater():
    entries = [_entry(300, "stable"), _entry(200, "stable"), _entry(100, "stable")]
    assert [i["build"] for i in updates._filter_whats_new(entries, "stable", 200, 10)] == ["300"]


def test_filter_limit_caps_to_newest():
    entries = [_entry(b, "stable") for b in (500, 400, 300, 200, 100)]
    assert [i["build"] for i in updates._filter_whats_new(entries, "stable", None, 2)] == ["500", "400"]


def test_filter_empty():
    assert updates._filter_whats_new([], "stable", None, 10) == []


def test_filter_non_numeric_build_skipped_when_since_given():
    entries = [_entry(200, "stable"), {**_entry(0, "stable"), "version_info": {"version": "x", "build": "NA"}}]
    # since_build filter drops the unparseable build rather than raising
    assert [i["build"] for i in updates._filter_whats_new(entries, "stable", 100, 10)] == ["200"]


# --- endpoint (async handler driven directly) ---


def _kv_release(tag, changelog=None, channel="stable", is_live=True, published_at="2026-01-01T00:00:00Z"):
    lines = [f"isLive: {'true' if is_live else 'false'}", f"channel: {channel}"]
    if changelog:
        lines.append("changelog: " + "|".join(changelog))
    body = "<!-- KEY_VALUE_START\n" + "\n".join(lines) + "\nKEY_VALUE_END -->"
    return {"tag_name": tag, "body": body, "published_at": published_at, "draft": False, "assets": []}


def _call(**kwargs):
    params = {"platform": "macos", "channel": "stable", "since_build": None, "limit": 10}
    params.update(kwargs)
    return asyncio.run(updates.get_desktop_whats_new(**params))


def test_endpoint_returns_items_newest_first():
    releases = [
        _kv_release("v1.0.0+100-macos", changelog=["Old"], published_at="2026-01-01T00:00:00Z"),
        _kv_release("v2.0.0+200-macos", changelog=["New"], published_at="2026-03-01T00:00:00Z"),
    ]
    with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
        result = _call()
    assert result["platform"] == "macos"
    assert [i["build"] for i in result["items"]] == ["200", "100"]


def test_endpoint_since_build_trims():
    releases = [
        _kv_release("v2.0.0+200-macos", published_at="2026-03-01T00:00:00Z"),
        _kv_release("v1.0.0+100-macos", published_at="2026-01-01T00:00:00Z"),
    ]
    with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=releases):
        result = _call(since_build=100)
    assert [i["build"] for i in result["items"]] == ["200"]


def test_endpoint_empty_upstream_is_200_empty():
    with patch("routers.updates.get_omi_github_releases", new_callable=AsyncMock, return_value=[]):
        result = _call()
    assert result == {"platform": "macos", "channel": "stable", "items": []}
