from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from routers import app_review_config_sweep as router
from services import app_review_config_lifecycle as lifecycle
from utils.other import endpoints as endpoint_utils

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT.parent / 'app' / 'scripts'


def active_entry(
    platform: str,
    version: str,
    *,
    code: str | None = None,
    expiry: datetime | None = None,
):
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
        config,
        version_states={'2.1.0': 'IN_REVIEW', '2.2.0': 'WAITING_FOR_REVIEW'},
        now=NOW,
    )

    assert updated['hidden_versions'] == ['2.1.0', '2.2.0']
    entries = updated['review_submission_entries']
    assert entries[0]['expires_at'] == existing['expires_at']
    assert entries[1]['source'] == 'reconciliation'
    assert (repairs, clears) == (2, 0)


def test_expired_tombstone_prevents_l4_from_rehiding_long_review():
    expired = active_entry('ios', '2.1.0', expiry=NOW - timedelta(seconds=1))
    config = {
        'hidden_versions': ['2.1.0', 'manual'],
        'review_submission_entries': [expired],
    }
    expired_config, count = lifecycle.expire_config_entries(config, now=NOW)

    assert count == 1
    assert expired_config['hidden_versions'] == ['manual']
    assert expired_config['review_submission_entries'][0]['state'] == 'expired'
    reconciled, repairs, clears = lifecycle.reconcile_ios_config(
        expired_config, version_states={'2.1.0': 'IN_REVIEW'}, now=NOW
    )
    assert reconciled == expired_config
    assert (repairs, clears) == (0, 0)


def test_ttl_expires_an_adopted_preexisting_hide_but_preserves_unmatched_legacy_hides():
    entry = active_entry('ios', '2.1.0', expiry=NOW - timedelta(seconds=1))
    entry['owns_hidden_version'] = False  # persisted by the earlier implementation
    config = {
        'hidden_versions': ["2.1.0+22", 'old-ios-version'],
        'review_submission_entries': [entry],
    }

    updated, count = lifecycle.expire_config_entries(config, now=NOW)

    assert count == 1
    assert updated['hidden_versions'] == ['old-ios-version']
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
        'hidden_versions': ["3.0.0+12", 'legacy-android'],
        'review_submission_entries': [active_entry('android', '3.0.0', code='412')],
    }

    updated, repairs, clears = lifecycle.reconcile_android_config(config, production_codes={'412'})

    assert updated['hidden_versions'] == ['legacy-android']
    assert updated['review_submission_entries'] == []
    assert (repairs, clears) == (0, 1)


def test_existing_hide_is_removed_when_ios_version_becomes_live_without_a_lifecycle_entry():
    config = {"hidden_versions": ["2.1.0+22", "unmatched-legacy"]}

    updated, repairs, clears = lifecycle.reconcile_ios_config(
        config, version_states={"2.1.0": "READY_FOR_SALE"}, now=NOW
    )

    assert updated["hidden_versions"] == ["unmatched-legacy"]
    assert (repairs, clears) == (0, 1)


def test_android_missing_hide_is_repaired_while_code_is_not_on_production():
    config = {
        'hidden_versions': [],
        'review_submission_entries': [active_entry('android', '3.0.0', code='412')],
    }

    updated, repairs, clears = lifecycle.reconcile_android_config(config, production_codes={'999'})

    assert updated['hidden_versions'] == ['3.0.0']
    assert updated['review_submission_entries'] == config['review_submission_entries']
    assert (repairs, clears) == (1, 0)


def test_submission_ttl_is_fourteen_days_and_existing_fields_survive():
    config = {
        'hidden_versions': ['legacy'],
        'reviewer_uids': ['reviewer'],
        'other': 'kept',
    }

    updated = lifecycle.record_submission_config(
        config, platform='android', version='3.0.0', version_code='412', now=NOW
    )

    entry = updated['review_submission_entries'][0]
    assert entry['expires_at'] == (NOW + timedelta(days=14)).isoformat().replace('+00:00', 'Z')
    assert entry['version_code'] == '412'
    assert updated['hidden_versions'] == ['legacy', '3.0.0']
    assert updated['reviewer_uids'] == ['reviewer']
    assert updated['other'] == 'kept'


def test_submission_adopts_a_preexisting_build_qualified_hide_for_its_semantic_version():
    updated = lifecycle.record_submission_config(
        {"hidden_versions": ["2.1.0+22", "unmatched-legacy"]},
        platform="ios",
        version="2.1.0",
        version_code=None,
        now=NOW,
    )

    assert updated["hidden_versions"] == ["2.1.0+22", "unmatched-legacy"]
    assert updated["review_submission_entries"][0]["owns_hidden_version"] is True


