"""Firmware rollout policy with real KV parsing and mocked GitHub reads."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.firmware as fw


def release(version, policy='', published='2026-11-03T00:00:00Z'):
    return {
        'tag_name': f'Omi_CV1_v{version}',
        'published_at': published,
        'body': f'<!-- KEY_VALUE_START\nrelease_firmware_version:{version}\n{policy}\nKEY_VALUE_END -->',
        'assets': [{'name': 'ota.zip', 'browser_download_url': f'https://example.com/{version}.zip'}],
    }


def latest(releases, device_id=None):
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=releases)):
        return asyncio.run(fw.get_latest_version('Omi CV 1', '3.0.10', '1', 'Omi', device_id))


def test_missing_policy_preserves_existing_releases_for_unidentified_app():
    assert latest([release('3.0.21')])['version'] == '3.0.21'


def test_nested_cohorts_are_stable_and_cover_both_sides():
    devices = [f'bench-device-{n}' for n in range(1000)]
    first = {d for d in devices if fw._release_is_eligible({'rollout_percent': '1'}, d)}
    expanded = {d for d in devices if fw._release_is_eligible({'rollout_percent': '10'}, d)}
    assert 0 < len(first) < len(expanded) < len(devices)
    assert first <= expanded
    assert first == {d for d in devices if fw._release_is_eligible({'rollout_percent': '1'}, d)}
    assert fw._release_is_eligible({'rollout_percent': '1'}, 'bench-device-0') is False


@pytest.mark.parametrize('percent', ['0', '1', '99'])
@pytest.mark.parametrize('identifier', [None, '', '   '])
def test_partial_rollout_excludes_missing_device_identifier(percent, identifier):
    assert not fw._release_is_eligible({'rollout_percent': percent}, identifier)


def test_all_and_zero_boundaries():
    for device in (None, 'bench-device'):
        assert fw._release_is_eligible({'rollout_percent': '100'}, device)
        assert not fw._release_is_eligible({'rollout_percent': '0'}, device)


@pytest.mark.parametrize('percent', ['-1', '101', 'oops', '', '1.5'])
def test_invalid_percentage_cannot_expand_rollout(percent):
    assert not fw._release_is_eligible({'rollout_percent': percent}, 'bench-device')


@pytest.mark.parametrize('blocked', ['true', 'True', ' TRUE '])
def test_kill_switch_overrides_full_rollout(blocked):
    assert not fw._release_is_eligible({'blocked': blocked, 'rollout_percent': '100'}, 'bench-device')
    assert latest([release('3.0.21', f'blocked:{blocked}'), release('3.0.20')])['version'] == '3.0.20'


def test_outside_cohort_falls_back_to_newest_eligible_release():
    assert (
        latest([release('3.0.22', 'rollout_percent:0'), release('3.0.21'), release('3.0.20', published='2026-11-02')])[
            'version'
        ]
        == '3.0.21'
    )


def test_selected_device_receives_partial_release():
    device = next(
        f'device-{i}' for i in range(1000) if fw._release_is_eligible({'rollout_percent': '1'}, f'device-{i}')
    )
    assert latest([release('3.0.21', 'rollout_percent:1')], device)['version'] == '3.0.21'


def test_none_eligible_returns_existing_404_contract():
    with pytest.raises(HTTPException) as exc:
        latest([release('3.0.21', 'rollout_percent:1')])
    assert exc.value.status_code == 404


def test_fallback_retains_version_and_minimum_firmware_checks():
    with pytest.raises(HTTPException):
        latest(
            [release('3.0.21', 'blocked:true'), release('3.0.20', 'minimum_firmware_required:3.0.19'), release('3.0.9')]
        )


def test_blocked_release_is_also_unavailable_by_version_and_stable():
    releases = [release('3.0.21', 'blocked:true'), release('3.0.20')]
    assert fw._find_release_by_version(releases, 'Omi_CV1', (3, 0, 21)) is None
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=releases)):
        assert asyncio.run(fw.get_stable_version('Omi CV 1'))['version'] == '3.0.20'
