"""Response-owned voice pushes survive terminal SSE disconnects without sending early."""

import asyncio
import logging
import sys
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import ClientDisconnect

from tests.unit import _chat_router_test_harness as harness
from tests.unit.test_chat_answer_client_displayed_notification import _loaded_notifications
from tests.unit.test_chat_stream_error_fallback import _cleanup, _decode_done_frame, _make_client


@pytest.fixture
def environment():
    client, router, chat, chat_db, saved = _make_client()
    try:
        # Keep the real generator, message models and FCM construction/cleanup.
        # Only database, provider SDK and transcription boundaries are fixtures.
        model = harness.load_real_module(
            'models.notification_message', harness.BACKEND_DIR / 'models/notification_message.py'
        )
        chat.NotificationMessage = model.NotificationMessage
        chat._test_router = router
        router.enforce_chat_quota = MagicMock()
        router.retrieve_file_paths = lambda *args: ['/tmp/synthetic.opus']
        router.decode_files_to_wav = lambda *args: ['/tmp/decoded.wav']
        router.read_wav_duration_ms = lambda *args: 1000
        router.try_consume_budget = lambda *args: (True, 0, 1000)
        router._cleanup_temp_voice_wavs = MagicMock()
        usage = ContextVar('voice-test-usage', default=None)
        chat.set_usage_context = lambda *args: usage.set('synthetic-uid')
        chat.reset_usage_context = MagicMock(side_effect=usage.reset)
        sys.modules['utils.executors'].postprocess_executor = MagicMock()
        harness.install_module('utils.integration_telemetry', MagicMock())
        with _loaded_notifications() as notifications:
            chat.send_client_displayed_notification_async = notifications.send_client_displayed_notification_async
            notifications._emit_tokens_invalidated = MagicMock()
            yield chat, chat_db, notifications
    finally:
        _cleanup(saved)


def _stage_answer(chat, branch):
    async def graph(*args, **kwargs):
        kwargs['callback_data']['answer'] = 'A synthetic pendant answer.'
        yield 'data: A synthetic pendant answer.'
        if branch == 'staged_error':
            kwargs['callback_data']['error'] = 'idle_timeout'
            yield 'error: synthetic failure'
        elif branch == 'sentinel':
            # Repeated completion signals must not re-save or re-send the answer.
            yield None
        yield None if branch != 'generator_end' else 'think: complete'

    chat.execute_graph_chat_stream = graph


async def _receive_answer(chat, close_at_done, *, spec='2.4', middleware=False):
    router = chat._test_router
    response = router.create_voice_message_stream(files=[], uid='synthetic-uid', language='en', x_app_platform='ios')
    frames = []
    disconnected = asyncio.Event()
    chat._terminal_send_seen = False

    async def send(event):
        if event['type'] != 'http.response.body':
            return
        if close_at_done and disconnected.is_set():
            raise OSError('synthetic client disconnect')
        body = event.get('body', b'').decode()
        frames.append(body)
        if body.startswith('done: '):
            chat._terminal_send_seen = True
            if close_at_done:
                disconnected.set()
                await asyncio.sleep(0)  # Let ASGI <=2.3's disconnect watcher cancel iteration.

    async def receive():
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def app(scope, receive, send):
        await response(scope, receive, send)

    if middleware:
        timeout = harness.load_real_module('utils.other.timeout', harness.BACKEND_DIR / 'utils/other/timeout.py')
        app = timeout.TimeoutMiddleware(app)
    scope = {
        'type': 'http',
        'asgi': {'spec_version': spec},
        'method': 'POST',
        'path': '/v2/voice-messages',
        'headers': [],
        'query_string': b'',
    }
    try:
        await app(scope, receive, send)
    except (ClientDisconnect, OSError):
        assert close_at_done
    await response._delivery.dispatch()  # A repeated cleanup cannot dispatch twice.
    assert sum(frame.startswith('done: ') for frame in frames) == 1
    router._cleanup_temp_voice_wavs.assert_called_once()
    chat.reset_usage_context.assert_called_once()
    return _decode_done_frame(''.join(frames))


