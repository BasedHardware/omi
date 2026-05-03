"""Tests for the API-key auth flow."""

from __future__ import annotations

import pytest

from omi_cli import config as cfg
from omi_cli.auth import api_key as api_key_auth
from omi_cli.auth.store import clear_credentials, store_api_key
from omi_cli.errors import UsageError


def test_validate_rejects_empty_key() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("")


def test_validate_rejects_whitespace_only() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("   ")


def test_validate_rejects_non_dev_prefix() -> None:
    with pytest.raises(UsageError) as info:
        api_key_auth.validate_api_key_format("omi_mcp_" + "x" * 32)
    assert "developer key" in str(info.value).lower()


def test_validate_rejects_truncated_dev_key() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("omi_dev_short")


def test_validate_strips_whitespace() -> None:
    key = "omi_dev_" + "x" * 32
    result = api_key_auth.validate_api_key_format(f"  {key}\n")
    assert result == key


def test_login_persists_to_disk(config_path) -> None:
    key = "omi_dev_" + "y" * 40
    profile = api_key_auth.login_with_api_key("default", key, api_base="https://api.staging.omi.me")
    assert profile.api_key == key
    assert profile.api_base == "https://api.staging.omi.me"

    # Re-load from disk to confirm persistence.
    reloaded = cfg.load().get_profile("default")
    assert reloaded.api_key == key


def test_store_and_clear_round_trip(config_path) -> None:
    key = "omi_dev_" + "z" * 40
    store_api_key("default", key)
    assert cfg.load().get_profile("default").api_key == key

    cleared = clear_credentials("default")
    assert cleared is True
    assert cfg.load().get_profile("default").api_key is None
    assert cfg.load().get_profile("default").auth_method is None


def test_clear_credentials_returns_false_for_unconfigured_profile(config_path) -> None:
    assert clear_credentials("nonexistent") is False
