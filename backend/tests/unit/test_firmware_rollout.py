"""Firmware rollout policy with real KV parsing and mocked GitHub reads."""

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

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


@pytest.mark.parametrize('blocked', ['true', 'True', ' TRUE ', 'invalid', ''])
@pytest.mark.parametrize('percent', ['1', '100'])
def test_explicit_version_endpoint_returns_404_for_blocked_release(blocked, percent):
    app = FastAPI()
    app.include_router(fw.router)
    releases = [release('3.0.21', f'blocked:{blocked}\nrollout_percent:{percent}')]
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=releases)):
        with TestClient(app) as client:
            response = client.get('/v2/firmware/version', params={'device_model': 'Omi CV 1', 'version': '3.0.21'})
    assert response.status_code == 404


@pytest.mark.parametrize('percent', ['0', '1', '99'])
def test_explicit_version_endpoint_ignores_rollout_percent_for_support_and_reverts(percent):
    app = FastAPI()
    app.include_router(fw.router)
    releases = [release('3.0.21', f'blocked:false\nrollout_percent:{percent}')]
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=releases)):
        with TestClient(app) as client:
            response = client.get('/v2/firmware/version', params={'device_model': 'Omi CV 1', 'version': '3.0.21'})
            stable = client.get('/v2/firmware/stable', params={'device_model': 'Omi CV 1'})
    assert response.status_code == 200
    assert response.json()['version'] == '3.0.21'
    assert stable.status_code == 404


# Release audiences: an allowlist of hashed uids and app channels.

TESTER_UID = 'tester-uid'
TESTER_HASH = hashlib.sha256(TESTER_UID.encode()).hexdigest()
OTHER_HASH = hashlib.sha256(b'someone-else').hexdigest()


def audience(uid=None, channel='store'):
    return fw.ReleaseAudience(uid_sha256=hashlib.sha256(uid.encode()).hexdigest() if uid else None, channel=channel)


def test_allowlisted_uid_gets_zero_percent_release():
    kv = {'rollout_percent': '0', 'allow_uid_sha256': f'{OTHER_HASH}, {TESTER_HASH}'}
    assert fw._release_is_eligible(kv, None, audience=audience(TESTER_UID))
    assert not fw._release_is_eligible(kv, None, audience=audience('stranger'))
    assert not fw._release_is_eligible(kv, None)


def test_allowlist_alone_keeps_the_percent_cohort():
    kv = {'rollout_percent': '100', 'allow_uid_sha256': TESTER_HASH}
    assert fw._release_is_eligible(kv, None, audience=audience('stranger'))


def test_beta_channel_only_release():
    kv = {'rollout_percent': '100', 'channels': 'beta'}
    assert fw._release_is_eligible(kv, 'device', audience=audience(channel='beta'))
    for other in ('store', 'unknown'):
        assert not fw._release_is_eligible(kv, 'device', audience=audience(channel=other))
    assert not fw._release_is_eligible(kv, 'device')


def test_channel_and_allowlist_combine():
    kv = {'rollout_percent': '0', 'channels': 'beta', 'allow_uid_sha256': TESTER_HASH}
    assert fw._release_is_eligible(kv, None, audience=audience(TESTER_UID, 'store'))
    assert fw._release_is_eligible(kv, None, audience=audience('stranger', 'beta'))
    assert not fw._release_is_eligible(kv, None, audience=audience('stranger', 'store'))


@pytest.mark.parametrize(
    'policy',
    [
        {'allow_uid_sha256': ''},
        {'allow_uid_sha256': 'tester-uid'},
        {'allow_uid_sha256': f'{TESTER_HASH},'},
        {'channels': ''},
        {'channels': 'beta,testflight'},
    ],
)
def test_malformed_audience_fails_closed(policy):
    kv = {'rollout_percent': '100', **policy}
    assert not fw._release_is_eligible(kv, 'device', audience=audience(TESTER_UID, 'beta'))


def test_blocked_beats_audience():
    kv = {'blocked': 'true', 'channels': 'beta', 'allow_uid_sha256': TESTER_HASH}
    assert not fw._release_is_eligible(kv, None, audience=audience(TESTER_UID, 'beta'))


def _client_get(releases, headers, verified_uid=None):
    app = FastAPI()
    app.include_router(fw.router)
    params = {
        'device_model': 'Omi CV 1',
        'firmware_revision': '3.0.21',
        'hardware_revision': '1',
        'manufacturer_name': 'Omi',
    }
    verifier = MagicMock(return_value=verified_uid)
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=releases)), patch.object(
        fw, '_verified_uid', verifier
    ):
        with TestClient(app) as client:
            response = client.get('/v2/firmware/latest', params=params, headers=headers)
    return response, verifier


def test_latest_endpoint_reads_token_for_allowlisted_release():
    releases = [release('3.0.23', f'rollout_percent:0\nallow_uid_sha256:{TESTER_HASH}')]
    response, verifier = _client_get(releases, {'Authorization': 'Bearer t'}, verified_uid=TESTER_UID)
    assert response.status_code == 200
    assert response.json()['version'] == '3.0.23'
    verifier.assert_called_once_with('Bearer t')

    response, _ = _client_get(releases, {'Authorization': 'Bearer t'}, verified_uid=None)
    assert response.status_code == 404


def test_latest_endpoint_reads_app_channel_and_skips_token_without_allowlist():
    releases = [release('3.0.23', 'rollout_percent:0\nchannels:beta'), release('3.0.22')]
    beta, verifier = _client_get(releases, {'X-Omi-App-Channel': 'beta', 'Authorization': 'Bearer t'})
    store, _ = _client_get(releases, {'X-Omi-App-Channel': 'store'})
    assert beta.json()['version'] == '3.0.23'
    assert store.json()['version'] == '3.0.22'
    verifier.assert_not_called()
