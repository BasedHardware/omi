"""Daily recap depth is a persisted account preference, not a client-only switch."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from routers import users


def test_get_settings_defaults_to_brief_for_legacy_accounts(monkeypatch):
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_enabled', lambda _uid: True)
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_hour_local', lambda _uid: None)
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_depth', lambda _uid: 'brief', raising=False)

    settings = users.get_daily_summary_settings(uid='user-1')

    assert settings.enabled is True
    assert settings.hour == users.notification_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL
    assert settings.depth == 'brief'


@pytest.mark.parametrize('depth', ['brief', 'normal', 'deep'])
def test_patch_settings_persists_each_supported_depth(monkeypatch, depth):
    save_depth = Mock(return_value=True)
    monkeypatch.setattr(users.notification_db, 'set_daily_summary_depth', save_depth, raising=False)

    response = users.update_daily_summary_settings(users.DailySummarySettingsUpdate(depth=depth), uid='user-1')

    assert response == {'status': 'ok', 'depth': depth}
    save_depth.assert_called_once_with('user-1', depth)


def test_patch_settings_rejects_unsupported_depth():
    with pytest.raises(ValidationError):
        users.DailySummarySettingsUpdate(depth='verbose')


def test_http_settings_round_trip_uses_the_same_depth_contract(monkeypatch):
    saved = {'value': 'brief'}
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_enabled', lambda _uid: True)
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_hour_local', lambda _uid: 22)
    monkeypatch.setattr(users.notification_db, 'get_daily_summary_depth', lambda _uid: saved['value'])
    monkeypatch.setattr(
        users.notification_db,
        'set_daily_summary_depth',
        lambda _uid, value: saved.update(value=value) or True,
    )
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.auth.get_current_user_uid] = lambda: 'user-1'
    client = TestClient(app)

    assert client.get('/v1/users/daily-summary-settings').json()['depth'] == 'brief'
    mutation = client.patch('/v1/users/daily-summary-settings', json={'depth': 'deep'}).json()
    assert mutation['status'] == 'ok'
    assert mutation['depth'] == 'deep'
    assert client.get('/v1/users/daily-summary-settings').json()['depth'] == 'deep'
    assert client.patch('/v1/users/daily-summary-settings', json={'depth': 'unsupported'}).status_code == 422
    assert saved['value'] == 'deep'
