from unittest.mock import MagicMock
from database.app_review_config import (
    _fetch_review_config,
    _is_plausible_version,
    get_review_config,
    should_hide_subscription_ui,
)


def test_is_plausible_version():
    assert _is_plausible_version("1.0.531") is True
    assert _is_plausible_version("v1.0.531") is True
    assert _is_plausible_version("1.0.531+607") is True
    assert _is_plausible_version(" 1.0.0 ") is True
    assert _is_plausible_version("2") is True
    assert _is_plausible_version("2.1") is True
    assert _is_plausible_version("") is False
    assert _is_plausible_version("   ") is False
    assert _is_plausible_version("invalid") is False
    assert _is_plausible_version("malformed..version") is False
    assert _is_plausible_version("1.0-alpha") is False


def test_should_hide_unsupported_or_empty_platform():
    assert should_hide_subscription_ui("user1", None, "1.0.0") is False
    assert should_hide_subscription_ui("user1", "", "1.0.0") is False
    assert should_hide_subscription_ui("user1", "   ", "1.0.0") is False
    assert should_hide_subscription_ui("user1", "android", "1.0.0") is False
    assert should_hide_subscription_ui("user1", "web", "1.0.0") is False
    assert should_hide_subscription_ui("user1", "windows", "1.0.0") is False


def test_should_hide_platform_whitespace_and_casing_normalization():
    cfg = {"reviewer_uids": ["reviewer_1"], "hidden_versions": ["1.0.531"]}

    # Whitespace and uppercase in 'ios'
    assert should_hide_subscription_ui("reviewer_1", " iOS ", "1.0.0", config=cfg) is True
    assert should_hide_subscription_ui("reviewer_1", "\tios\n", "1.0.0", config=cfg) is True

    # Whitespace and uppercase in 'macos'
    assert should_hide_subscription_ui("reviewer_1", "  MacOS  ", "1.0.0", config=cfg) is True
    assert should_hide_subscription_ui("user_regular", " MacOS ", "1.0.531", config=cfg) is True


def test_should_hide_by_reviewer_uid_exact_and_trimmed():
    cfg = {
        "reviewer_uids": ["apple_reviewer_1", "  apple_reviewer_2  ", 12345, None],
        "hidden_versions": [],
    }

    assert should_hide_subscription_ui("apple_reviewer_1", "ios", "1.0.0", config=cfg) is True
    assert should_hide_subscription_ui("  apple_reviewer_1  ", "ios", "1.0.0", config=cfg) is True
    assert should_hide_subscription_ui("apple_reviewer_2", "ios", "1.0.0", config=cfg) is True
    assert should_hide_subscription_ui("unknown_user", "ios", "1.0.0", config=cfg) is False
    assert should_hide_subscription_ui("", "ios", "1.0.0", config=cfg) is False
    assert should_hide_subscription_ui("   ", "ios", "1.0.0", config=cfg) is False


def test_should_hide_by_version_semantic_and_build():
    cfg = {
        "reviewer_uids": [],
        "hidden_versions": ["1.0.531", "2.1.0+400", "  3.0.0  ", None, 999],
    }

    # Matches semantic version and any build of it
    assert should_hide_subscription_ui("user1", "ios", "1.0.531", config=cfg) is True
    assert should_hide_subscription_ui("user1", "ios", "1.0.531+607", config=cfg) is True
    assert should_hide_subscription_ui("user1", "ios", " 1.0.531 ", config=cfg) is True

    # Specific build match
    assert should_hide_subscription_ui("user1", "ios", "2.1.0+400", config=cfg) is True
    assert should_hide_subscription_ui("user1", "ios", "2.1.0+401", config=cfg) is False

    # Trimmed version match
    assert should_hide_subscription_ui("user1", "ios", "3.0.0", config=cfg) is True

    # Non-matching versions
    assert should_hide_subscription_ui("user1", "ios", "1.0.532", config=cfg) is False
    assert should_hide_subscription_ui("user1", "ios", "0.9.0", config=cfg) is False
    assert should_hide_subscription_ui("user1", "ios", None, config=cfg) is False
    assert should_hide_subscription_ui("user1", "ios", "", config=cfg) is False
    assert should_hide_subscription_ui("user1", "ios", "   ", config=cfg) is False


def test_should_hide_handles_malformed_version_safely():
    cfg = {
        "reviewer_uids": [],
        "hidden_versions": ["", "   ", "malformed..version", "special-build-42"],
    }

    # Should not match blank/empty version and should not crash on invalid strings
    assert should_hide_subscription_ui("user1", "ios", "1.0.0", config=cfg) is False
    assert should_hide_subscription_ui("user1", "ios", "invalid_ver", config=cfg) is False
    # Exact non-semantic string match works
    assert should_hide_subscription_ui("user1", "ios", "special-build-42", config=cfg) is True


def test_should_hide_non_list_config_fields():
    cfg = {
        "reviewer_uids": "invalid_string_instead_of_list",
        "hidden_versions": 12345,
    }
    assert should_hide_subscription_ui("user1", "ios", "1.0.0", config=cfg) is False


def test_fetch_review_config_success_and_missing_doc():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"hidden_versions": ["1.0.0"]}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    result = _fetch_review_config("ios", firestore_client=mock_client)
    assert result == {"hidden_versions": ["1.0.0"]}
    mock_client.collection.assert_called_with("app_review_config")
    mock_client.collection.return_value.document.assert_called_with("ios")

    # Document does not exist
    mock_doc.exists = False
    result_missing = _fetch_review_config("ios", firestore_client=mock_client)
    assert result_missing == {}


def test_fetch_review_config_non_dict_return():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = "string_not_dict"
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    result = _fetch_review_config("ios", firestore_client=mock_client)
    assert result == {}


def test_fetch_review_config_exception_safety():
    mock_client = MagicMock()
    mock_client.collection.side_effect = RuntimeError("Firestore unavailable")

    # Should safely return empty dict and not raise
    result = _fetch_review_config("ios", firestore_client=mock_client)
    assert result == {}


def test_fetch_review_config_none_client():
    # If client is None and db is None, safely return {}
    assert _fetch_review_config("ios", firestore_client=None) == {} or isinstance(
        _fetch_review_config("ios", firestore_client=None), dict
    )


def test_get_review_config_platform_sanitization():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"hidden_versions": ["1.2.3"]}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    # Empty platform returns {}
    assert get_review_config("", firestore_client=mock_client) == {}
    assert get_review_config("   ", firestore_client=mock_client) == {}

    # Stripped & lowercased platform passed to fetcher
    res = get_review_config("  IOS  ", firestore_client=mock_client)
    assert res == {"hidden_versions": ["1.2.3"]}
    mock_client.collection.return_value.document.assert_called_with("ios")


def test_should_hide_subscription_ui_with_injected_firestore_client():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"reviewer_uids": ["tester_uid"]}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    assert should_hide_subscription_ui("tester_uid", "ios", "1.0.0", firestore_client=mock_client) is True
    assert should_hide_subscription_ui("other_uid", "ios", "1.0.0", firestore_client=mock_client) is False
