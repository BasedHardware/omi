from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from routers import app_review_config_sweep as router
from services import app_review_config_lifecycle as lifecycle

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT.parent / 'app' / 'scripts'


def active_entry(platform: str, version: str, *, code: str | None = None, expiry: datetime | None = None):
    entry = {
        'platform': platform,
        'version': version,
        'submitted_at': (NOW - timedelta(hours=1)).isoformat(),
        'expires_at': (expiry or NOW + timedelta(days=14)).isoformat(),
        'state': 'active',
        'owns_hidden_version': True,
        'source': 'submission',
    }
    if code is not None:
        entry['version_code'] = code
    return entry


@pytest.mark.parametrize('state', ['WAITING_FOR_REVIEW', 'IN_REVIEW'])
def test_apple_review_states_keep_active_hide(state):
    config = {
        'hidden_versions': ['2.1.0'],
        'reviewer_uids': ['legacy-reviewer'],
        'review_submission_entries': [active_entry('ios', '2.1.0')],
    }

    updated, repairs, clears = lifecycle.reconcile_ios_config(config, version_states={'2.1.0': state}, now=NOW)

    assert updated == config
    assert (repairs, clears) == (0, 0)


@pytest.mark.parametrize('state', ['PENDING_DEVELOPER_RELEASE', 'READY_FOR_SALE', 'REJECTED'])
def test_apple_terminal_states_clear_owned_hide_and_metadata(state):
    config = {
        'hidden_versions': ['2.1.0', 'legacy-version'],
        'reviewer_uids': ['legacy-reviewer'],
        'review_submission_entries': [active_entry('ios', '2.1.0')],
    }

    updated, repairs, clears = lifecycle.reconcile_ios_config(config, version_states={'2.1.0': state}, now=NOW)

    assert updated['hidden_versions'] == ['legacy-version']
    assert updated['reviewer_uids'] == ['legacy-reviewer']
    assert updated['review_submission_entries'] == []
    assert (repairs, clears) == (0, 1)


def test_apple_reconciliation_repairs_missing_hide_and_does_not_extend_active_ttl():
    existing = active_entry('ios', '2.1.0', expiry=NOW + timedelta(days=3))
    config = {'hidden_versions': [], 'review_submission_entries': [existing]}

    updated, repairs, clears = lifecycle.reconcile_ios_config(
        config, version_states={'2.1.0': 'IN_REVIEW', '2.2.0': 'WAITING_FOR_REVIEW'}, now=NOW
    )

    assert updated['hidden_versions'] == ['2.1.0', '2.2.0']
    entries = updated['review_submission_entries']
    assert entries[0]['expires_at'] == existing['expires_at']
    assert entries[1]['source'] == 'reconciliation'
    assert (repairs, clears) == (2, 0)


def test_expired_tombstone_prevents_l4_from_rehiding_long_review():
    expired = active_entry('ios', '2.1.0', expiry=NOW - timedelta(seconds=1))
    config = {'hidden_versions': ['2.1.0', 'manual'], 'review_submission_entries': [expired]}
    expired_config, count = lifecycle.expire_config_entries(config, now=NOW)

    assert count == 1
    assert expired_config['hidden_versions'] == ['manual']
    assert expired_config['review_submission_entries'][0]['state'] == 'expired'
    reconciled, repairs, clears = lifecycle.reconcile_ios_config(
        expired_config, version_states={'2.1.0': 'IN_REVIEW'}, now=NOW
    )
    assert reconciled == expired_config
    assert (repairs, clears) == (0, 0)


def test_ttl_preserves_manual_legacy_hides():
    entry = active_entry('ios', '2.1.0', expiry=NOW - timedelta(seconds=1))
    entry['owns_hidden_version'] = False
    config = {'hidden_versions': ['2.1.0', 'old-ios-version'], 'review_submission_entries': [entry]}

    updated, count = lifecycle.expire_config_entries(config, now=NOW)

    assert count == 1
    assert updated['hidden_versions'] == ['2.1.0', 'old-ios-version']
    assert updated['review_submission_entries'][0]['state'] == 'expired'


def test_missing_ttl_cannot_leave_an_owned_hide_permanent():
    entry = active_entry('ios', '2.1.0')
    entry.pop('expires_at')
    config = {'hidden_versions': ['2.1.0'], 'review_submission_entries': [entry]}

    updated, count = lifecycle.expire_config_entries(config, now=NOW)

    assert count == 1
    assert updated['hidden_versions'] == []
    assert updated['review_submission_entries'][0]['state'] == 'expired'