@pytest.mark.parametrize('branch', ['sentinel', 'staged_error', 'generator_end'])
@pytest.mark.parametrize('close_at_done', [True, False])
@pytest.mark.parametrize('spec', ['2.3', '2.4'])
def test_terminal_notification_follows_send_and_uses_saved_identity(environment, caplog, branch, close_at_done, spec):
    chat, chat_db, notifications = environment
    _stage_answer(chat, branch)
    sent = []

    def send(messages):
        assert chat._terminal_send_seen, 'FCM must not be awaited before terminal transport send'
        sent.extend(messages)
        return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

    notifications.messaging.send_each = send
    with caplog.at_level(logging.INFO):
        payload = asyncio.run(_receive_answer(chat, close_at_done, spec=spec))

    writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1]['sender'] == 'ai']
    assert len(writes) == len(sent) == 1
    assert sent[0].data['id'] == payload['id'] == writes[0]['id']
    assert sent[0].data['text'] == payload['text'] == writes[0]['text']
    assert sent[0].data['navigate_to'] == '/chat/omi'
    assert sent[0].data['push_type'] == 'chat_answer'
    _assert_outcome_log(caplog, payload['id'], 'accepted', 'none')


@pytest.mark.parametrize('branch', ['sentinel', 'staged_error', 'generator_end'])
@pytest.mark.parametrize(
    'failure',
    [
        'provider_exception',
        'provider_rejection',
        'unregistered',
        'no_tokens',
        'suppressed',
        'lookup_exception',
        'timeout',
    ],
)
def test_notification_failure_never_discards_the_terminal_answer(environment, monkeypatch, caplog, branch, failure):
    chat, chat_db, notifications = environment
    _stage_answer(chat, branch)
    removed = []
    notifications.notification_db.remove_bulk_tokens = removed.extend

    def send(messages):
        if failure == 'provider_exception':
            raise RuntimeError('synthetic provider rejection device-token A synthetic pendant answer.')
        code = 'UNREGISTERED' if failure == 'unregistered' else 'UNAVAILABLE'
        return SimpleNamespace(
            responses=[SimpleNamespace(success=False, exception=SimpleNamespace(code=code, detail='device-token'))]
        )

    notifications.messaging.send_each = send
    if failure == 'no_tokens':
        notifications.notification_db.get_all_tokens = lambda uid: []
    elif failure == 'suppressed':
        notifications.account_deletion_blocks_user_work = lambda uid: True
    elif failure == 'lookup_exception':
        notifications.notification_db.get_all_tokens = MagicMock(side_effect=RuntimeError('synthetic lookup failure'))
    elif failure == 'timeout':
        cancelled = []

        async def blocked(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        chat.send_chat_message_notification_async = blocked
        monkeypatch.setattr(
            sys.modules['utils.voice_answer_delivery'], 'VOICE_ANSWER_NOTIFICATION_TIMEOUT_SECONDS', 0.01
        )

    async def bounded_answer():
        return await asyncio.wait_for(_receive_answer(chat, True), timeout=1)

    with caplog.at_level(logging.INFO):
        payload = asyncio.run(bounded_answer())
    writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1]['sender'] == 'ai']
    assert len(writes) == 1
    assert payload['id'] == writes[0]['id']
    assert payload['text'] == 'A synthetic pendant answer.'
    assert removed == (['device-token'] if failure == 'unregistered' else [])
    if failure == 'timeout':
        assert cancelled == [True]
    if failure in ('lookup_exception', 'timeout'):
        assert chat.record_fallback.call_args.kwargs['outcome'] == 'degraded'
    elif branch != 'staged_error':
        chat.record_fallback.assert_not_called()
    outcome, error_type = {
        'lookup_exception': ('failed', 'RuntimeError'),
        'timeout': ('indeterminate', 'TimeoutError'),
    }.get(failure, ('no_acceptance', 'none'))
    _assert_outcome_log(caplog, payload['id'], outcome, error_type)
    assert 'synthetic provider rejection' not in caplog.text
    assert 'synthetic lookup failure' not in caplog.text


