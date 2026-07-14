"""Router tests for explicit backend chat quota question counting."""

import base64
import io
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit import _chat_router_test_harness as harness
from tests.unit._chat_router_test_harness import BACKEND_DIR


def _make_chat_client():
    saved = {k: v for k, v in sys.modules.items()}

    harness.install_package('models', BACKEND_DIR / 'models')
    harness.install_package('database', BACKEND_DIR / 'database')
    harness.install_package('utils', BACKEND_DIR / 'utils')
    harness.install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    harness.install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    harness.install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    harness.install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    harness.install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')

    # This suite stubs database.* modules as MagicMock (auto-attribute) exactly
    # as the original harness did; utils.* stubs are forced to ModuleType inside
    # wire_common_stubs.
    harness.wire_common_stubs(harness.install_module)

    harness.install_module('models.app')

    # Stub utils.chat entirely -- this suite exercises the real routers.chat only.
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

    async def fake_execute_chat_stream(*args, **kwargs):
        kwargs['callback_data']['answer'] = 'hello back'
        yield ''

    graph.execute_chat_stream = fake_execute_chat_stream
    graph.execute_graph_chat = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    sys.modules.pop('routers.chat', None)
    module = harness.load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    return client, module, saved


def _cleanup(saved):
    harness.cleanup(saved)


def test_v2_messages_records_quota_question_after_human_message_persisted():
    client, module, saved = _make_chat_client()
    try:
        with patch.object(module.uuid, 'uuid4', side_effect=['human-msg-id', 'ai-msg-id']):
            response = client.post(
                '/v2/messages',
                json={'text': 'hello', 'file_ids': []},
                headers={'X-App-Platform': 'ios'},
            )

        assert response.status_code == 200
        module.llm_usage_db.record_chat_quota_question.assert_called_once_with(
            'test-uid',
            idempotency_key='v2_messages:human-msg-id',
            source='v2_messages',
            message_id='human-msg-id',
            chat_session_id=None,
            platform='ios',
        )
        first_message = module.chat_db.add_message.call_args_list[0].args[1]
        assert first_message['id'] == 'human-msg-id'
        assert first_message['sender'] == 'human'
    finally:
        _cleanup(saved)


def test_v2_messages_quota_exceeded_reply_does_not_record_quota_question():
    client, module, saved = _make_chat_client()
    try:
        quota_detail = {
            'error': 'quota_exceeded',
            'plan': 'Free',
            'unit': 'questions',
            'used': 30,
            'limit': 30,
        }
        module.enforce_chat_quota.side_effect = module.HTTPException(status_code=402, detail=quota_detail)

        response = client.post(
            '/v2/messages',
            json={'text': 'hello', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        assert 'done: ' in response.text
        module.llm_usage_db.record_chat_quota_question.assert_not_called()
    finally:
        _cleanup(saved)


def test_v2_voice_messages_records_quota_question_from_visible_message_chunk():
    client, module, saved = _make_chat_client()
    try:
        human_message = module.Message(
            id='voice-human-msg-id',
            text='voice hello',
            created_at=module.datetime.now(module.timezone.utc),
            sender='human',
            type='text',
            chat_session_id='voice-session-id',
        )
        encoded = base64.b64encode(bytes(human_message.model_dump_json(), 'utf-8')).decode('utf-8')

        async def fake_voice_stream(*args, **kwargs):
            yield f'message: {encoded}\n\n'
            yield 'done: e30=\n\n'

        with patch.object(module, 'retrieve_file_paths', return_value=['/tmp/upload.wav']):
            with patch.object(module, 'decode_files_to_wav', return_value=['/tmp/decoded.wav']):
                with patch.object(module, 'process_voice_message_segment_stream', side_effect=fake_voice_stream):
                    response = client.post(
                        '/v2/voice-messages',
                        files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                        headers={'X-App-Platform': 'ios'},
                    )

        assert response.status_code == 200
        module.llm_usage_db.record_chat_quota_question.assert_called_once_with(
            'test-uid',
            idempotency_key='v2_voice_messages:voice-human-msg-id',
            source='v2_voice_messages',
            message_id='voice-human-msg-id',
            chat_session_id='voice-session-id',
            platform='ios',
        )
    finally:
        _cleanup(saved)


def test_v2_voice_messages_without_visible_message_does_not_record_quota_question():
    client, module, saved = _make_chat_client()
    try:

        async def fake_voice_stream(*args, **kwargs):
            yield 'done: e30=\n\n'

        with patch.object(module, 'retrieve_file_paths', return_value=['/tmp/upload.wav']):
            with patch.object(module, 'decode_files_to_wav', return_value=['/tmp/decoded.wav']):
                with patch.object(module, 'process_voice_message_segment_stream', side_effect=fake_voice_stream):
                    response = client.post(
                        '/v2/voice-messages',
                        files=[('files', ('test.wav', io.BytesIO(b'\x00' * 100), 'audio/wav'))],
                        headers={'X-App-Platform': 'ios'},
                    )

        assert response.status_code == 200
        module.llm_usage_db.record_chat_quota_question.assert_not_called()
    finally:
        _cleanup(saved)
