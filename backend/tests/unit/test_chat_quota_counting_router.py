"""Router tests for explicit backend chat quota question counting."""

import base64
import importlib.util
import io
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

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
    module = module or MagicMock()
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


def _make_chat_client():
    saved = {k: v for k, v in sys.modules.items()}

    _install_package('models', BACKEND_DIR / 'models')
    _install_package('database', BACKEND_DIR / 'database')
    _install_package('utils', BACKEND_DIR / 'utils')
    _install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    _install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    _install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    _install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    _install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')

    _load_real_module('models.chat', BACKEND_DIR / 'models' / 'chat.py')
    _install_module('models.app')

    chat_db = _install_module('database.chat')
    chat_db.get_chat_session = MagicMock(return_value=None)
    chat_db.get_messages = MagicMock(return_value=[])
    chat_db.add_message = MagicMock(side_effect=lambda uid, message_data: message_data)
    chat_db.add_message_to_chat_session = MagicMock()
    _install_module('database.conversations')
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

    executors = _install_module('utils.executors', ModuleType('utils.executors'))
    executors.critical_executor = MagicMock()
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.storage_executor = MagicMock()
    executors.sync_executor = MagicMock()

    async def run_blocking_side_effect(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    executors.run_blocking = AsyncMock(side_effect=run_blocking_side_effect)

    utils_apps = _install_module('utils.apps', ModuleType('utils.apps'))
    utils_apps.get_available_app_by_id = MagicMock(return_value=None)
    helpers = _install_module('utils.conversation_helpers', ModuleType('utils.conversation_helpers'))
    helpers.extract_memory_ids = MagicMock(return_value=[])
    goals = _install_module('utils.llm.goals', ModuleType('utils.llm.goals'))
    goals.extract_and_update_goal_progress = MagicMock()
    users = _install_module('utils.users', ModuleType('utils.users'))
    users.get_user_display_name = MagicMock(return_value='Test User')
    sanitizer = _install_module('utils.log_sanitizer', ModuleType('utils.log_sanitizer'))
    sanitizer.sanitize_pii = lambda value: value
    observability = _install_module('utils.observability', ModuleType('utils.observability'))
    observability.submit_langsmith_feedback = MagicMock()

    rate_limit = _install_module('utils.rate_limit_config', ModuleType('utils.rate_limit_config'))
    rate_limit.get_effective_limit = MagicMock(return_value=(100, 60))
    rate_limit.RATE_LIMIT_SHADOW = False
    subscription = _install_module('utils.subscription', ModuleType('utils.subscription'))
    subscription.enforce_chat_quota = MagicMock()
    subscription.is_trial_paywalled = MagicMock(return_value=False)

    auth = _install_module('utils.other.endpoints', ModuleType('utils.other.endpoints'))

    def get_current_user_uid():
        return 'test-uid'

    def with_rate_limit(func, _policy):
        return func

    auth.get_current_user_uid = get_current_user_uid
    auth.get_current_user_uid_ws_listen = get_current_user_uid
    auth.with_rate_limit = with_rate_limit
    storage = _install_module('utils.other.storage', ModuleType('utils.other.storage'))
    storage.get_syncing_file_temporal_signed_url = MagicMock(return_value='https://example.test/audio.wav')
    storage.schedule_syncing_temporal_file_deletion = MagicMock()
    chat_file = _install_module('utils.other.chat_file', ModuleType('utils.other.chat_file'))
    chat_file.FileChatTool = MagicMock()

    chat_utils = _install_module('utils.chat', ModuleType('utils.chat'))
    chat_utils.acquire_chat_session = MagicMock()
    chat_utils.initial_message_util = MagicMock()
    chat_utils.process_voice_message_segment = MagicMock()
    chat_utils.resolve_voice_message_language = MagicMock(return_value='en')
    chat_utils.transcribe_voice_message_segment = MagicMock()
    chat_utils.transcribe_pcm_bytes = MagicMock()

    async def default_voice_stream(*args, **kwargs):
        if False:
            yield None

    chat_utils.process_voice_message_segment_stream = MagicMock(side_effect=default_voice_stream)

    sync_files = _install_module('utils.sync.files', ModuleType('utils.sync.files'))
    sync_files.retrieve_file_paths = MagicMock(return_value=[])
    sync_files.decode_files_to_wav = MagicMock(return_value=[])
    stt_streaming = _install_module('utils.stt.streaming', ModuleType('utils.stt.streaming'))
    stt_streaming.process_audio_dg = MagicMock()
    stt_streaming.get_stt_service_for_language = MagicMock()

    usage_tracker = _install_module('utils.llm.usage_tracker', ModuleType('utils.llm.usage_tracker'))
    usage_tracker.set_usage_context = MagicMock(return_value='usage-token')
    usage_tracker.reset_usage_context = MagicMock()

    class Features:
        CHAT = 'chat'

    usage_tracker.Features = Features

    graph = _install_module('utils.retrieval.graph', ModuleType('utils.retrieval.graph'))

    async def fake_execute_chat_stream(*args, **kwargs):
        kwargs['callback_data']['answer'] = 'hello back'
        yield ''

    graph.execute_chat_stream = fake_execute_chat_stream
    graph.execute_graph_chat = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    limiter = _install_module('utils.voice_duration_limiter', ModuleType('utils.voice_duration_limiter'))
    limiter.compute_pcm_duration_ms = MagicMock(return_value=1000)
    limiter.read_wav_duration_ms = MagicMock(return_value=1000)
    limiter.try_consume_budget = MagicMock(return_value=(True, 1000, 7199000))
    limiter.check_budget = MagicMock(return_value=(True, 0, 7200000))
    limiter.record_actual_duration = MagicMock()

    multipart = _install_module('multipart', ModuleType('multipart'))
    multipart.__version__ = '0.0.20'
    multipart_sub = _install_module('multipart.multipart', ModuleType('multipart.multipart'))
    import shutil

    multipart_sub.shutil = shutil

    sys.modules.pop('routers.chat', None)
    spec = importlib.util.spec_from_file_location('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['routers.chat'] = module
    spec.loader.exec_module(module)

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    return client, module, saved


def _cleanup(saved):
    for name in [k for k in sys.modules if k not in saved]:
        del sys.modules[name]
    for name, module in saved.items():
        sys.modules[name] = module


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
