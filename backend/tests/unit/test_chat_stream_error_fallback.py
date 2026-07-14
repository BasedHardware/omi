"""Regression tests for graceful fallback when the chat stream fails mid-turn.

Before the fix, when the LLM/tool pipeline raised mid-stream the backend swallowed
the exception and ended the SSE stream as a clean 200 with zero bytes -- no chunks,
no ``done:`` frame -- so every client rendered a blank assistant bubble. These tests
load the real ``utils.chat`` and ``routers.chat`` (heavy deps stubbed) and assert the
stream now ends with a ``done:`` frame carrying real fallback text, and that the
fallback AI reply is persisted like the quota-exceeded precedent.
"""

import asyncio
import base64
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit import _chat_router_test_harness as harness
from tests.unit._chat_router_test_harness import BACKEND_DIR


def _install(name: str, module=None):
    """This suite stubs bare modules as empty ``ModuleType`` (not auto-mocking
    ``MagicMock``) so that ``from X import Y`` on the real ``utils.chat`` /
    ``routers.chat`` fails loudly when a required name is not wired."""
    return harness.install_module(name, module, default_factory=lambda n: ModuleType(n))


def _make_client():
    """Load real models.chat + utils.chat + routers.chat with heavy deps stubbed."""
    saved = {k: v for k, v in sys.modules.items()}

    harness.install_package('models', BACKEND_DIR / 'models')
    harness.install_package('database', BACKEND_DIR / 'database')
    harness.install_package('utils', BACKEND_DIR / 'utils')
    harness.install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    harness.install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    harness.install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    harness.install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    harness.install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')
    harness.install_package('utils.conversations', BACKEND_DIR / 'utils' / 'conversations')

    common = harness.wire_common_stubs(_install)
    chat_db = common.chat_db

    # Scenario-specific stubs: this suite loads the *real* utils.chat + routers.chat,
    # so every name they import must be wired (heavier than the quota suite).
    models_app = _install('models.app')
    models_app.App = MagicMock()
    models_app.UsageHistoryType = MagicMock()
    nm = _install('models.notification_message')
    nm.NotificationMessage = MagicMock()
    ts = _install('models.transcript_segment')
    ts.TranscriptSegment = MagicMock()

    chat_db.get_chat_session_by_id = MagicMock(return_value=None)
    chat_db.add_chat_session = MagicMock(side_effect=lambda uid, data: data)
    _install('database.notifications')

    factory = _install('utils.conversations.factory')
    factory.deserialize_conversation = MagicMock()
    llm_chat = _install('utils.llm.chat')
    llm_chat.initial_chat_message = MagicMock(return_value='hi')
    llm_persona = _install('utils.llm.persona')
    llm_persona.initial_persona_chat_message = MagicMock(return_value='hi')
    notifications = _install('utils.notifications')
    notifications.send_notification = MagicMock()

    fallback_obs = _install('utils.observability.fallback')
    fallback_obs.record_fallback = MagicMock()

    pre_recorded = _install('utils.stt.pre_recorded')
    pre_recorded.get_deepgram_model_for_language = MagicMock(return_value=('en', 'nova-2'))
    pre_recorded.postprocess_words = MagicMock(return_value=[SimpleNamespace(text='hello')])
    pre_recorded.prerecorded = MagicMock(return_value=[])
    pre_recorded.prerecorded_from_bytes = MagicMock(return_value=[])

    common.usage_tracker.track_usage = MagicMock()

    # utils.retrieval.graph is imported by both utils.chat and routers.chat -- stub it
    # so tests can install per-scenario streaming behaviour.
    graph = _install('utils.retrieval.graph')
    graph.execute_graph_chat = MagicMock()
    graph.execute_graph_chat_stream = MagicMock()
    graph.execute_chat_stream = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    chat_utils = harness.load_real_module('utils.chat', BACKEND_DIR / 'utils' / 'chat.py')

    sys.modules.pop('routers.chat', None)
    router_module = harness.load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)
    return client, router_module, chat_utils, chat_db, saved


def _cleanup(saved):
    harness.cleanup(saved)


def _decode_done_frame(text: str) -> dict:
    for block in text.split('\n\n'):
        block = block.strip()
        if block.startswith('done: '):
            payload = block[len('done: ') :]
            return json.loads(base64.b64decode(payload).decode('utf-8'))
    raise AssertionError(f'no done: frame in stream: {text!r}')


