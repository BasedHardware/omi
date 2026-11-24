"""Pipeline lab, lane chain: capture-only sinks (FCM would-have-fired log, HTTP egress, leaves)."""

import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import json

import httpx

from testing.pipeline_lab.sinks.capture import (
    SCOPE_CONVERSATION_HEADER,
    SCOPE_STAGE_HEADER,
    CaptureSinks,
    capture_scope,
    current_scope,
    decode_message,
)

AT = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
PROXY = 'http://127.0.0.1:9180'


def _sinks(tmp_path):
    return CaptureSinks(run_dir=tmp_path, clock=lambda: AT, allowed_ports=frozenset({9180}), proxy_url=PROXY)


def test_scope_is_contextual_with_a_thread_fallback():
    assert current_scope()['scope_source'] == 'none'
    with capture_scope('c1', 'finalize'):
        assert current_scope() == {'conversation_id': 'c1', 'stage': 'finalize', 'scope_source': 'context'}
        with capture_scope('c2', 'daily_summary'):
            assert current_scope()['conversation_id'] == 'c2'
        assert current_scope()['conversation_id'] == 'c1'
    assert current_scope()['scope_source'] == 'none'


def test_real_product_push_lands_in_the_would_have_fired_log(tmp_path, monkeypatch):
    from firebase_admin import messaging
    from utils import notifications

    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', lambda uid: False)
    sinks = _sinks(tmp_path)
    with ExitStack() as stack:
        sinks.install(stack, http=False, leaves=False)
        with capture_scope('conv-7', 'finalize'):
            sent = notifications._send_to_user(
                'local-dev-user',
                'reminder',
                notification=messaging.Notification(title='Order seeds', body='Due tomorrow'),
                data={'type': 'action_item_reminder', 'due_at': '2026-03-15T09:00:00Z'},
                tokens=['pipeline-lab-synthetic-fcm-token'],
            )
    assert sent == 1
    row = sinks.notifications[0]
    assert row['title'] == 'Order seeds' and row['body'] == 'Due tomorrow'
    assert row['conversation_id'] == 'conv-7' and row['trigger'] == 'finalize'
    assert row['fire_at'] == '2026-03-15T09:00:00Z' and row['at'] == '2026-03-14T10:00:00Z'
    assert row['token_class'] == 'synthetic' and row['kind'] == 'alert'
    assert row['caller'].startswith('utils.notifications:')
    logged = [json.loads(line) for line in (tmp_path / 'notifications.jsonl').read_text().splitlines()]
    assert logged == sinks.notifications
    assert messaging.send_each.__module__ == 'firebase_admin.messaging'  # restored


def test_decode_handles_data_only_messages():
    decoded = decode_message({'token': 'other', 'data': {'type': 'reminder_cancel', 'title': 'x'}})
    assert decoded['kind'] == 'data' and decoded['data_type'] == 'reminder_cancel'
    assert decoded['token_class'] == 'other'


def test_http_egress_is_captured_and_proxy_calls_are_tagged(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={'ok': True})

    sinks = _sinks(tmp_path)
    with ExitStack() as stack:
        sinks.install(stack, fcm=False, leaves=False)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with capture_scope('conv-1', 'notes'):
            proxied = client.post(f'{PROXY}/v1/chat/completions', json={})
            external = client.post('https://hooks.example.com/hook?uid=secret-uid', json={'a': 1})
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        asyncio.run(async_client.get('https://integrations.example.org/x'))
    assert proxied.status_code == 201 and external.status_code == 200
    assert len(seen) == 1
    assert seen[0].headers[SCOPE_CONVERSATION_HEADER] == 'conv-1'
    assert seen[0].headers[SCOPE_STAGE_HEADER] == 'notes'
    destinations = [row['destination'] for row in sinks.egress]
    assert destinations == ['https://hooks.example.com/hook', 'https://integrations.example.org/x']
    assert 'secret-uid' not in (tmp_path / 'sinks_egress.jsonl').read_text()
    assert sinks.egress[0]['conversation_id'] == 'conv-1'


def test_named_leaves_capture_webhooks_task_sync_and_telemetry(tmp_path):
    from utils import product_telemetry, task_sync, webhooks

    sinks = _sinks(tmp_path)
    with ExitStack() as stack:
        sinks.install(stack, fcm=False, http=False)
        response = asyncio.run(webhooks._post_dev_webhook('conversation_created', 'https://dev.example.com/wh'))
        synced = asyncio.run(task_sync._sync_to_cloud_service('local-dev-user', 'todoist', {}, {'id': 't1'}))
        product_telemetry.emit_product_event(uid='local-dev-user', event='conversation_finalized', properties={})
    assert response.status_code == 200
    assert synced['synced'] is True and synced['reason'] == 'pipeline_lab_captured'
    assert [row['channel'] for row in sinks.egress] == ['webhook', 'task_sync']
    assert sinks.telemetry[0]['event'] == 'conversation_finalized'
    assert webhooks._post_dev_webhook.__name__ == '_post_dev_webhook'