def test_replayed_receipt_does_not_extend_an_active_submission_lease():
    existing = active_entry("ios", "2.1.0", expiry=NOW + timedelta(days=2))
    config = {"hidden_versions": ["2.1.0"], "review_submission_entries": [existing]}

    updated = lifecycle.record_submission_config(config, platform="ios", version="2.1.0", version_code=None, now=NOW)

    row = updated["review_submission_entries"][0]
    assert row["expires_at"] == existing["expires_at"]
    assert row["owns_hidden_version"] is True


def test_store_api_failures_still_run_ttl_and_keep_unexpired_hides(monkeypatch):
    configs = {
        'ios': {
            'hidden_versions': ['2.1.0'],
            'review_submission_entries': [active_entry('ios', '2.1.0')],
        },
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
    monkeypatch.setattr(
        lifecycle,
        '_apple_versions',
        lambda: (_ for _ in ()).throw(RuntimeError('offline')),
    )
    monkeypatch.setattr(
        lifecycle,
        '_play_production_codes',
        lambda: (_ for _ in ()).throw(lifecycle.StoreCredentialsUnavailable('missing')),
    )
    sweep_counter = Mock()
    monkeypatch.setattr(lifecycle, "OMI_APP_REVIEW_CONFIG_SWEEP_TOTAL", sweep_counter)

    summary = lifecycle.run_app_review_config_sweep(now=NOW)

    assert summary == {'expired': 1, 'repaired': 0, 'cleared': 0, 'store_errors': 2}
    assert configs['ios']['hidden_versions'] == ['2.1.0']
    assert configs['android']['hidden_versions'] == []
    assert configs['android']['review_submission_entries'][0]['state'] == 'expired'
    sweep_counter.labels.assert_called_once_with(outcome="error")


def test_reconciliation_persists_dropped_tombstone_even_when_no_hide_was_cleared(
    monkeypatch,
):
    tombstone = active_entry("ios", "2.1.0")
    tombstone["state"] = "expired"
    configs = {
        "ios": {"hidden_versions": [], "review_submission_entries": [tombstone]},
        "android": {},
    }
    writes = []
    monkeypatch.setattr(lifecycle, "_firestore_config", lambda platform: configs[platform])

    def update(platform, transform):
        configs[platform] = transform(configs[platform])
        writes.append(platform)
        return configs[platform]

    monkeypatch.setattr(lifecycle, "_update_config", update)
    monkeypatch.setattr(lifecycle, "_apple_versions", lambda: {"2.1.0": "READY_FOR_SALE"})
    monkeypatch.setattr(lifecycle, "_play_production_codes", lambda: set())
    monkeypatch.setattr(lifecycle, "OMI_APP_REVIEW_CONFIG_SWEEP_TOTAL", Mock())

    summary = lifecycle.run_app_review_config_sweep(now=NOW)

    assert summary["cleared"] == 0
    assert configs["ios"]["review_submission_entries"] == []
    assert "ios" in writes


def test_sweep_alerts_after_clearing_a_preexisting_build_qualified_ios_hide(
    monkeypatch,
):
    configs = {
        "ios": {"hidden_versions": ["2.1.0+22", "unmatched-legacy"]},
        "android": {},
    }
    monkeypatch.setattr(lifecycle, "_firestore_config", lambda platform: configs[platform])

    def update(platform, transform):
        configs[platform] = transform(configs[platform])
        return configs[platform]

    monkeypatch.setattr(lifecycle, "_update_config", update)
    monkeypatch.setattr(lifecycle, "_apple_versions", lambda: {"2.1.0": "READY_FOR_SALE"})
    monkeypatch.setattr(lifecycle, "_play_production_codes", lambda: set())
    alerts = Mock()
    monkeypatch.setattr(lifecycle, "report_lifecycle_alert", alerts)
    monkeypatch.setattr(lifecycle, "OMI_APP_REVIEW_CONFIG_SWEEP_TOTAL", Mock())

    summary = lifecycle.run_app_review_config_sweep(now=NOW)

    assert summary["cleared"] == 1
    assert configs["ios"]["hidden_versions"] == ["unmatched-legacy"]
    alerts.assert_any_call("ios", "live_hide_cleared", "count=1")


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
                        {
                            'status': 'inProgress',
                            'userFraction': 0.01,
                            'versionCodes': ['412'],
                        },
                        {"status": "draft", "versionCodes": ["413"]},
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
        'google.oauth2.service_account.Credentials.from_service_account_info',
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(lifecycle, 'AuthorizedSession', lambda _credentials: session)

    codes = lifecycle._play_production_codes()
    assert codes == {'411'}
    for version, code in (("3.0.0", '412'), ("3.0.1", "413")):
        held_config = {
            "hidden_versions": [version],
            "review_submission_entries": [active_entry("android", version, code=code)],
        }
        held_after_sweep, repairs, clears = lifecycle.reconcile_android_config(held_config, production_codes=codes)
        assert held_after_sweep["hidden_versions"] == [version]
        assert (repairs, clears) == (0, 0)
    completed_config = {
        "hidden_versions": ["3.0.2"],
        "review_submission_entries": [active_entry("android", "3.0.2", code="411")],
    }
    completed_after_sweep, repairs, clears = lifecycle.reconcile_android_config(
        completed_config, production_codes=codes
    )
    assert completed_after_sweep["hidden_versions"] == []
    assert completed_after_sweep["review_submission_entries"] == []
    assert (repairs, clears) == (0, 1)
    assert len(session.calls) == 3
    assert '/tracks/production' in session.calls[1][1]
    assert '/tracks/internal' not in str(session.calls)
    assert session.calls[2][0] == 'delete'


def test_play_edit_creation_retries_once_after_conflict(monkeypatch):
    class Response:
        def __init__(self, status, body):
            self.status_code = status
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    class Session:
        def __init__(self):
            self.posts = 0
            self.calls = []

        def post(self, url, **_kwargs):
            self.posts += 1
            self.calls.append(("post", url))
            return Response(409, {}) if self.posts == 1 else Response(200, {"id": "retry-edit"})

        def get(self, url, **_kwargs):
            self.calls.append(("get", url))
            return Response(200, {"releases": [{"status": "completed", "versionCodes": ["412"]}]})

        def delete(self, url, **_kwargs):
            self.calls.append(("delete", url))
            return Response(200, {})

    session = Session()
    monkeypatch.setattr(lifecycle, "load_secret", lambda _name: json.dumps({"type": "service_account"}))
    monkeypatch.setattr(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(lifecycle, "AuthorizedSession", lambda _credentials: session)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)

    assert lifecycle._play_production_codes() == {"412"}
    assert session.posts == 2
    assert session.calls[-1][0] == "delete"


def test_apple_reader_maps_all_paged_states_through_fake_http(monkeypatch):
    responses = [
        {
            'data': [
                {
                    'attributes': {
                        'versionString': '2.1.0',
                        'appStoreState': 'IN_REVIEW',
                    }
                },
                {
                    'attributes': {
                        'versionString': '2.0.0',
                        'appStoreState': 'READY_FOR_SALE',
                    }
                },
            ],
            'links': {'next': f"{lifecycle.APPLE_API}/apps/{lifecycle.APPLE_APP_ID}/appStoreVersions?cursor=2"},
        },
        {
            'data': [
                {
                    'attributes': {
                        'versionString': '2.2.0',
                        'appStoreState': 'WAITING_FOR_REVIEW',
                    }
                }
            ],
            'links': {},
        },
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
    expression = page['data'][0]['model']['expr']
    expected_reasons = "credentials_unavailable|store_api_error|submission_token_unavailable"
    assert f'reason=~"{expected_reasons}"' in expression
    assert f'reason=~"{expected_reasons}"' in page['annotations']['threshold']
    assert "reconciliation_repair" not in expression and "live_hide_cleared" not in expression
    deadman = rules['omi-app-review-config-sweep-silent']
    assert deadman['isPaused']
    assert deadman['noDataState'] == 'Alerting'
    assert 'omi_app_review_config_last_sweep_timestamp_seconds' in deadman['data'][0]['model']['expr']


def test_submission_endpoint_rejects_missing_and_wrong_token(monkeypatch):
    monkeypatch.setattr(router, "load_submission_token", lambda: 'expected-token')
    monkeypatch.setattr(
        router,
        'submit_review_version',
        Mock(side_effect=AssertionError('must not write')),
    )
    body = router.ReviewSubmission(platform='ios', version='2.1.0', submitted_at=datetime.now(timezone.utc))

    for token in (None, 'wrong-token', "nøt-the-token"):
        with pytest.raises(HTTPException) as error:
            asyncio.run(router.record_review_submission(body, token))
        assert error.value.status_code == 401


def test_submission_endpoint_fails_closed_when_credential_is_missing(monkeypatch):
    monkeypatch.setattr(
        router,
        "load_submission_token",
        lambda: (_ for _ in ()).throw(lifecycle.StoreCredentialsUnavailable('missing')),
    )
    body = router.ReviewSubmission(platform='ios', version='2.1.0', submitted_at=datetime.now(timezone.utc))

    with pytest.raises(HTTPException) as error:
        asyncio.run(router.record_review_submission(body, 'token'))
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {
            "platform": "ios",
            "version": "2.1.0",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "extra": "forbidden",
        },
        {
            "platform": "android",
            "version": "2.1.0",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "platform": "ios",
            "version": "2.1.0",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "version_code": "22",
        },
        {
            "platform": "ios",
            "version": "2.1",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "platform": "android",
            "version": "2.1.0",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "version_code": "0",
        },
        {"platform": "ios", "version": "2.1.0", "submitted_at": "2026-11-12T12:00:00"},
    ],
)
def test_submission_body_rejects_invalid_or_extra_fields(payload):
    with pytest.raises(ValidationError):
        router.ReviewSubmission.model_validate(payload)


