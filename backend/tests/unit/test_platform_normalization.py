"""Regression tests for coarse platform normalization (`database.users`).

Part of the Windows platform-recognition fix: the raw `X-App-Platform` header is
normalized into a coarse `desktop | mobile | web` bucket used for signup /
last-active platform telemetry and per-device `device_class`. Windows must bucket
as `desktop` (it previously fell through to an unrecognized `None` coarse value).
"""

from database.users import _normalize_platform


def test_windows_normalizes_to_desktop():
    coarse, os_value = _normalize_platform('windows')
    assert coarse == 'desktop'
    assert os_value == 'windows'


def test_windows_is_case_insensitive():
    assert _normalize_platform('Windows')[0] == 'desktop'
    assert _normalize_platform('  WINDOWS  ')[0] == 'desktop'


def test_macos_still_desktop():
    assert _normalize_platform('macos') == ('desktop', 'macos')


def test_mobile_platforms_unchanged():
    assert _normalize_platform('ios')[0] == 'mobile'
    assert _normalize_platform('android')[0] == 'mobile'


def test_unrecognized_platform_has_no_coarse_bucket():
    coarse, os_value = _normalize_platform('linux')
    assert coarse is None
    assert os_value == 'linux'


def test_missing_platform():
    assert _normalize_platform(None) == (None, None)
    assert _normalize_platform('') == (None, None)
