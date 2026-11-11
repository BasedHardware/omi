import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from routers.users import ButtonEventRequest, post_developer_button_event


@pytest.mark.asyncio
async def test_button_event_route_forwards_validated_contract():
    body = ButtonEventRequest.model_validate(
        {
            'button_event': 'double_tap',
            'device_id': 'omi-1',
            'event_id': 'a02765ac-c962-4118-bfcc-a06c0d7750d9',
            'timestamp': '2026-08-21T04:15:00Z',
            'session_id': 'session-1',
        }
    )

    with patch('routers.users.button_event_webhook', new_callable=AsyncMock) as mock_webhook:
        response = await post_developer_button_event(body, uid='uid-1')

    assert response == {'status': 'ok'}
    mock_webhook.assert_awaited_once_with(
        'uid-1',
        button_event='double_tap',
        device_id='omi-1',
        event_id='a02765ac-c962-4118-bfcc-a06c0d7750d9',
        timestamp='2026-08-21T04:15:00+00:00',
        session_id='session-1',
    )


def test_button_event_contract_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        ButtonEventRequest.model_validate(
            {
                'button_event': 'single_tap',
                'device_id': 'omi-1',
                'event_id': 'a02765ac-c962-4118-bfcc-a06c0d7750d9',
                'timestamp': '2026-08-21T04:15:00',
            }
        )


@pytest.mark.asyncio
async def test_button_events_keep_stable_id_and_serialize_per_device(monkeypatch):
    from utils import webhooks

    monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
    monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value='https://example.com/hook'))
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())
    circuit_breaker = MagicMock()
    circuit_breaker.allow_request.return_value = True
    monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', MagicMock(return_value=circuit_breaker))

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    delivered: list[str] = []

    async def post_webhook(_name, _url, *, json, idempotency_key, **_kwargs):
        delivered.append(idempotency_key)
        if idempotency_key == 'event-1':
            first_started.set()
            await release_first.wait()
        return MagicMock(status_code=200)

    monkeypatch.setattr(webhooks, '_post_dev_webhook', post_webhook)

    first = asyncio.create_task(
        webhooks.button_event_webhook(
            'uid-1',
            button_event='single_tap',
            device_id='omi-1',
            event_id='event-1',
            timestamp='2026-08-21T04:15:00Z',
        )
    )
    await first_started.wait()
    second = asyncio.create_task(
        webhooks.button_event_webhook(
            'uid-1',
            button_event='double_tap',
            device_id='omi-1',
            event_id='event-2',
            timestamp='2026-08-21T04:15:01Z',
        )
    )
    await asyncio.sleep(0)

    assert delivered == ['event-1']
    release_first.set()
    await asyncio.gather(first, second)
    assert delivered == ['event-1', 'event-2']


@pytest.mark.asyncio
async def test_button_event_is_noop_when_not_configured(monkeypatch):
    from utils import webhooks

    monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=False))
    post_webhook = AsyncMock()
    monkeypatch.setattr(webhooks, '_post_dev_webhook', post_webhook)

    await webhooks.button_event_webhook(
        'uid-1',
        button_event='long_tap',
        device_id='omi-1',
        event_id='event-1',
        timestamp='2026-08-21T04:15:00Z',
    )

    post_webhook.assert_not_awaited()