def test_submission_endpoint_success_writes_exact_identity(monkeypatch):
    monkeypatch.setattr(router, "load_submission_token", lambda: "expected-token")
    write = Mock(return_value={"accepted": True, "expires_at": "2026-11-26T12:00:00Z"})
    monkeypatch.setattr(router, "submit_review_version", write)
    body = router.ReviewSubmission(
        platform="android",
        version="2.1.0",
        version_code="412",
        submitted_at=datetime.now(timezone.utc),
    )

    response = router.record_review_submission(body, "expected-token")

    assert response == {"accepted": True, "expires_at": "2026-11-26T12:00:00Z"}
    write.assert_called_once_with("android", "2.1.0", "412")


def test_submission_endpoint_returns_conflict_if_active_lease_disappears(monkeypatch):
    monkeypatch.setattr(router, "load_submission_token", lambda: "expected-token")
    monkeypatch.setattr(
        router,
        "submit_review_version",
        Mock(side_effect=lifecycle.SubmissionConfigConflict("missing")),
    )
    body = router.ReviewSubmission(platform="ios", version="2.1.0", submitted_at=datetime.now(timezone.utc))

    with pytest.raises(HTTPException) as error:
        router.record_review_submission(body, "expected-token")
    assert error.value.status_code == 409


def test_submission_endpoint_rejects_stale_receipt_before_writing(monkeypatch):
    monkeypatch.setattr(router, "load_submission_token", lambda: "expected-token")
    write = Mock(side_effect=AssertionError("stale receipt must not write"))
    monkeypatch.setattr(router, "submit_review_version", write)
    body = router.ReviewSubmission(
        platform="ios",
        version="2.1.0",
        submitted_at=datetime.now(timezone.utc) - timedelta(minutes=16),
    )

    with pytest.raises(HTTPException) as error:
        router.record_review_submission(body, "expected-token")
    assert error.value.status_code == 409
    write.assert_not_called()


