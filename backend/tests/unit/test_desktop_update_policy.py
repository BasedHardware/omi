from unittest.mock import MagicMock
import pytest

from database.desktop_update_policy import (
    DEFAULT_DESKTOP_DOWNLOAD_URL,
    default_desktop_update_policy,
    get_desktop_update_policy,
    _normalize_policy,
    _applies_to_platform,
    _as_int,
    _as_bool,
    _as_string,
    _as_string_list,
    _as_download_url,
)


def test_as_int_valid_and_invalid():
    assert _as_int(123) == 123
    assert _as_int("456") == 456
    assert _as_int("  789  ") == 789
    assert _as_int(True) is None
    assert _as_int(False) is None
    assert _as_int("invalid") is None
    assert _as_int(None) is None
    assert _as_int([]) is None


def test_as_bool_valid_and_default():
    assert _as_bool(True) is True
    assert _as_bool(False) is False
    assert _as_bool("True", default=False) is False
    assert _as_bool(None, default=True) is True


def test_as_string_clean():
    assert _as_string("hello") == "hello"
    assert _as_string("  hello  ") == "hello"
    assert _as_string("   ") is None
    assert _as_string(None) is None
    assert _as_string(123) is None


def test_as_string_list():
    assert _as_string_list(["macos", "windows"]) == ["macos", "windows"]
    assert _as_string_list([" macos ", "   ", 123, None, "linux"]) == ["macos", "linux"]
    assert _as_string_list("not a list") == []
    assert _as_string_list(None) == []


def test_as_download_url_valid_schemes():
    assert _as_download_url("https://example.com/update") == "https://example.com/update"
    assert _as_download_url("http://example.com/update") == "http://example.com/update"
    assert _as_download_url("ftp://example.com/update") is None
    assert _as_download_url("javascript:alert(1)") is None
    assert _as_download_url("not a url") is None
    assert _as_download_url(None) is None


def test_default_desktop_update_policy():
    policy = default_desktop_update_policy()
    assert policy["id"] == "current"
    assert policy["active"] is False
    assert policy["severity"] == "none"
    assert policy["download_url"] == DEFAULT_DESKTOP_DOWNLOAD_URL
    assert policy["can_dismiss"] is True
    assert policy["platforms"] == []


def test_normalize_policy_none_and_empty():
    assert _normalize_policy(None) == default_desktop_update_policy()
    assert _normalize_policy("not a dict") == default_desktop_update_policy()
    res = _normalize_policy({})
    assert res["active"] is False
    assert res["severity"] == "none"


def test_normalize_policy_with_values():
    raw = {
        "id": "forced-update-v2",
        "active": True,
        "severity": "required",
        "maximum_build_number": 500,
        "latest_build_number": 510,
        "title": "Security Update",
        "message": "Please update your client immediately.",
        "cta_text": "Upgrade Now",
        "download_url": "https://download.omi.me/v2/update",
        "can_dismiss": False,
        "platforms": ["macos", "windows"],
    }
    policy = _normalize_policy(raw)
    assert policy["id"] == "forced-update-v2"
    assert policy["active"] is True
    assert policy["severity"] == "required"
    assert policy["maximum_build_number"] == 500
    assert policy["latest_build_number"] == 510
    assert policy["title"] == "Security Update"
    assert policy["message"] == "Please update your client immediately."
    assert policy["cta_text"] == "Upgrade Now"
    assert policy["download_url"] == "https://download.omi.me/v2/update"
    assert policy["can_dismiss"] is False
    assert policy["platforms"] == ["macos", "windows"]


def test_normalize_policy_severity_fallback():
    raw = {"severity": "unknown_value"}
    policy = _normalize_policy(raw)
    assert policy["severity"] == "none"


def test_normalize_policy_minimum_build_fallback():
    raw = {"minimum_build_number": "450"}
    policy = _normalize_policy(raw)
    assert policy["maximum_build_number"] == 450


def test_applies_to_platform():
    policy = {"platforms": ["macos", "windows"]}
    assert _applies_to_platform(policy, "macos") is True
    assert _applies_to_platform(policy, "MacOS") is True
    assert _applies_to_platform(policy, "windows") is True
    assert _applies_to_platform(policy, "linux") is False
    assert _applies_to_platform(policy, None) is False
    assert _applies_to_platform(policy, 123) is False

    empty_platforms_policy = {"platforms": []}
    assert _applies_to_platform(empty_platforms_policy, "linux") is True
    assert _applies_to_platform(empty_platforms_policy, "macos") is True


def test_get_desktop_update_policy_not_existing():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_client.collection().document().get.return_value = mock_doc

    policy = get_desktop_update_policy(100, "macos", firestore_client=mock_client)
    assert policy == default_desktop_update_policy()


def test_get_desktop_update_policy_exception_fallback():
    mock_client = MagicMock()
    mock_client.collection.side_effect = RuntimeError("Firestore unavailable")

    policy = get_desktop_update_policy(100, "macos", firestore_client=mock_client)
    assert policy == default_desktop_update_policy()


def test_get_desktop_update_policy_platform_mismatch():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "active": True,
        "severity": "required",
        "platforms": ["windows"],
    }
    mock_client.collection().document().get.return_value = mock_doc

    policy = get_desktop_update_policy(100, "macos", firestore_client=mock_client)
    assert policy == default_desktop_update_policy()


def test_get_desktop_update_policy_build_exceeds_maximum():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "active": True,
        "severity": "required",
        "maximum_build_number": 200,
        "platforms": ["macos"],
    }
    mock_client.collection().document().get.return_value = mock_doc

    # Current build 250 > maximum build 200 -> exempt from forced update
    policy = get_desktop_update_policy(250, "macos", firestore_client=mock_client)
    assert policy == default_desktop_update_policy()

    # Current build 150 <= maximum build 200 -> update policy active
    policy_active = get_desktop_update_policy(150, "macos", firestore_client=mock_client)
    assert policy_active["active"] is True
    assert policy_active["maximum_build_number"] == 200


def test_get_desktop_update_policy_inactive():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "active": False,
        "severity": "required",
    }
    mock_client.collection().document().get.return_value = mock_doc

    policy = get_desktop_update_policy(100, "macos", firestore_client=mock_client)
    assert policy == default_desktop_update_policy()
