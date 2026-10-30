"""CWE-209: appcast-generation exception details must never leak to clients.

Covers issue #21190:
  - backend/routers/updates.py (get_desktop_appcast_xml — /v2/desktop/appcast.xml)
  - backend/routers/desktop_tts_updates.py (promote_release — same desktop
    release-update machinery, same raw-exception-reflection class)

The fix pattern (mirroring google_calendar.py and PR #20896): full exception
detail goes to server-side logs via ``logger.error(..., exc_info=True)`` with
secret/PII scrubbing per the logging policy; the client-facing HTTPException
detail is a fixed generic message.

Hermetic: every external dependency is patched in-process; the network guard
in tests/conftest.py blocks any real outbound call.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.updates as updates_mod
import routers.desktop_tts_updates as tts_updates_mod

APPCAST_GENERIC_DETAIL = "Failed to generate desktop appcast."
PROMOTE_GENERIC_DETAIL = "Failed to promote release"

# Leak classes, not just one string: paths, connection strings, tokens, tracebacks.
LEAK_MARKERS = [
    "/etc/",
    "/var/",
    "/home/",
    "C:\\",
    "\\secrets\\",
    "api.github.com",
    ":443",
    "redis://",
    "Connection refused",
    "ghp_",
    "ghs_",
    "gho_",
    "Bearer",
    "sk-",
    "token=",
    "PERMISSION_DENIED",
    "Traceback (most recent call last)",
    'File "',
]


def _assert_sanitized(exc, expected_detail):
    assert exc.status_code in (400, 404, 500)
    assert exc.detail == expected_detail
    for marker in LEAK_MARKERS:
        assert marker not in exc.detail, f"leaked into client response: {marker!r}"


def _call_appcast(**overrides):
    kwargs = {"platform": "macos", "identity": "stable"}
    kwargs.update(overrides)
    return asyncio.run(updates_mod.get_desktop_appcast_xml(**kwargs))


class TestAppcastGenerationSanitization:
    """updates.py — GitHub resolution + XML generation failures stay server-side."""

    def test_github_resolution_failure_returns_generic_detail(self):
        sensitive = RuntimeError(
            "Connection refused to api.github.com:443: Bearer ghp_abcd1234efgh5678 "
            "while resolving /repos/BasedHardware/omi/releases for tarball"
        )
        with patch.object(updates_mod, "_get_live_desktop_releases", new=AsyncMock(side_effect=sensitive)):
            with pytest.raises(HTTPException) as ei:
                _call_appcast()
        assert ei.value.status_code == 500
        _assert_sanitized(ei.value, APPCAST_GENERIC_DETAIL)

    def test_xml_generation_failure_returns_generic_detail(self):
        entry = {
            "channel": "stable",
            "release": {"body": "notes", "published_at": "2026-10-10T12:00:00Z"},
            "version_info": {"version": "1.0.0", "build": "100"},
            "metadata": {"changelog": []},
        }
        leak = ValueError("encoding invalid at /var/app/internal_secrets/appcast_sparkle.xml")
        with (
            patch.object(updates_mod, "_get_live_desktop_releases", new=AsyncMock(return_value=[entry])),
            patch.object(updates_mod, "_parse_changelog_to_changes", return_value=[]),
            patch.object(
                updates_mod,
                "_get_sparkle_zip_download_url",
                return_value="https://example.com/Omi.zip",
            ),
            patch.object(updates_mod, "_generate_appcast_xml", side_effect=leak),
        ):
            with pytest.raises(HTTPException) as ei:
                _call_appcast()
        assert ei.value.status_code == 500
        _assert_sanitized(ei.value, APPCAST_GENERIC_DETAIL)

    def test_not_found_404_is_preserved(self):
        with patch.object(updates_mod, "_get_live_desktop_releases", new=AsyncMock(return_value=[])):
            with pytest.raises(HTTPException) as ei:
                _call_appcast()
        assert ei.value.status_code == 404
        assert "No desktop releases found" in ei.value.detail


class TestPromoteReleaseSanitization:
    """desktop_tts_updates.py — manifest/datastore internals stay server-side."""

    def _call_promote(self, boom):
        with (
            patch.object(tts_updates_mod, "_release_authorized", return_value=True),
            patch.object(tts_updates_mod, "_promote_release", side_effect=boom),
        ):
            return asyncio.run(tts_updates_mod.promote_release(SimpleNamespace(doc_id="d1"), x_release_secret="s3cret"))

    def test_value_error_detail_is_sanitized(self):
        def boom(*args, **kwargs):
            raise ValueError(
                'PERMISSION_DENIED: firestore doc "users/u1/desktop_releases/9921" '
                "manifest write blocked (service account svc-updates@based-hardware.iam)"
            )

        with pytest.raises(HTTPException) as ei:
            self._call_promote(boom)
        assert ei.value.status_code == 400
        _assert_sanitized(ei.value, PROMOTE_GENERIC_DETAIL)

    def test_generic_error_detail_already_generic(self):
        def boom(*args, **kwargs):
            raise RuntimeError("Traceback (most recent call last): ... db_executor pool exhausted")

        with pytest.raises(HTTPException) as ei:
            self._call_promote(boom)
        assert ei.value.status_code == 400
        _assert_sanitized(ei.value, PROMOTE_GENERIC_DETAIL)