def test_submission_secret_is_cached_in_process_for_sixty_seconds(monkeypatch):
    values = iter(["cached-token", "rotated-token"])
    reads = Mock(side_effect=lambda _name: next(values))
    clock = Mock(side_effect=[100.0, 101.0, 161.0])
    monkeypatch.setattr(lifecycle, "load_secret", reads)
    monkeypatch.setattr(lifecycle.time, "monotonic", clock)
    monkeypatch.setattr(lifecycle, "_submission_secret_cache", None)

    assert lifecycle.load_submission_token() == "cached-token"
    assert lifecycle.load_submission_token() == "cached-token"
    assert lifecycle.load_submission_token() == "rotated-token"
    assert reads.call_count == 2


def test_submission_receipt_timestamp_has_a_bounded_age_and_future_skew():
    assert lifecycle.is_recent_submission_timestamp(NOW, now=NOW)
    assert not lifecycle.is_recent_submission_timestamp(NOW - timedelta(minutes=16), now=NOW)
    assert not lifecycle.is_recent_submission_timestamp(NOW + timedelta(minutes=6), now=NOW)
    assert not lifecycle.is_recent_submission_timestamp(datetime(2026, 11, 12, 12, 0), now=NOW)


def test_missing_submission_secret_is_negative_cached(monkeypatch):
    reads = Mock(side_effect=lifecycle.StoreCredentialsUnavailable("missing"))
    monkeypatch.setattr(lifecycle, "load_secret", reads)
    monkeypatch.setattr(lifecycle.time, "monotonic", Mock(side_effect=[100.0, 101.0]))
    monkeypatch.setattr(lifecycle, "_submission_secret_cache", None)

    for _ in range(2):
        with pytest.raises(lifecycle.StoreCredentialsUnavailable):
            lifecycle.load_submission_token()
    assert reads.call_count == 1


