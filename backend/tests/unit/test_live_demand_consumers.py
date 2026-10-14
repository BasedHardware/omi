"""Consumer absence must be established from real fanout authorities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.stt import demand_consumers
from database import redis_db, notifications
from utils import mentor_admission
from utils import apps, executors


@pytest.mark.asyncio
@pytest.mark.parametrize('consumer', ['none', 'app', 'audio_app', 'webhook', 'mentor', 'mentor_off', 'mentor_free'])
async def test_active_consumers_require_vendor(monkeypatch, consumer):
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort' if consumer.startswith('mentor') else 'off')
    monkeypatch.setattr(executors, 'run_blocking', AsyncMock(side_effect=lambda pool, fn, *args: fn(*args)))
    monkeypatch.setattr(
        notifications, 'get_mentor_notification_frequency', lambda uid: 0 if consumer == 'mentor_off' else 3
    )
    monkeypatch.setattr(mentor_admission, 'mentor_plan_allows_evaluation', lambda uid: consumer != 'mentor_free')
    app = SimpleNamespace(
        enabled=True,
        triggers_realtime=lambda: consumer == 'app',
        triggers_realtime_audio_bytes=lambda: consumer == 'audio_app',
    )
    monkeypatch.setattr(apps, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(redis_db, 'user_webhook_status_db', lambda uid, kind: consumer == 'webhook')
    monkeypatch.setattr(redis_db, 'get_user_webhook_db', lambda uid, kind: 'https://example.invalid/hook')
    assert await demand_consumers.realtime_consumer_active('user') == (
        consumer not in {'none', 'mentor_off', 'mentor_free'}
    )