def test_v2_messages_emits_fallback_done_frame_on_pipeline_error():
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:

        async def failing_stream(*args, **kwargs):
            kwargs['callback_data']['error'] = 'boom: internal detail'
            yield None  # signal completion with no answer set

        router_module.execute_chat_stream = failing_stream

        response = client.post(
            '/v2/messages',
            json={'text': 'hello', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        payload = _decode_done_frame(response.text)
        assert payload['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
        assert payload['sender'] == 'ai'
        # Raw exception detail must never reach the client.
        assert 'boom' not in response.text

        # The fallback AI reply is persisted (mirrors _build_quota_exceeded_reply).
        ai_writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai']
        assert len(ai_writes) == 1
        assert ai_writes[0]['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT

        # Fail-open correctness degrade is recorded once, as a persisted degrade.
        chat_utils.record_fallback.assert_called_once()
        assert chat_utils.record_fallback.call_args.kwargs['outcome'] == 'degraded'
    finally:
        _cleanup(saved)


def test_v2_messages_normal_answer_still_emits_single_done_frame():
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:

        async def ok_stream(*args, **kwargs):
            yield 'thinking'
            kwargs['callback_data']['answer'] = 'here is your answer'
            yield None

        router_module.execute_chat_stream = ok_stream

        response = client.post(
            '/v2/messages',
            json={'text': 'hello', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        assert response.text.count('done: ') == 1
        payload = _decode_done_frame(response.text)
        assert payload['text'] == 'here is your answer'
        # No fallback text leaks into a successful turn.
        assert chat_utils.CHAT_STREAM_ERROR_TEXT not in response.text
        # A successful turn is not a fallback -- the emitter must not fire.
        chat_utils.record_fallback.assert_not_called()
    finally:
        _cleanup(saved)


def _collect_voice_frames(chat_utils):
    async def collect():
        return [
            chunk
            async for chunk in chat_utils.process_voice_message_segment_stream(
                '/tmp/decoded.wav', 'test-uid', language='en'
            )
        ]

    return asyncio.run(collect())


def test_voice_stream_emits_fallback_done_frame_on_pipeline_error():
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:
        stub_calls = []

        async def failing_graph_stream(*args, **kwargs):
            stub_calls.append(1)
            kwargs['callback_data']['error'] = 'boom: internal detail'
            yield None

        # Patch the USING module's binding. utils.chat did
        # ``from utils.retrieval.graph import execute_graph_chat_stream`` at import
        # time, so patching the graph module's attribute would be stale and the
        # loop would silently iterate the leftover empty MagicMock instead.
        chat_utils.execute_graph_chat_stream = failing_graph_stream

        # Spy on the shared emitter to capture the error state the pipeline signalled.
        real_emit = chat_utils.emit_stream_error_fallback
        captured = {}

        async def spy_emit(*args, **kwargs):
            captured.update(kwargs)
            return await real_emit(*args, **kwargs)

        chat_utils.emit_stream_error_fallback = spy_emit

        frames = _collect_voice_frames(chat_utils)

        # Prove the error path actually ran -- a stale patch can never go green.
        assert stub_calls, 'failing_graph_stream was never called (binding was stale)'
        assert captured.get('error_recorded') is True

        done_frames = [f for f in frames if f.startswith('done: ')]
        assert len(done_frames) == 1
        payload = _decode_done_frame(''.join(frames))
        assert payload['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
        assert payload['sender'] == 'ai'
        assert not any('boom' in f for f in frames)

        ai_writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai']
        assert len(ai_writes) == 1
        assert ai_writes[0]['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT

        # Fail-open correctness degrade is recorded once, as a persisted degrade.
        chat_utils.record_fallback.assert_called_once()
        assert chat_utils.record_fallback.call_args.kwargs['outcome'] == 'degraded'
    finally:
        _cleanup(saved)


def test_voice_stream_emits_fallback_when_pipeline_yields_no_answer():
    """Distinct from the error path: the pipeline completes cleanly but produces
    neither an answer nor an error (empty LLM output). Still a blank-bubble bug
    without the fallback, but error_recorded is False."""
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:

        async def empty_stream(*args, **kwargs):
            yield None  # no answer, no error

        chat_utils.execute_graph_chat_stream = empty_stream

        real_emit = chat_utils.emit_stream_error_fallback
        captured = {}

        async def spy_emit(*args, **kwargs):
            captured.update(kwargs)
            return await real_emit(*args, **kwargs)

        chat_utils.emit_stream_error_fallback = spy_emit

        frames = _collect_voice_frames(chat_utils)

        assert captured.get('error_recorded') is False
        done_frames = [f for f in frames if f.startswith('done: ')]
        assert len(done_frames) == 1
        payload = _decode_done_frame(''.join(frames))
        assert payload['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
        chat_utils.record_fallback.assert_called_once()
        assert chat_utils.record_fallback.call_args.kwargs['outcome'] == 'degraded'
    finally:
        _cleanup(saved)


def test_emit_stream_error_fallback_reports_exhausted_when_persist_fails():
    """If the Firestore write for the fallback reply itself raises, the emitter
    must still return a done: frame (blank bubble otherwise) but record the
    fallback as 'exhausted' rather than the persisted 'degraded'."""
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:
        chat_db.add_message.side_effect = RuntimeError('firestore down')

        frame = asyncio.run(
            chat_utils.emit_stream_error_fallback('test-uid', None, None, label='chat', error_recorded=True)
        )

        assert frame.startswith('done: ')
        payload = _decode_done_frame(frame)
        assert payload['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
        assert payload['sender'] == 'ai'

        chat_utils.record_fallback.assert_called_once()
        assert chat_utils.record_fallback.call_args.kwargs['outcome'] == 'exhausted'
    finally:
        _cleanup(saved)


def test_build_stream_error_reply_persists_ai_message():
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:
        reply = chat_utils.build_stream_error_reply('test-uid')

        assert reply.text == chat_utils.CHAT_STREAM_ERROR_TEXT
        assert reply.sender == 'ai'
        chat_db.add_message.assert_called_once()
        persisted = chat_db.add_message.call_args.args[1]
        assert persisted['sender'] == 'ai'
        assert persisted['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
    finally:
        _cleanup(saved)