def test_submission_endpoint_is_ip_rate_limited_and_policy_is_declared(monkeypatch):
    monkeypatch.setattr(endpoint_utils, "cached", {})
    monkeypatch.setattr(router, "load_submission_token", lambda: "expected-token")
    monkeypatch.setattr(
        router,
        "submit_review_version",
        lambda *_args: {"accepted": True, "expires_at": "soon"},
    )
    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)

    statuses = [
        client.post(
            "/v2/internal/app-review-config/submissions",
            headers={"X-Review-Config-Token": "expected-token"},
            json={
                "platform": "ios",
                "version": "2.1.0",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
        ).status_code
        for _ in range(11)
    ]

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
    policies = yaml.safe_load((BACKEND_ROOT / "route_policy_manifest.yaml").read_text())["routes"]
    route = next(row for row in policies if row.get("path") == "/v2/internal/app-review-config/submissions")
    assert route["policy"]["rate_limit"] == {
        "policy_name": "app_review_config_submission",
        "key_subject": "ip",
        "enforcement": "fail_closed",
        "placement": "dependency",
    }


def test_codemagic_submission_group_is_limited_to_the_two_review_workflows():
    config = yaml.safe_load((BACKEND_ROOT.parent / "codemagic.yaml").read_text())
    attached = {
        name
        for name, workflow in config["workflows"].items()
        if "app_review_config" in workflow.get("environment", {}).get("groups", [])
    }

    assert attached == {"mobile-store-promote", "mobile-daily-train"}


def _load_script(name: str):
    path = APP_ROOT / name
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
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
        seen.append(
            (
                request.full_url,
                json.loads(request.data),
                request.get_header('X-review-config-token'),
            )
        )
        return Response()

    staging_endpoint = "https://staging.example.test/v2/internal/app-review-config/submissions"
    monkeypatch.setenv("APP_REVIEW_CONFIG_ENDPOINT", staging_endpoint)
    assert hook.post_receipts(receipt, opener=opener) == 0
    assert len(seen) == 1
    sent_url, payload, sent_token = seen[0]
    assert sent_url == staging_endpoint
    assert payload["platform"] == "android"
    assert payload["version"] == "3.0.0"
    assert payload["version_code"] == "412"
    assert isinstance(payload["submitted_at"], str) and payload["submitted_at"].endswith("Z")
    assert sent_token == 'do-not-print-token'
    output = capsys.readouterr()
    assert 'do-not-print-token' not in output.out + output.err


def test_hook_missing_token_or_server_error_is_nonfatal_after_store_submission(tmp_path, monkeypatch, capsys):
    hook = _load_script("app_review_config_hook.py")
    receipt = tmp_path / "receipt.json"
    receipt.write_text('[{"platform":"ios","version":"2.1.0"}]', encoding="utf-8")
    monkeypatch.delenv("APP_REVIEW_CONFIG_SUBMISSION_TOKEN", raising=False)
    assert hook.post_receipts(receipt, opener=lambda *_a, **_k: pytest.fail("must not send without token")) == 0

    monkeypatch.setenv("APP_REVIEW_CONFIG_SUBMISSION_TOKEN", "token")

    class ErrorResponse:
        status = 500
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    assert hook.post_receipts(receipt, opener=lambda *_a, **_k: ErrorResponse()) == 0
    output = capsys.readouterr()
    assert "submission token is missing" in output.err
    assert "continuing after store submission" in output.err


def test_corrupt_submission_receipt_does_not_fail_after_store_submission(tmp_path, monkeypatch, capsys):
    promote = _load_script("mobile_store_promote.py")
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setenv("APP_REVIEW_CONFIG_SUBMISSION_RECEIPT", str(receipt))

    promote.record_review_submission("ios", "2.1.0")

    assert "store submission already succeeded" in capsys.readouterr().err
