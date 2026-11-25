"""Release-specific loader qualification across all OTA metadata routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.firmware as fw

QUALIFIED = 'a' * 64
OTHER = 'b' * 64


def release(version='3.0.25', policy=None, published='2026-11-18'):
    policy = f'required_bootloader_sha256:{QUALIFIED}' if policy is None else policy
    return {
        'tag_name': f'Omi_CV1_v{version}',
        'published_at': published,
        'body': f'<!-- KEY_VALUE_START\nrelease_firmware_version:{version}\n{policy}\nKEY_VALUE_END -->',
        'assets': [{'name': 'ota.zip', 'browser_download_url': 'https://example.com/ota.zip'}],
    }


@pytest.mark.parametrize('route', ['latest', 'stable', 'version'])
@pytest.mark.parametrize(
    'digest,eligible',
    [
        (None, False),
        ('', False),
        ('unknown', False),
        (OTHER, False),
        (QUALIFIED.upper(), False),
        (QUALIFIED + '\n', False),
        (' ' + QUALIFIED, False),
        (QUALIFIED, True),
    ],
)
def test_all_routes_require_exact_evidence(route, digest, eligible):
    app = FastAPI()
    app.include_router(fw.router)
    params = dict(
        device_model='Omi CV 1',
        firmware_revision='3.0.21',
        hardware_revision='1',
        manufacturer_name='Omi',
        version='3.0.25',
    )
    if digest is not None:
        params['bootloader_sha256'] = digest
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=[release()])):
        with TestClient(app) as client:
            response = client.get(f'/v2/firmware/{route}', params=params)
    assert response.status_code == (200 if eligible else 404)
    if eligible:
        assert response.json()['version'] == '3.0.25'


@pytest.mark.parametrize(
    'policy',
    ['', 'unknown', QUALIFIED + ',', ',' + QUALIFIED, 'A' * 64, QUALIFIED + ',bad', None, [], True, QUALIFIED + '\n'],
)
def test_invalid_explicit_policy_fails_closed(policy):
    # Spaces/newlines around metadata tokens are removed by the existing KV parser;
    # embedded garbage and empty tokens must not qualify a release.
    if policy == QUALIFIED + '\n':
        policy = QUALIFIED[:32] + '\n' + QUALIFIED[32:]
    assert not fw._release_is_eligible(
        {fw.REQUIRED_BOOTLOADER_KEY: policy}, None, bootloader_sha256=QUALIFIED, ignore_rollout_percent=True
    )


def test_multiple_qualified_loaders_and_unmodified_rollout():
    policy = {fw.REQUIRED_BOOTLOADER_KEY: f'{QUALIFIED}, {OTHER}', 'rollout_percent': '0'}
    assert not fw._release_is_eligible(policy, None, bootloader_sha256=OTHER)
    assert fw._release_is_eligible(policy, None, bootloader_sha256=OTHER, ignore_rollout_percent=True)
    assert not fw._release_is_eligible(
        {**policy, 'blocked': 'true'}, None, bootloader_sha256=OTHER, ignore_rollout_percent=True
    )


def test_audience_allowlist_cannot_bypass_loader_gate():
    policy = {fw.REQUIRED_BOOTLOADER_KEY: QUALIFIED, 'channels': 'beta', 'rollout_percent': '0'}
    audience = fw.ReleaseAudience(channel='beta')
    assert not fw._release_is_eligible(policy, None, audience=audience)
    assert fw._release_is_eligible(policy, None, audience=audience, bootloader_sha256=QUALIFIED)


@pytest.mark.parametrize('digest', [None, '', 'unknown', OTHER, QUALIFIED])
def test_no_policy_preserves_legacy_eligibility(digest):
    assert fw._release_is_eligible({}, None, bootloader_sha256=digest)
    assert not fw._release_is_eligible({'rollout_percent': '0'}, None, bootloader_sha256=digest)
    assert fw._release_is_eligible(
        {'rollout_percent': '0'}, None, bootloader_sha256=digest, ignore_rollout_percent=True
    )


def test_unknown_falls_back_only_to_previously_eligible_release():
    releases = [release(), release('3.0.24', 'rollout_percent:0', '2026-11-17'), release('3.0.21', '', '2026-11-16')]
    candidates = fw._find_candidate_releases(releases, 'Omi_CV1')
    assert [r['tag_name'] for r in candidates] == ['Omi_CV1_v3.0.21']
    assert not fw._find_candidate_releases(releases, 'Omi_CV1', (3, 0, 21))
    assert fw._find_release_by_version(releases, 'Omi_CV1', (3, 0, 25)) is None


@pytest.mark.parametrize('route', ['latest', 'stable', 'version'])
@pytest.mark.parametrize(
    'policy',
    [
        'required_bootloader_sha256',
        'required_bootloader_sha256=',
        f'required_bootloader_sha256:{QUALIFIED}\n,bad',
        f'required_bootloader_sha256:{QUALIFIED}\n{OTHER}',
        f'required_bootloader_sha256:{OTHER}\nrequired_bootloader_sha256:{QUALIFIED}',
        f'REQUIRED_BOOTLOADER_SHA256:{QUALIFIED}',
    ],
)
@pytest.mark.parametrize('digest', [None, QUALIFIED])
def test_malformed_guard_declaration_cannot_disappear_in_real_parser(route, policy, digest):
    app = FastAPI()
    app.include_router(fw.router)
    params = dict(
        device_model='Omi CV 1',
        firmware_revision='3.0.21',
        hardware_revision='1',
        manufacturer_name='Omi',
        version='3.0.25',
    )
    if digest is not None:
        params['bootloader_sha256'] = digest
    with patch.object(fw, 'get_omi_github_releases', AsyncMock(return_value=[release(policy=policy)])):
        with TestClient(app) as client:
            response = client.get(f'/v2/firmware/{route}', params=params)
    assert response.status_code == 404


def test_guard_in_ignored_second_block_or_outside_block_fails_closed():
    candidate = release(policy='')
    for extra in [
        f'\nrequired_bootloader_sha256:{QUALIFIED}',
        f'\n<!-- KEY_VALUE_START\nrequired_bootloader_sha256:{QUALIFIED}\nKEY_VALUE_END -->',
    ]:
        malformed = {**candidate, 'body': candidate['body'] + extra}
        assert not fw._find_candidate_releases([malformed], 'Omi_CV1', bootloader_sha256=QUALIFIED)


def test_unguarded_legacy_metadata_with_free_text_is_unchanged():
    assert fw._find_candidate_releases([release(policy='legacy free text')], 'Omi_CV1')


@pytest.mark.parametrize('declaration', ['required_bootloader_sha256', 'required_bootloader_sha256='])
def test_inline_malformed_declaration_is_not_ignored(declaration):
    candidate = release(policy='')
    candidate['body'] = f'<!-- KEY_VALUE_START {declaration}\nrelease_firmware_version:3.0.25\nKEY_VALUE_END -->'
    assert not fw._find_candidate_releases([candidate], 'Omi_CV1')


@pytest.mark.parametrize('separator', ['\r', '\v', '\f', '\x85', '\u2028', '\u2029'])
@pytest.mark.parametrize('declaration', ['required_bootloader_sha256=', f'required_bootloader_sha256:{QUALIFIED}'])
def test_non_lf_line_separator_cannot_hide_guard(separator, declaration):
    candidate = release(policy=f'x:y{separator}{declaration}')
    assert not fw._find_candidate_releases([candidate], 'Omi_CV1')
    assert not fw._find_candidate_releases([candidate], 'Omi_CV1', bootloader_sha256=QUALIFIED)


def test_colon_in_invalid_list_continuation_cannot_disguise_as_metadata():
    candidate = release(policy=f'required_bootloader_sha256:{QUALIFIED}\n,bad:ignored')
    assert not fw._find_candidate_releases([candidate], 'Omi_CV1', bootloader_sha256=QUALIFIED)
