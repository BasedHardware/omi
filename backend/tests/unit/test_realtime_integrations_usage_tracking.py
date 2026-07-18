"""Behavioral tests for LLM usage ownership in realtime integrations.

The production coordinator binds its collaborators at import time. Each test
therefore loads fresh production modules inside ``stub_modules`` so no partial
database/model stubs survive collection or leak into another test file.
"""

import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    return module


def _auto_module(name: str, **attributes: Any) -> AutoMockModule:
    module = AutoMockModule(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _realtime_app(app_id: str = 'app-1') -> MagicMock:
    app = MagicMock()
    app.id = app_id
    app.name = 'Test App'
    app.uid = 'owner-uid'
    app.enabled = True
    app.external_integration.webhook_url = 'https://app.test/hook'
    app.triggers_realtime.return_value = True
    app.triggers_realtime_audio_bytes.return_value = True
    app.has_capability.return_value = False
    return app


class _BaseCallbackHandler:
    pass


class _LLMResult:
    def __init__(self, generations=None, llm_output=None, **_kwargs):
        self.generations = generations or []
        self.llm_output = llm_output


class _App:
    pass


class _ProactiveNotification:
    pass


class _UsageHistoryType:
    memory_created_external_integration = 'memory_created_external_integration'
    transcript_processed_external_integration = 'transcript_processed_external_integration'


class _Message:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Conversation:
    pass


class _ConversationSource:
    workflow = 'workflow'
    unknown = 'unknown'


class _NotificationMessage:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @staticmethod
    def get_message_as_dict(message):
        return dict(message.__dict__)


@pytest.fixture
def integration_harness() -> Iterator[SimpleNamespace]:
    process_mentor_notification = MagicMock(return_value=None)
    get_available_apps = MagicMock(return_value=[])
    add_app_message = MagicMock(return_value={'id': 'msg-1'})
    send_notification_async = AsyncMock(return_value=None)

    async def run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def gather_safe(*awaitables, **_kwargs):
        return await asyncio.gather(*awaitables)

    circuit_breaker = MagicMock()
    circuit_breaker.allow_request.return_value = True

    stubs: dict[str, ModuleType] = {
        'utils': _package('utils', BACKEND_DIR / 'utils'),
        'utils.llm': _package('utils.llm', BACKEND_DIR / 'utils' / 'llm'),
        'utils.llms': _package('utils.llms', BACKEND_DIR / 'utils' / 'llms'),
        'utils.conversations': _package('utils.conversations', BACKEND_DIR / 'utils' / 'conversations'),
        'database': _package('database', BACKEND_DIR / 'database'),
        'models': _package('models', BACKEND_DIR / 'models'),
        'langchain_core': _package('langchain_core', BACKEND_DIR),
        'langchain_core.callbacks': _module(
            'langchain_core.callbacks',
            BaseCallbackHandler=_BaseCallbackHandler,
        ),
        'langchain_core.outputs': _module('langchain_core.outputs', LLMResult=_LLMResult),
        'database.llm_usage': _module('database.llm_usage', record_llm_usage=MagicMock()),
        'database.notifications': _auto_module(
            'database.notifications',
            get_mentor_notification_frequency=MagicMock(return_value=0),
        ),
        'database.dev_api_key': _auto_module(
            'database.dev_api_key',
            get_dev_keys_for_user=MagicMock(return_value=[]),
        ),
        'database.mem_db': _auto_module(
            'database.mem_db',
            get_proactive_noti_sent_at=MagicMock(return_value=None),
            set_proactive_noti_sent_at=MagicMock(),
        ),
        'database.redis_db': _auto_module(
            'database.redis_db',
            get_generic_cache=MagicMock(return_value=None),
            set_generic_cache=MagicMock(),
            delete_app_cache_by_id=MagicMock(),
            get_proactive_noti_sent_at=MagicMock(return_value=None),
            set_proactive_noti_sent_at=MagicMock(),
            incr_daily_notification_count=MagicMock(),
            get_daily_notification_count=MagicMock(return_value=0),
            get_proactive_noti_sent_at_ttl=MagicMock(return_value=0),
        ),
        'database.apps': _auto_module(
            'database.apps',
            get_app_by_id_db=MagicMock(return_value=None),
            record_app_usage=MagicMock(),
        ),
        'database.webhook_health': _auto_module(
            'database.webhook_health',
            record_app_webhook_failure=MagicMock(return_value=0),
            record_app_webhook_success=MagicMock(),
            is_app_webhook_disabled=MagicMock(return_value=False),
            disable_app_in_firestore=MagicMock(),
        ),
        'database.chat': _auto_module(
            'database.chat',
            add_app_message=add_app_message,
            get_app_messages=MagicMock(return_value=[]),
        ),
        'database.goals': _auto_module('database.goals', get_user_goals=MagicMock(return_value=[])),
        'database.users': _auto_module(
            'database.users',
            get_user_language_preference=MagicMock(return_value='en'),
        ),
        'database.vector_db': _auto_module(
            'database.vector_db',
            query_vectors_by_metadata=MagicMock(return_value=[]),
        ),
        'database.conversations': _auto_module(
            'database.conversations',
            get_conversations_by_id=MagicMock(return_value=[]),
        ),
        'models.app': _module(
            'models.app',
            App=_App,
            ProactiveNotification=_ProactiveNotification,
            UsageHistoryType=_UsageHistoryType,
        ),
        'models.chat': _module('models.chat', Message=_Message),
        'models.conversation': _module('models.conversation', Conversation=_Conversation),
        'models.conversation_enums': _module(
            'models.conversation_enums',
            ConversationSource=_ConversationSource,
        ),
        'models.notification_message': _module(
            'models.notification_message',
            NotificationMessage=_NotificationMessage,
        ),
        'utils.http_client': _auto_module(
            'utils.http_client',
            get_webhook_client=MagicMock(),
            get_webhook_circuit_breaker=MagicMock(return_value=circuit_breaker),
            get_webhook_semaphore=MagicMock(return_value=asyncio.Semaphore(1)),
            latest_wins_start=MagicMock(return_value=1),
            latest_wins_check=MagicMock(return_value=True),
        ),
        'utils.executors': _module(
            'utils.executors',
            db_executor=object(),
            postprocess_executor=object(),
            run_blocking=run_blocking,
        ),
        'utils.async_tasks': _module('utils.async_tasks', gather_safe=gather_safe),
        'utils.dev_cache': _auto_module(
            'utils.dev_cache',
            get_cached_developer=MagicMock(return_value=None),
            set_cached_developer=MagicMock(),
        ),
        'utils.subscription': _module(
            'utils.subscription',
            is_trial_paywalled=MagicMock(return_value=False),
        ),
        'utils.conversations.factory': _module(
            'utils.conversations.factory',
            deserialize_conversations=MagicMock(return_value=[]),
        ),
        'utils.conversations.render': _module(
            'utils.conversations.render',
            conversations_to_string=MagicMock(return_value=''),
            conversation_to_dict=MagicMock(return_value={}),
            serialize_datetimes=MagicMock(side_effect=lambda value: value),
        ),
        'utils.apps': _module('utils.apps', get_available_apps=get_available_apps),
        'utils.notifications': _module(
            'utils.notifications',
            send_notification=MagicMock(),
            send_notification_async=send_notification_async,
        ),
        'utils.llm.clients': _auto_module(
            'utils.llm.clients',
            generate_embedding=MagicMock(return_value=[0] * 3072),
            get_llm=MagicMock(),
        ),
        'utils.llm.proactive_notification': _auto_module(
            'utils.llm.proactive_notification',
            evaluate_relevance=MagicMock(),
            generate_notification=MagicMock(),
            validate_notification=MagicMock(),
            FREQUENCY_TO_BASE_THRESHOLD={1: 0.5, 2: 0.4, 3: 0.3},
            MAX_DAILY_NOTIFICATIONS=10,
        ),
        'utils.llms.memory': _module(
            'utils.llms.memory',
            get_prompt_memories=MagicMock(return_value=('', '')),
        ),
        'utils.log_sanitizer': _module('utils.log_sanitizer', sanitize=MagicMock(side_effect=lambda value: value)),
        'utils.mentor_notifications': _module(
            'utils.mentor_notifications',
            process_mentor_notification=process_mentor_notification,
        ),
    }

    with stub_modules(stubs):
        usage_tracker = load_module_fresh(
            'utils.llm.usage_tracker',
            str(BACKEND_DIR / 'utils' / 'llm' / 'usage_tracker.py'),
        )
        app_integrations = load_module_fresh(
            'utils.app_integrations',
            str(BACKEND_DIR / 'utils' / 'app_integrations.py'),
        )
        yield SimpleNamespace(
            app=app_integrations,
            usage=usage_tracker,
            process_mentor_notification=process_mentor_notification,
            get_available_apps=get_available_apps,
            add_app_message=add_app_message,
            send_notification_async=send_notification_async,
        )


def test_realtime_integrations_feature_constant_exists(integration_harness):
    """REALTIME_INTEGRATIONS is a distinct stable usage bucket."""
    features = integration_harness.usage.Features
    assert features.REALTIME_INTEGRATIONS == 'realtime_integrations'
    assert features.REALTIME_INTEGRATIONS != features.APP_INTEGRATIONS
    assert features.REALTIME_INTEGRATIONS != features.NOTIFICATIONS


@pytest.mark.asyncio
async def test_mentor_notification_tracked_under_realtime_integrations(integration_harness):
    """The mentor coordinator enters the realtime-integration usage context."""
    app = integration_harness.app
    usage = integration_harness.usage
    captured_contexts = []
    original_track = usage.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append((uid, feature))
        with original_track(uid, feature):
            yield

    with patch.object(app, 'track_usage', spy_track_usage), patch.object(
        app,
        'process_mentor_notification',
        MagicMock(return_value=[{'text': 'hello'}]),
    ), patch.object(app, '_process_mentor_proactive_notification', MagicMock(return_value=None)):
        await app.trigger_realtime_integrations('user-rt-1', [{'text': 'hello'}], 'conv-1')

    assert ('user-rt-1', usage.Features.REALTIME_INTEGRATIONS) in captured_contexts


@pytest.mark.asyncio
async def test_no_tracking_when_no_llm_calls(integration_harness):
    """No mentor payload and no apps means no usage context is entered."""
    app = integration_harness.app
    usage = integration_harness.usage
    captured_contexts = []
    original_track = usage.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append((uid, feature))
        with original_track(uid, feature):
            yield

    with patch.object(app, 'track_usage', spy_track_usage), patch.object(
        app, 'process_mentor_notification', MagicMock(return_value=None)
    ), patch.object(app, 'get_available_apps', MagicMock(return_value=[])):
        await app.trigger_realtime_integrations('user-rt-2', [{'text': 'hello'}], 'conv-2')

    assert captured_contexts == []


@pytest.mark.asyncio
async def test_track_usage_context_entered_around_proactive_message(integration_harness):
    """Usage context surrounds the mentor processing call, including its exit."""
    app = integration_harness.app
    usage = integration_harness.usage
    call_log = []

    @contextmanager
    def spy_track_usage(uid, feature):
        call_log.append(('enter', uid, feature))
        yield
        call_log.append(('exit', uid, feature))

    def spy_process(*_args, **_kwargs):
        call_log.append(('process_called',))
        return 'Test notification'

    with patch.object(app, 'track_usage', spy_track_usage), patch.object(
        app,
        'process_mentor_notification',
        MagicMock(return_value=[{'text': 'hello'}]),
    ), patch.object(app, '_process_mentor_proactive_notification', spy_process):
        await app.trigger_realtime_integrations('user-rt-3', [{'text': 'hello'}], 'conv-3')

    marker = ('enter', 'user-rt-3', usage.Features.REALTIME_INTEGRATIONS)
    process_idx = call_log.index(('process_called',))
    enter_idx = call_log.index(marker)
    exit_idx = call_log.index(('exit', 'user-rt-3', usage.Features.REALTIME_INTEGRATIONS))
    assert enter_idx < process_idx < exit_idx


@pytest.mark.asyncio
async def test_audio_app_lookup_uses_db_executor_without_blocking_loop(integration_harness):
    app = integration_harness.app
    started = threading.Event()
    release = threading.Event()
    calls = []
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='test-app-lookup')

    def blocking_get_apps(uid):
        assert uid == 'user-audio'
        started.set()
        assert release.wait(timeout=2)
        return []

    async def routing_run_blocking(executor, func, *args, **kwargs):
        calls.append((executor, func, args, kwargs))
        if func is blocking_get_apps:
            call = functools.partial(func, *args, **kwargs)
            return await asyncio.get_running_loop().run_in_executor(worker, call)
        return func(*args, **kwargs)

    safety_release = threading.Timer(1, release.set)
    safety_release.start()
    try:
        with patch.object(app, 'run_blocking', routing_run_blocking), patch.object(
            app, 'get_available_apps', blocking_get_apps
        ):
            task = asyncio.create_task(app.trigger_realtime_audio_bytes('user-audio', 16_000, bytearray(b'audio')))
            deadline = asyncio.get_running_loop().time() + 0.75
            while not started.is_set() and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.005)
            assert started.is_set()

            loop_tick = asyncio.Event()
            asyncio.get_running_loop().call_soon(loop_tick.set)
            await asyncio.wait_for(loop_tick.wait(), timeout=1)
            assert not task.done()

            release.set()
            assert await task == {}
    finally:
        release.set()
        safety_release.cancel()
        worker.shutdown(wait=True)

    lookup_call = next(call for call in calls if call[1] is blocking_get_apps)
    assert lookup_call[0] is app.db_executor
    assert lookup_call[2] == ('user-audio',)