def _assert_outcome_log(caplog, message_id, outcome, error_type):
    records = [record.getMessage() for record in caplog.records if record.name == 'utils.voice_answer_delivery']
    terminal_logs = [line for line in records if line.startswith('voice answer notification ')]
    assert terminal_logs == [
        f'voice answer notification message_id={message_id} outcome={outcome} error_type={error_type}'
    ]
    assert 'A synthetic pendant answer.' not in caplog.text
    assert 'device-token' not in caplog.text


def test_repeated_notification_id_keeps_existing_collapse_identity(environment):
    chat, chat_db, notifications = environment
    sent = []
    notifications.messaging.send_each = lambda messages: (
        sent.extend(messages) or SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])
    )

    async def repeat():
        for _ in range(2):
            await chat.send_chat_message_notification_async(
                'synthetic-uid', 'omi', 'omi', 'Synthetic answer', 'same-id'
            )

    asyncio.run(repeat())
    assert len(sent) == 2  # Existing transport uses collapse identity, not server-side exactly-once delivery.
    assert sent[0].data['id'] == sent[1].data['id'] == 'same-id'
    assert sent[0].apns.headers['apns-collapse-id'] == sent[1].apns.headers['apns-collapse-id']


def test_one_provider_acceptance_is_reported_when_another_registration_fails(environment, caplog):
    chat, chat_db, notifications = environment
    _stage_answer(chat, 'sentinel')
    notifications.notification_db.get_all_tokens = lambda uid: ['device-token', 'second-token']
    notifications.messaging.send_each = lambda messages: SimpleNamespace(
        responses=[
            SimpleNamespace(success=True, exception=None),
            SimpleNamespace(success=False, exception=SimpleNamespace(code='UNAVAILABLE')),
        ]
    )
    with caplog.at_level(logging.INFO):
        payload = asyncio.run(_receive_answer(chat, True))
    _assert_outcome_log(caplog, payload['id'], 'accepted', 'none')


def test_token_cleanup_failure_keeps_the_known_acceptance(environment, caplog):
    chat, chat_db, notifications = environment
    _stage_answer(chat, 'sentinel')
    notifications.notification_db.get_all_tokens = lambda uid: ['device-token', 'second-token']
    notifications.notification_db.remove_bulk_tokens = MagicMock(side_effect=RuntimeError('synthetic cleanup failure'))
    send = MagicMock(
        return_value=SimpleNamespace(
            responses=[
                SimpleNamespace(success=True, exception=None),
                SimpleNamespace(success=False, exception=SimpleNamespace(code='UNREGISTERED')),
            ]
        )
    )
    notifications.messaging.send_each = send
    with caplog.at_level(logging.INFO):
        payload = asyncio.run(_receive_answer(chat, True))
    send.assert_called_once()
    _assert_outcome_log(caplog, payload['id'], 'accepted', 'none')


@pytest.mark.parametrize('spec', ['2.3', '2.4'])
@pytest.mark.parametrize('close_at_done', [True, False])
def test_actual_timeout_middleware_keeps_response_owned_push(environment, spec, close_at_done):
    chat, chat_db, notifications = environment
    _stage_answer(chat, 'sentinel')
    send = MagicMock(return_value=SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)]))
    notifications.messaging.send_each = send
    asyncio.run(_receive_answer(chat, close_at_done, spec=spec, middleware=True))
    send.assert_called_once()


@pytest.mark.parametrize('registered', [False, True])
def test_outer_request_cancellation_keeps_only_an_already_registered_answer(environment, registered):
    chat, chat_db, notifications = environment
    module = sys.modules['utils.voice_answer_delivery']
    entered = asyncio.Event()
    send = AsyncMock(return_value=1)
    delivery = module.VoiceAnswerDelivery()

    async def stream():
        if registered:
            delivery.register('same-id', send)
        entered.set()
        await asyncio.Event().wait()
        yield 'never'

    async def cancel():
        async def receive():
            await asyncio.Event().wait()

        response = module.VoiceAnswerStreamingResponse(stream(), delivery)
        task = asyncio.create_task(response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, AsyncMock()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await delivery.dispatch()

    asyncio.run(cancel())
    assert send.await_count == int(registered)
