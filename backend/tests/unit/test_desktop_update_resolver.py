from unittest.mock import patch

from utils.desktop_update_resolver import resolve_pointer_release


def _release(channel="beta"):
    return {
        "pointer": {
            "platform": "macos",
            "channel": channel,
            "release_id": "v0.12.64+12064-macos",
            "generation": 3,
            "updated_at": "2026-07-09T12:00:00Z",
        },
        "manifest": {
            "release_id": "v0.12.64+12064-macos",
            "platform": "macos",
            "version": "0.12.64+12064",
            "build_number": 12064,
            "zip_url": "https://example.com/Omi.zip",
            "dmg_url": "https://example.com/Omi.dmg",
            "ed_signature": "signature",
            "published_at": "2026-07-09T12:00:00Z",
            "changelog": ["Qualified beta"],
            "mandatory": False,
            "source_sha": "a" * 40,
            "zip_sha256": "b" * 64,
            "dmg_sha256": "c" * 64,
            "qualification": {"passed": True, "tier": "T2"},
        },
    }


def test_live_pointer_cache_is_primary():
    with (
        patch("utils.desktop_update_resolver.get_generic_cache", return_value=_release()),
        patch("utils.desktop_update_resolver.get_channel_release") as firestore,
    ):
        release, source, reason = resolve_pointer_release("macos", "beta")

    assert release is not None
    assert source == "pointer_cache"
    assert reason is None
    firestore.assert_not_called()


def test_firestore_pointer_refreshes_live_and_lkg_caches():
    with (
        patch("utils.desktop_update_resolver.get_generic_cache", return_value=None),
        patch("utils.desktop_update_resolver.get_channel_release", return_value=_release()),
        patch("utils.desktop_update_resolver.set_generic_cache") as set_cache,
    ):
        release, source, reason = resolve_pointer_release("macos", "beta")

    assert release is not None
    assert source == "pointer"
    assert reason is None
    assert [call.args[0] for call in set_cache.call_args_list] == [
        "desktop_update_pointer:macos:beta",
        "desktop_update_pointer:macos:beta:lkg",
    ]


def test_validated_lkg_is_used_when_pointer_is_invalid():
    cache_values = [None, {**_release(), "cached_at": "2026-07-09T12:00:00Z"}]
    with (
        patch("utils.desktop_update_resolver.get_generic_cache", side_effect=cache_values),
        patch("utils.desktop_update_resolver.get_channel_release", side_effect=ValueError("invalid pointer")),
    ):
        release, source, reason = resolve_pointer_release("macos", "beta")

    assert release is not None
    assert source == "pointer_lkg"
    assert reason == "pointer_invalid"


def test_invalid_lkg_falls_through_for_legacy_resolution():
    with (
        patch("utils.desktop_update_resolver.get_generic_cache", side_effect=[None, {"bad": "cache"}]),
        patch("utils.desktop_update_resolver.get_channel_release", return_value=None),
    ):
        release, source, reason = resolve_pointer_release("macos", "stable")

    assert release is None
    assert source == "none"
    assert reason == "pointer_missing"
