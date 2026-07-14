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
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _install_package(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _install_module(name: str, module=None):
    module = module or ModuleType(name)
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _load_real_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    spec.loader.exec_module(module)
    return module


def _make_client():
    """Load real models.chat + utils.chat + routers.chat with heavy deps stubbed."""
    saved = {k: v for k, v in sys.modules.items()}

    _install_package('models', BACKEND_DIR / 'models')
    _install_package('database', BACKEND_DIR / 'database')
    _install_package('utils', BACKEND_DIR / 'utils')
    _install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    _install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    _install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    _install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    _install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')
    _install_package('utils.conversations', BACKEND_DIR / 'utils' / 'conversations')

    _load_real_module('models.chat', BACKEND_DIR / 'models' / 'chat.py')
    models_app = _install_module('models.app')
    models_app.App = MagicMock()
    models_app.UsageHistoryType = MagicMock()
    nm = _install_module('models.notification_message')
    nm.NotificationMessage = MagicMock()
    ts = _install_module('models.transcript_segment')
    ts.TranscriptSegment = MagicMock()

    chat_db = _install_module('database.chat')
    chat_db.get_chat_session = MagicMock(return_value=None)
    chat_db.get_chat_session_by_id = MagicMock(return_value=None)
    chat_db.add_chat_session = MagicMock(side_effect=lambda uid, data: data)
    chat_db.get_messages = MagicMock(return_value=[])
    chat_db.add_message = MagicMock(side_effect=lambda uid, message_data: message_data)
    chat_db.add_message_to_chat_session = MagicMock()
    _install_module('database.conversations')
    notif_db = _install_module('database.notifications')
    apps_db = _install_module('database.apps')
    apps_db.record_app_usage = MagicMock()
    llm_usage_db = _install_module('database.llm_usage')
    llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)
    users_db = _install_module('database.users')
    users_db.set_chat_message_rating_score = MagicMock()
    redis_db = _install_module('database.redis_db')
    redis_db.try_acquire_goal_extraction_lock = MagicMock(return_value=False)
    redis_db.check_rate_limit = MagicMock(return_value=(True, 99, 0))
    redis_db.store_chat_share = MagicMock()
    redis_db.get_chat_share = MagicMock(return_value=None)

    executors = _install_module('utils.executors')
    executors.critical_executor = MagicMock()
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.storage_executor = MagicMock()
    executors.sync_executor = MagicMock()

    async def run_blocking_side_effect(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    executors.run_blocking = AsyncMock(side_effect=run_blocking_side_effect)

    utils_apps = _install_module('utils.apps')
    utils_apps.get_available_app_by_id = MagicMock(return_value=None)
    helpers = _install_module('utils.conversation_helpers')
    helpers.extract_memory_ids = MagicMock(return_value=[])
    factory = _install_module('utils.conversations.factory')
    factory.deserialize_conversation = MagicMock()
    goals = _install_module('utils.llm.goals')
    goals.extract_and_update_goal_progress = MagicMock()
    llm_chat = _install_module('utils.llm.chat')
    llm_chat.initial_chat_message = MagicMock(return_value='hi')
    llm_persona = _install_module('utils.llm.persona')
    llm_persona.initial_persona_chat_message = MagicMock(return_value='hi')
    notifications = _install_module('utils.notifications')
    notifications.send_notification = MagicMock()
    users = _install_module('utils.users')
    users.get_user_display_name = MagicMock(return_value='Test User')
    sanitizer = _install_module('utils.log_sanitizer')
    sanitizer.sanitize_pii = lambda value: value
    observability = _install_module('utils.observability')
    observability.submit_langsmith_feedback = MagicMock()

    rate_limit = _install_module('utils.rate_limit_config')
    rate_limit.get_effective_limit = MagicMock(return_value=(100, 60))
    rate_limit.RATE_LIMIT_SHADOW = False
    subscription = _install_module('utils.subscription')
    subscription.enforce_chat_quota = MagicMock()
    subscription.is_trial_paywalled = MagicMock(return_value=False)

    auth = _install_module('utils.other.endpoints')

    def get_current_user_uid():
        return 'test-uid'

    def with_rate_limit(func, _policy):
        return func

    auth.get_current_user_uid = get_current_user_uid
    auth.get_current_user_uid_ws_listen = get_current_user_uid
    auth.with_rate_limit = with_rate_limit
    storage = _install_module('utils.other.storage')
    storage.get_syncing_file_temporal_signed_url = MagicMock(return_value='https://example.test/audio.wav')
    storage.schedule_syncing_temporal_file_deletion = MagicMock()
    chat_file = _install_module('utils.other.chat_file')
    chat_file.FileChatTool = MagicMock()

    sync_files = _install_module('utils.sync.files')
    sync_files.retrieve_file_paths = MagicMock(return_value=[])
    sync_files.decode_files_to_wav = MagicMock(return_value=[])
    stt_streaming = _install_module('utils.stt.streaming')
    stt_streaming.process_audio_dg = MagicMock()
    stt_streaming.get_stt_service_for_language = MagicMock()
    pre_recorded = _install_module('utils.stt.pre_recorded')
    pre_recorded.get_deepgram_model_for_language = MagicMock(return_value=('en', 'nova-2'))
    pre_recorded.postprocess_words = MagicMock(return_value=[SimpleNamespace(text='hello')])
    pre_recorded.prerecorded = MagicMock(return_value=[])
    pre_recorded.prerecorded_from_bytes = MagicMock(return_value=[])

    usage_tracker = _install_module('utils.llm.usage_tracker')
    usage_tracker.set_usage_context = MagicMock(return_value='usage-token')
    usage_tracker.reset_usage_context = MagicMock()
    usage_tracker.track_usage = MagicMock()

    class Features:
        CHAT = 'chat'

    usage_tracker.Features = Features

    # utils.retrieval.graph is imported by both utils.chat and routers.chat -- stub it
    # so tests can install per-scenario streaming behaviour.
    graph = _install_module('utils.retrieval.graph')
    graph.execute_graph_chat = MagicMock()
    graph.execute_graph_chat_stream = MagicMock()
    graph.execute_chat_stream = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    limiter = _install_module('utils.voice_duration_limiter')
    limiter.compute_pcm_duration_ms = MagicMock(return_value=1000)
    limiter.read_wav_duration_ms = MagicMock(return_value=1000)
    limiter.try_consume_budget = MagicMock(return_value=(True, 1000, 7199000))
    limiter.check_budget = MagicMock(return_value=(True, 0, 7200000))
    limiter.record_actual_duration = MagicMock()

    multipart = _install_module('multipart')
    multipart.__version__ = '0.0.20'
    multipart_sub = _install_module('multipart.multipart')
    import shutil

    multipart_sub.shutil = shutil

    chat_utils = _load_real_module('utils.chat', BACKEND_DIR / 'utils' / 'chat.py')

    sys.modules.pop('routers.chat', None)
    router_module = _load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')

    app = FastAPI()
    app.include_router(router_module.router)
    client = TestClient(app)
    return client, router_module, chat_utils, chat_db, saved


def _cleanup(saved):
    for name in [k for k in sys.modules if k not in saved]:
        del sys.modules[name]
    for name, module in saved.items():
        sys.modules[name] = module


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
    finally:
        _cleanup(saved)


def test_voice_stream_emits_fallback_done_frame_on_pipeline_error():
    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:

        async def failing_graph_stream(*args, **kwargs):
            kwargs['callback_data']['error'] = 'boom: internal detail'
            yield None

        sys.modules['utils.retrieval.graph'].execute_graph_chat_stream = failing_graph_stream

        async def collect():
            return [
                chunk
                async for chunk in chat_utils.process_voice_message_segment_stream(
                    '/tmp/decoded.wav', 'test-uid', language='en'
                )
            ]

        frames = asyncio.run(collect())

        done_frames = [f for f in frames if f.startswith('done: ')]
        assert len(done_frames) == 1
        payload = _decode_done_frame(''.join(frames))
        assert payload['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
        assert payload['sender'] == 'ai'
        assert not any('boom' in f for f in frames)

        ai_writes = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai']
        assert len(ai_writes) == 1
        assert ai_writes[0]['text'] == chat_utils.CHAT_STREAM_ERROR_TEXT
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
