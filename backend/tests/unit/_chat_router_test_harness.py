"""Shared stubbing harness for chat router/util unit tests.

Both ``test_chat_quota_counting_router`` and ``test_chat_stream_error_fallback``
load the real ``routers.chat`` (and, for the fallback suite, the real
``utils.chat``) with every heavy dependency stubbed. The stub-installation trio
and the large common block of module stubs are identical between the two suites;
they live here so each suite only layers its scenario-specific mocks on top.

Test isolation: all ``sys.modules`` mutation happens inside functions called by a
per-test fixture that snapshots ``sys.modules`` first and restores it in a
``finally`` via :func:`cleanup`. Nothing here mutates ``sys.modules`` at module
scope.
"""

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def install_package(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def install_module(name: str, module=None, *, default_factory=None):
    if module is None:
        module = default_factory(name) if default_factory is not None else MagicMock()
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def load_real_module(name: str, path: Path):
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


def cleanup(saved):
    for name in [k for k in sys.modules if k not in saved]:
        del sys.modules[name]
    for name, module in saved.items():
        sys.modules[name] = module


def wire_common_stubs(install) -> SimpleNamespace:
    """Install the module stubs shared verbatim by both chat test suites.

    ``install`` is the caller's bound installer (it carries that suite's default
    module factory, so bare ``database.*`` stubs stay ``MagicMock`` or
    ``ModuleType`` exactly as each suite had them). ``utils.*`` stubs are forced
    to ``ModuleType`` because both suites installed them that way. Returns the
    handles a suite layers extra attributes onto.
    """
    load_real_module('models.chat', BACKEND_DIR / 'models' / 'chat.py')

    chat_db = install('database.chat')
    chat_db.get_chat_session = MagicMock(return_value=None)
    chat_db.get_messages = MagicMock(return_value=[])
    chat_db.get_cache_aligned_messages = MagicMock(return_value=[])
    chat_db.add_message = MagicMock(side_effect=lambda uid, message_data: message_data)
    chat_db.add_message_to_chat_session = MagicMock()
    install('database.conversations')
    apps_db = install('database.apps')
    apps_db.record_app_usage = MagicMock()
    llm_usage_db = install('database.llm_usage')
    llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)
    users_db = install('database.users')
    users_db.set_chat_message_rating_score = MagicMock()
    redis_db = install('database.redis_db')
    redis_db.try_acquire_goal_extraction_lock = MagicMock(return_value=False)
    redis_db.check_rate_limit = MagicMock(return_value=(True, 99, 0))
    redis_db.store_chat_share = MagicMock()
    redis_db.get_chat_share = MagicMock(return_value=None)

    executors = install('utils.executors', ModuleType('utils.executors'))
    executors.critical_executor = MagicMock()
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.storage_executor = MagicMock()
    executors.sync_executor = MagicMock()

    async def run_blocking_side_effect(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    executors.run_blocking = AsyncMock(side_effect=run_blocking_side_effect)

    utils_apps = install('utils.apps', ModuleType('utils.apps'))
    utils_apps.get_available_app_by_id = MagicMock(return_value=None)
    helpers = install('utils.conversation_helpers', ModuleType('utils.conversation_helpers'))
    helpers.extract_memory_ids = MagicMock(return_value=[])
    goals = install('utils.llm.goals', ModuleType('utils.llm.goals'))
    goals.extract_and_update_goal_progress = MagicMock()
    users = install('utils.users', ModuleType('utils.users'))
    users.get_user_display_name = MagicMock(return_value='Test User')
    sanitizer = install('utils.log_sanitizer', ModuleType('utils.log_sanitizer'))
    sanitizer.sanitize_pii = lambda value: value
    observability = install('utils.observability', ModuleType('utils.observability'))
    observability.submit_langsmith_feedback = MagicMock()

    journey_observability = install('utils.observability.journeys', ModuleType('utils.observability.journeys'))

    class JourneyAttempt:
        """Spy double: records every attempt and its finish() outcomes per suite run."""

        instances = []

        def __init__(self, journey):
            self.journey = journey
            self.finished = False
            self.outcomes = []
            self.__class__.instances.append(self)

        def finish(self, outcome):
            if self.finished:
                return
            self.finished = True
            self.outcomes.append(outcome)

    journey_observability.JourneyAttempt = JourneyAttempt
    transcription_observability = install(
        'utils.observability.transcription', ModuleType('utils.observability.transcription')
    )
    transcription_observability.TranscriptionAttempt = MagicMock

    rate_limit = install('utils.rate_limit_config', ModuleType('utils.rate_limit_config'))
    rate_limit.get_effective_limit = MagicMock(return_value=(100, 60))
    rate_limit.RATE_LIMIT_SHADOW = False
    subscription = install('utils.subscription', ModuleType('utils.subscription'))
    subscription.enforce_chat_quota = MagicMock()
    subscription.is_trial_paywalled = MagicMock(return_value=False)

    auth = install('utils.other.endpoints', ModuleType('utils.other.endpoints'))

    def get_current_user_uid():
        return 'test-uid'

    def with_rate_limit(func, _policy):
        return func

    auth.get_current_user_uid = get_current_user_uid
    auth.get_current_user_uid_ws_listen = get_current_user_uid
    auth.with_rate_limit = with_rate_limit
    # routers.chat's import chain reaches modules decorated with @timeit.
    auth.timeit = lambda f: f
    storage = install('utils.other.storage', ModuleType('utils.other.storage'))
    storage.get_syncing_file_temporal_signed_url = MagicMock(return_value='https://example.test/audio.wav')
    storage.schedule_syncing_temporal_file_deletion = MagicMock()
    chat_file = install('utils.other.chat_file', ModuleType('utils.other.chat_file'))
    chat_file.FileChatTool = MagicMock()

    sync_files = install('utils.sync.files', ModuleType('utils.sync.files'))
    sync_files.retrieve_file_paths = MagicMock(return_value=[])
    sync_files.decode_files_to_wav = MagicMock(return_value=[])
    stt_streaming = install('utils.stt.streaming', ModuleType('utils.stt.streaming'))
    stt_streaming.process_audio_dg = MagicMock()
    stt_streaming.get_stt_service_for_language = MagicMock()
    stt_streaming.STTService = MagicMock()
    stt_streaming.connect_stt_socket_with_fallback = MagicMock()
    stt_streaming.drain_stt_socket = AsyncMock()
    stt_streaming.process_audio_modulate = MagicMock()
    stt_streaming.process_audio_parakeet = MagicMock()
    # These chat suites do not exercise prerecorded STT. Loading the real module
    # would import NumPy after a suite restores sys.modules between cases, which
    # native extension modules cannot safely do in one process.
    prerecorded = install('utils.stt.pre_recorded', ModuleType('utils.stt.pre_recorded'))
    prerecorded.PrerecordedSTTConfigurationError = type('PrerecordedSTTConfigurationError', (Exception,), {})
    prerecorded.get_prerecorded_service = MagicMock(return_value=('parakeet', 'en', 'parakeet'))

    usage_tracker = install('utils.llm.usage_tracker', ModuleType('utils.llm.usage_tracker'))
    usage_tracker.set_usage_context = MagicMock(return_value='usage-token')
    usage_tracker.reset_usage_context = MagicMock()

    class Features:
        CHAT = 'chat'

    usage_tracker.Features = Features

    limiter = install('utils.voice_duration_limiter', ModuleType('utils.voice_duration_limiter'))
    limiter.compute_pcm_duration_ms = MagicMock(return_value=1000)
    limiter.read_wav_duration_ms = MagicMock(return_value=1000)
    limiter.try_consume_budget = MagicMock(return_value=(True, 1000, 7199000))
    limiter.check_budget = MagicMock(return_value=(True, 0, 7200000))
    limiter.record_actual_duration = MagicMock()

    multipart = install('multipart', ModuleType('multipart'))
    multipart.__version__ = '0.0.20'
    multipart_sub = install('multipart.multipart', ModuleType('multipart.multipart'))
    multipart_sub.shutil = shutil

    return SimpleNamespace(
        chat_db=chat_db,
        llm_usage_db=llm_usage_db,
        apps_db=apps_db,
        usage_tracker=usage_tracker,
        auth=auth,
    )
