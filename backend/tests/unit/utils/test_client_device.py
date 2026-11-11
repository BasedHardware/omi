import pytest
from utils.client_device import build_client_device_id


def test_build_client_device_id_valid():
    assert build_client_device_id("ios", "12345678") == "ios_12345678"
    assert build_client_device_id("android", "abcdef12") == "android_abcdef12"
    assert build_client_device_id("WEB", "1234ABCD") == "web_1234abcd"
    assert build_client_device_id("  windows  ", "  12345678  ") == "windows_12345678"


def test_build_client_device_id_invalid_platform():
    assert build_client_device_id("blackberry", "12345678") is None
    assert build_client_device_id("", "12345678") is None
    assert build_client_device_id(None, "12345678") is None


def test_build_client_device_id_invalid_hash():
    assert build_client_device_id("ios", "1234567") is None
    assert build_client_device_id("ios", "123456789") is None
    assert build_client_device_id("ios", "1234567g") is None
    assert build_client_device_id("ios", "") is None
    assert build_client_device_id("ios", None) is None


def test_build_client_device_id_both_invalid():
    assert build_client_device_id("blackberry", "1234567") is None
    assert build_client_device_id(None, None) is None