def test_play_production_version_code_clears_hide_and_preserves_manual_entry():
    config = {
        'hidden_versions': ['3.0.0', 'legacy-android'],
        'review_submission_entries': [active_entry('android', '3.0.0', code='412')],
    }

    updated, repairs, clears = lifecycle.reconcile_android_config(config, production_codes={'412'})

    assert updated['hidden_versions'] == ['legacy-android']
    assert updated['review_submission_entries'] == []
    assert (repairs, clears) == (0, 1)


def test_android_missing_hide_is_repaired_while_code_is_not_on_production():
    config = {'hidden_versions': [], 'review_submission_entries': [active_entry('android', '3.0.0', code='412')]}

    updated, repairs, clears = lifecycle.reconcile_android_config(config, production_codes={'999'})

    assert updated['hidden_versions'] == ['3.0.0']
    assert updated['review_submission_entries'] == config['review_submission_entries']
    assert (repairs, clears) == (1, 0)


def test_submission_ttl_is_fourteen_days_and_existing_fields_survive():
    config = {'hidden_versions': ['legacy'], 'reviewer_uids': ['reviewer'], 'other': 'kept'}

    updated = lifecycle.record_submission_config(
        config, platform='android', version='3.0.0', version_code='412', now=NOW
    )

    entry = updated['review_submission_entries'][0]
    assert entry['expires_at'] == (NOW + timedelta(days=14)).isoformat().replace('+00:00', 'Z')
    assert entry['version_code'] == '412'
    assert updated['hidden_versions'] == ['legacy', '3.0.0']
    assert updated['reviewer_uids'] == ['reviewer']
    assert updated['other'] == 'kept'


def test_store_api_failures_still_run_ttl_and_keep_unexpired_hides(monkeypatch):
    configs = {
        'ios': {'hidden_versions': ['2.1.0'], 'review_submission_entries': [active_entry('ios', '2.1.0')]},
        'android': {
            'hidden_versions': ['3.0.0'],
            'review_submission_entries': [
                active_entry('android', '3.0.0', code='412', expiry=NOW - timedelta(seconds=1))
            ],
        },
    }
    monkeypatch.setattr(lifecycle, '_firestore_config', lambda platform: configs[platform])

    def update(platform, transform):
        configs[platform] = transform(configs[platform])
        return configs[platform]

    monkeypatch.setattr(lifecycle, '_update_config', update)
    monkeypatch.setattr(lifecycle, '_apple_versions', lambda: (_ for _ in ()).throw(RuntimeError('offline')))
    monkeypatch.setattr(
        lifecycle,
        '_play_production_codes',
        lambda: (_ for _ in ()).throw(lifecycle.StoreCredentialsUnavailable('missing')),
    )

    summary = lifecycle.run_app_review_config_sweep(now=NOW)

    assert summary == {'expired': 1, 'repaired': 0, 'cleared': 0, 'store_errors': 2}
    assert configs['ios']['hidden_versions'] == ['2.1.0']
    assert configs['android']['hidden_versions'] == []
    assert configs['android']['review_submission_entries'][0]['state'] == 'expired'


def test_play_reader_uses_only_production_track_and_deletes_temporary_edit(monkeypatch):
    class Response:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            return None

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append(('post', url))
            return Response({'id': 'ephemeral-edit'})

        def get(self, url, **kwargs):
            self.calls.append(('get', url))
            return Response(
                {
                    'track': 'production',
                    'releases': [
                        {'status': 'inProgress', 'userFraction': 0.01, 'versionCodes': ['412']},
                        {'status': 'completed', 'versionCodes': ['411']},
                    ],
                }
            )

        def delete(self, url, **kwargs):
            self.calls.append(('delete', url))
            return Response({})

    session = Session()
    monkeypatch.setattr(lifecycle, 'load_secret', lambda _name: json.dumps({'type': 'service_account'}))
    monkeypatch.setattr(
        'google.oauth2.service_account.Credentials.from_service_account_info', lambda *_a, **_k: object()
    )
    monkeypatch.setattr(lifecycle, 'AuthorizedSession', lambda _credentials: session)

    assert lifecycle._play_production_codes() == {'411', '412'}
    assert len(session.calls) == 3
    assert '/tracks/production' in session.calls[1][1]
    assert '/tracks/internal' not in str(session.calls)
    assert session.calls[2][0] == 'delete'


