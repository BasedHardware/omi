"""_extract_firmware_response: is_legacy_secure_dfu parsing.

Replacing ast.literal_eval with a string compare must keep the historical
safe default: only an explicit false disables legacy DFU. Missing keys and
malformed values still select the legacy path so mobile startDfu does not
flip onto MCUmgr for unrecognized GitHub release metadata.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import routers.firmware as fw


def _release(dfu_line=None):
    extra = f"is_legacy_secure_dfu: {dfu_line}\n" if dfu_line is not None else ""
    body = "<!-- KEY_VALUE_START\n" "release_firmware_version: 3.0.15\n" f"{extra}" "KEY_VALUE_END -->"
    return {
        "tag_name": "Omi_CV1_v3.0.15",
        "body": body,
        "assets": [{"name": "Omi_CV1_OTA_v3.0.15.zip", "browser_download_url": "https://x/ota.zip"}],
        "draft": False,
        "prerelease": False,
        "published_at": "2026-01-01T00:00:00Z",
    }


def _extract(dfu_line=None):
    return fw._extract_firmware_response(fw.DeviceModel.OMI_CV1, _release(dfu_line))


def test_legacy_dfu_true_string():
    assert _extract("True")["is_legacy_secure_dfu"] is True
    assert _extract("true")["is_legacy_secure_dfu"] is True


def test_legacy_dfu_false_string():
    assert _extract("False")["is_legacy_secure_dfu"] is False
    assert _extract("false")["is_legacy_secure_dfu"] is False


def test_legacy_dfu_missing_key_defaults_true():
    assert _extract(None)["is_legacy_secure_dfu"] is True


def test_legacy_dfu_malformed_value_defaults_true():
    assert _extract("yes")["is_legacy_secure_dfu"] is True
    assert _extract("garbage")["is_legacy_secure_dfu"] is True