@pytest.mark.asyncio
async def test_trial_paywall_read_uses_db_executor_and_preserves_errors(integration_harness):
    app = integration_harness.app
    calls = []

    def failing_paywall(uid, source):
        assert (uid, source) == ('user-paywall', 'desktop')
        raise RuntimeError('paywall store unavailable')

    async def tracking_run_blocking(executor, func, *args, **kwargs):
        calls.append((executor, func, args, kwargs))
        return func(*args, **kwargs)

    with patch.object(app, 'run_blocking', tracking_run_blocking), patch.object(
        app, 'is_trial_paywalled', failing_paywall
    ):
        with pytest.raises(RuntimeError, match='paywall store unavailable'):
            await app.trigger_realtime_integrations('user-paywall', [{'text': 'hello'}], 'conv-1', source='desktop')

    assert calls == [(app.db_executor, failing_paywall, ('user-paywall', 'desktop'), {})]


@pytest.mark.asyncio
async def test_realtime_message_uses_async_notification_boundary(integration_harness):
    app = integration_harness.app
    external_app = _realtime_app()
    response = MagicMock(status_code=200, text='')
    response.json.return_value = {'message': 'A useful notification'}
    client = AsyncMock()
    client.post.return_value = response
    notifier = AsyncMock(return_value=None)

    with patch.object(app, 'get_available_apps', return_value=[external_app]), patch.object(
        app, 'process_mentor_notification', return_value=None
    ), patch.object(app, 'get_webhook_client', return_value=client), patch.object(
        app, 'send_app_notification_async', notifier
    ):
        result = await app.trigger_realtime_integrations('user-message', [{'text': 'hello'}], 'conv-1')

    notifier.assert_awaited_once_with('user-message', 'Test App', 'app-1', 'A useful notification')
    assert result == [{'id': 'msg-1'}]


@pytest.mark.asyncio
async def test_realtime_notification_failure_remains_fail_soft(integration_harness):
    app = integration_harness.app
    external_app = _realtime_app()
    response = MagicMock(status_code=200, text='')
    response.json.return_value = {'message': 'A useful notification'}
    client = AsyncMock()
    client.post.return_value = response
    integration_harness.add_app_message.reset_mock()

    with patch.object(app, 'get_available_apps', return_value=[external_app]), patch.object(
        app, 'process_mentor_notification', return_value=None
    ), patch.object(app, 'get_webhook_client', return_value=client), patch.object(
        app, 'send_app_notification_async', AsyncMock(side_effect=RuntimeError('fcm unavailable'))
    ):
        result = await app.trigger_realtime_integrations('user-message', [{'text': 'hello'}], 'conv-1')

    assert result == []
    integration_harness.add_app_message.assert_not_called()