def test_apple_reader_maps_all_paged_states_through_fake_http(monkeypatch):
    responses = [
        {
            'data': [
                {'attributes': {'versionString': '2.1.0', 'appStoreState': 'IN_REVIEW'}},
                {'attributes': {'versionString': '2.0.0', 'appStoreState': 'READY_FOR_SALE'}},
            ],
            'links': {'next': f'{lifecycle.APPLE_API}/apps/{lifecycle.APPLE_APP_ID}/appStoreVersions?cursor=2'},
        },
        {'data': [{'attributes': {'versionString': '2.2.0', 'appStoreState': 'WAITING_FOR_REVIEW'}}], 'links': {}},
    ]
    calls = []

    class Response:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(responses.pop(0))

    monkeypatch.setattr(
        lifecycle,
        'load_secret',
        lambda _name: json.dumps({'issuer_id': 'issuer', 'key_id': 'key', 'private_key': 'pem'}),
    )
    monkeypatch.setattr(lifecycle.jwt, 'encode', lambda *_a, **_k: 'fake-jwt')
    monkeypatch.setattr(lifecycle.requests, 'get', fake_get)

    assert lifecycle._apple_versions() == {
        '2.1.0': 'IN_REVIEW',
        '2.0.0': 'READY_FOR_SALE',
        '2.2.0': 'WAITING_FOR_REVIEW',
    }
    assert len(calls) == 2
    assert calls[0][1]['params']['filter[platform]'] == 'IOS'
    assert calls[0][1]['headers']['Authorization'] == 'Bearer fake-jwt'
    assert calls[1][1]['params'] is None


def test_alert_rules_cover_lifecycle_events_and_dead_sweeper():
    path = BACKEND_ROOT / 'charts' / 'monitoring' / 'alerts' / 'app-review-config.json'
    rules = {rule['uid']: rule for rule in json.loads(path.read_text(encoding='utf-8'))}

    page = rules['omi-app-review-config-alert']
    assert not page['isPaused']
    assert 'increase(omi_app_review_config_alert_total[15m])' in page['data'][0]['model']['expr']
    deadman = rules['omi-app-review-config-sweep-silent']
    assert deadman['isPaused']
    assert deadman['noDataState'] == 'Alerting'
    assert 'omi_app_review_config_last_sweep_timestamp_seconds' in deadman['data'][0]['model']['expr']


def test_submission_endpoint_rejects_missing_and_wrong_token(monkeypatch):
    monkeypatch.setattr(router, 'load_secret', lambda _name: 'expected-token')
    monkeypatch.setattr(router, 'submit_review_version', Mock(side_effect=AssertionError('must not write')))
    body = router.ReviewSubmission(platform='ios', version='2.1.0')

    for token in (None, 'wrong-token'):
        with pytest.raises(HTTPException) as error:
            asyncio.run(router.record_review_submission(body, token))
        assert error.value.status_code == 401


def test_submission_endpoint_fails_closed_when_credential_is_missing(monkeypatch):
    monkeypatch.setattr(
        router, 'load_secret', lambda _name: (_ for _ in ()).throw(lifecycle.StoreCredentialsUnavailable('missing'))
    )
    body = router.ReviewSubmission(platform='ios', version='2.1.0')

    with pytest.raises(HTTPException) as error:
        asyncio.run(router.record_review_submission(body, 'token'))
    assert error.value.status_code == 503


def _load_script(name: str):
    path = APP_ROOT / name
    spec = importlib.util.spec_from_file_location(f'test_{path.stem}', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_codemagic_receipt_hook_posts_exact_platform_version_and_build_without_logging_token(
    tmp_path, monkeypatch, capsys
):
    promote = _load_script('mobile_store_promote.py')
    hook = _load_script('app_review_config_hook.py')
    receipt = tmp_path / 'receipt.json'
    monkeypatch.setenv('APP_REVIEW_CONFIG_SUBMISSION_RECEIPT', str(receipt))
    monkeypatch.setenv('APP_REVIEW_CONFIG_SUBMISSION_TOKEN', 'do-not-print-token')
    promote.record_review_submission('android', '3.0.0', '412')

    seen = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def opener(request, **_kwargs):
        seen.append((json.loads(request.data), request.get_header('X-review-config-token')))
        return Response()

    assert hook.post_receipts(receipt, opener=opener) == 0
    assert seen == [({'platform': 'android', 'version': '3.0.0', 'version_code': '412'}, 'do-not-print-token')]
    output = capsys.readouterr()
    assert 'do-not-print-token' not in output.out + output.err
