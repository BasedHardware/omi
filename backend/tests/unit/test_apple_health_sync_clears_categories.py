"""Apple Health writes merge into the stored map, so a sync has to clear what it did not send.

Without that, a week with no workouts (or a HealthKit category the user revoked) keeps serving
the previous values, and the chat tools print them under a freshly written last_synced.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import pytest

import routers.integrations as integrations_router
from routers.integrations import AppleHealthSyncData, sync_apple_health_data


@pytest.fixture
def stored(monkeypatch):
    writes = []
    monkeypatch.setattr(
        integrations_router.users_db,
        'set_integration',
        lambda _uid, _app_key, data: writes.append(data),
    )
    return writes


def test_a_sync_without_workouts_clears_the_stored_workouts(stored):
    response = sync_apple_health_data(AppleHealthSyncData(period_days=7, total_steps=4000), uid='u1')

    health_data = stored[0]['health_data']
    assert health_data['workouts'] == []
    assert health_data['heart_rate'] == {}
    assert health_data['steps']['total'] == 4000
    # The client is still told only what this sync actually carried.
    assert response['data_types_synced'] == ['period_days', 'steps']


def test_a_sync_keeps_the_categories_it_carries(stored):
    sync_apple_health_data(
        AppleHealthSyncData(
            period_days=7,
            total_steps=4000,
            heart_rate_average=61.0,
            workouts=[{'type': 'run', 'duration': 30}],
        ),
        uid='u1',
    )

    health_data = stored[0]['health_data']
    assert health_data['heart_rate']['average'] == 61.0
    assert health_data['workouts'] == [{'type': 'run', 'duration': 30}]
