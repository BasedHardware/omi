"""Router tests for the stateless owner-authenticated reply generation endpoint.

Regression guard: automated drafting surfaces (the AI clone) must be able to
generate a reply without any turn landing in the owner's chat history.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit import _chat_router_test_harness as harness
from tests.unit._chat_router_test_harness import BACKEND_DIR


def _make_chat_client(stream_impl):
    saved = {k: v for k, v in sys.modules.items()}

    harness.install_package('models', BACKEND_DIR / 'models')
    harness.install_package('database', BACKEND_DIR / 'database')
    harness.install_package('utils', BACKEND_DIR / 'utils')
    harness.install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    harness.install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    harness.install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    harness.install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    harness.install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')

    harness.wire_common_stubs(harness.install_module)
    harness.install_module('models.app')

    chat_utils = harness.install_module('utils.chat', ModuleType('utils.chat'))
    chat_utils.acquire_chat_session = MagicMock()
    chat_utils.emit_stream_error_fallback = MagicMock()
    chat_utils.initial_message_util = MagicMock()
    chat_utils.process_voice_message_segment = MagicMock()
    chat_utils.resolve_voice_message_language = MagicMock(return_value='en')
    chat_utils.transcribe_voice_message_segment = MagicMock()
    chat_utils.transcribe_pcm_bytes = MagicMock()

    async def default_voice_stream(*args, **kwargs):
        if False:
            yield None

    chat_utils.process_voice_message_segment_stream = MagicMock(side_effect=default_voice_stream)

    graph = harness.install_module('utils.retrieval.graph', ModuleType('utils.retrieval.graph'))
    graph.execute_chat_stream = stream_impl
    graph.execute_graph_chat = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    sys.modules.pop('routers.chat', None)
    sys.modules.pop('routers.chat_generation', None)
    chat_module = harness.load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')
    generation_module = harness.load_real_module(
        'routers.chat_generation', BACKEND_DIR / 'routers' / 'chat_generation.py'
    )

    app = FastAPI()
    app.include_router(chat_module.router)
    app.include_router(generation_module.router)
    return TestClient(app, raise_server_exceptions=False), chat_module, generation_module, saved


def _answering_stream(recorded):
    async def _stream(uid, messages, app=None, **kwargs):
        recorded['uid'] = uid
        recorded['messages'] = messages
        recorded['kwargs'] = kwargs
        kwargs['callback_data']['answer'] = 'drafted reply'
        yield ''

    return _stream


def _failing_stream():
    async def _stream(uid, messages, app=None, **kwargs):
        # Mirrors the real graph: a typed failure stages a canned answer alongside
        # the error, and yields a verbatim `error: ` frame.
        kwargs['callback_data']['error'] = 'setup_timeout'
        kwargs['callback_data']['answer'] = 'Sorry, I had trouble answering.'
        yield 'error: Sorry, I had trouble answering.'
        yield None

    return _stream


def _raising_stream():
    async def _stream(uid, messages, app=None, **kwargs):
        raise RuntimeError('provider details must not escape')
        yield None

    return _stream


def test_generate_reply_does_not_write_any_turn_to_chat_history():
    recorded = {}
    client, chat_module, generation_module, saved = _make_chat_client(_answering_stream(recorded))
    try:
        response = client.post(
            '/v2/chat/generate-reply',
            json={
                'text': 'Draft a reply to Alice',
                'history': [{'text': 'hey are we still on for friday?', 'sender': 'human'}],
            },
            headers={'X-App-Platform': 'windows'},
        )

        assert response.status_code == 200
        assert response.json()['text'] == 'drafted reply'

        # The real property: nothing about this generation touched chat state.
        chat_module.chat_db.add_message.assert_not_called()
        chat_module.chat_db.add_message_to_chat_session.assert_not_called()
        chat_module.chat_db.get_chat_session.assert_not_called()
        chat_module.chat_db.add_files_to_chat_session.assert_not_called()
        chat_module.llm_usage_db.record_chat_quota_question.assert_not_called()
        chat_module.llm_executor.submit.assert_not_called()
        generation_module.record_fallback.assert_not_called()

        # Generation still runs through the shared chat path, with no session identity.
        assert recorded['uid'] == 'test-uid'
        assert recorded['kwargs']['chat_session'] is None
        assert [m.text for m in recorded['messages']] == [
            'hey are we still on for friday?',
            'Draft a reply to Alice',
        ]
    finally:
        harness.cleanup(saved)


def test_generate_reply_maps_raised_stream_failures_to_the_error_contract():
    client, chat_module, generation_module, saved = _make_chat_client(_raising_stream())
    try:
        response = client.post('/v2/chat/generate-reply', json={'text': 'Draft a reply'})

        assert response.status_code == 502
        assert response.json()['detail'] == {'error': 'stream_failure'}
        assert 'provider details' not in response.text
        chat_module.chat_db.add_message.assert_not_called()
        generation_module.record_fallback.assert_called_once()
    finally:
        harness.cleanup(saved)


def test_generate_reply_rejects_an_unavailable_requested_app():
    recorded = {}
    client, chat_module, generation_module, saved = _make_chat_client(_answering_stream(recorded))
    try:
        generation_module.get_available_app_by_id.return_value = None

        response = client.post(
            '/v2/chat/generate-reply',
            json={'text': 'Draft a reply', 'app_id': 'missing-app'},
        )

        assert response.status_code == 404
        assert response.json()['detail'] == {'error': 'app_not_found'}
        assert recorded == {}
        generation_module.record_fallback.assert_not_called()
        chat_module.chat_db.add_message.assert_not_called()
    finally:
        harness.cleanup(saved)


def test_generate_reply_removes_conversation_citations_from_external_drafts():
    async def cited_stream(uid, messages, app=None, **kwargs):
        kwargs['callback_data']['answer'] = 'Friday works[1]. Bring the notes[12].'
        yield ''

    client, chat_module, generation_module, saved = _make_chat_client(cited_stream)
    try:
        response = client.post('/v2/chat/generate-reply', json={'text': 'Draft a reply'})

        assert response.status_code == 200
        assert response.json()['text'] == 'Friday works. Bring the notes.'
        generation_module.record_fallback.assert_not_called()
        chat_module.chat_db.add_message.assert_not_called()
    finally:
        harness.cleanup(saved)


def test_generate_reply_never_returns_a_staged_error_answer_as_reply_text():
    client, chat_module, generation_module, saved = _make_chat_client(_failing_stream())
    try:
        response = client.post('/v2/chat/generate-reply', json={'text': 'Draft a reply'})

        assert response.status_code == 502
        assert response.json()['detail'] == {'error': 'setup_timeout'}
        assert 'Sorry' not in response.text
        chat_module.chat_db.add_message.assert_not_called()
        generation_module.record_fallback.assert_called_once()
        assert generation_module.record_fallback.call_args.kwargs['outcome'] == 'exhausted'
    finally:
        harness.cleanup(saved)


def test_v2_messages_still_persists_the_human_turn():
    """Legacy principal: the existing chat endpoint keeps its persisting behavior."""
    recorded = {}
    client, chat_module, generation_module, saved = _make_chat_client(_answering_stream(recorded))
    try:
        response = client.post('/v2/messages', json={'text': 'hello', 'file_ids': []})

        assert response.status_code == 200
        assert chat_module.chat_db.add_message.call_count >= 1
        chat_module.llm_usage_db.record_chat_quota_question.assert_called_once()
    finally:
        harness.cleanup(saved)
