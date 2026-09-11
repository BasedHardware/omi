"""Regression test: a webhook's documented no-notification response must not
log an ERROR, and a present-but-invalid notification payload must be a typed
rejection instead of a crash swallowed by the dispatch boundary.

Production loop sensor (30-min window, pusher service) ranked this signature
among the largest non-auth error sources:

    ERROR:utils.app_integrations:App <app-id> is not proactive_notification
    or data invalid <uid>

The realtime webhook contract (docs/doc/developer/apps/Notifications.mdx)
documents two response shapes: one WITH a ``notification`` object and one
without — "Response (when no notification needed): {"session_id": ..."}".
The dispatch site gated only on the app capability and passed
``response_data.get('notification', None)`` unconditionally, so the second,
fully documented shape reached ``_process_proactive_notification`` with
``data=None``, whose combined guard
``not app.has_capability(...) or not data`` logged the absence at ERROR level
on every such webhook call. The capability half of that guard was unreachable
from this call site (the caller had already checked it), so in production the
signature was exclusively the benign-absence case.

The fix has two halves, both covered here:

1. The dispatch site treats an absent ``notification`` key as the documented
   no-op: it does not dispatch and does not log. A present payload still
   dispatches under the capability gate exactly as before.
2. The processor's collapsed guard is split. The capability half stays (for
   direct callers) and the data half becomes a typed ``Mapping`` validation,
   so a present-but-non-mapping payload (e.g. a bare JSON string) is rejected
   with one typed ERROR instead of raising ``AttributeError`` inside
   ``data.get(...)`` — which the dispatch boundary previously swallowed with
   ``except Exception: pass``, silently dropping the notification with no log
   at all.

Failure-Class: new — instance fix; the violated contract is the realtime
webhook response contract (absent ``notification`` key is a documented
no-op, not an error condition) at the dispatch boundary in
``utils.app_integrations._async_trigger_realtime_integrations``.
"""

import asyncio as _asyncio
import logging
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


class _UnsafeWebhookURLError(Exception):
    """Isolated stand-in for ``utils.http_client.UnsafeWebhookURLError``.

    Production's SSRF guard catches this to reject non-public webhook URLs
    without tripping the circuit breaker, so the stub must expose a genuine
    exception class — the ``AutoMockModule`` default is a non-exception
    ``MagicMock`` that the production ``except`` clause can neither raise nor
    match, turning the guard into a ``TypeError``.
    """


@pytest.fixture
def integration_harness() -> Iterator[SimpleNamespace]:
    """Load the production coordinator fresh, with every blocking dependency
    stubbed, mirroring the sanctioned isolation harness used by
    test_realtime_integrations_usage_tracking.py."""
    process_mentor_notification = MagicMock(return_value=None)
    get_available_apps = MagicMock(return_value=[])
    add_app_message = MagicMock(return_value={'id': 'msg-1'})
    send_notification_async = AsyncMock(return_value=None)
    proactive_processor = MagicMock(return_value=None)

    async def run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def gather_safe(*awaitables, **_kwargs):
        return await _asyncio.gather(*awaitables)

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
            publish_proactive_message=MagicMock(),
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
            ACTION_NONE=0,
            ACTION_WARN_DAY1=1,
            ACTION_WARN_DAY2=2,
            ACTION_DISABLE=3,
            ACTION_REDIRECT_NOT_FOLLOWED=4,
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
            get_webhook_semaphore=MagicMock(return_value=_asyncio.Semaphore(1)),
            latest_wins_start=MagicMock(return_value=1),
            latest_wins_check=MagicMock(return_value=True),
            safe_request_target=MagicMock(side_effect=lambda url: (url, {'headers': {}, 'extensions': {}})),
            UnsafeWebhookURLError=_UnsafeWebhookURLError,
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
            redact_conversation_for_integration=MagicMock(side_effect=lambda value: value),
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
        'utils.llm.temporal': _auto_module(
            'utils.llm.temporal',
            current_date_for_uid=MagicMock(return_value='2026-01-01'),
        ),
        'utils.llms.memory': _module(
            'utils.llms.memory',
            get_prompt_memories=MagicMock(return_value=('', '')),
        ),
        'utils.log_sanitizer': _module(
            'utils.log_sanitizer',
            sanitize=MagicMock(side_effect=lambda value: value),
            sanitize_pii=MagicMock(side_effect=lambda value: value),
        ),
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
            get_available_apps=get_available_apps,
            proactive_processor=proactive_processor,
        )


def _realtime_app(app_id: str = 'app-1') -> MagicMock:
    """An enabled external-integration app with the proactive_notification
    capability and a reachable webhook — the exact population the production
    signature was emitted for."""
    app = MagicMock()
    app.id = app_id
    app.name = f'App {app_id}'
    app.uid = 'owner-uid'
    app.enabled = True
    app.external_integration.webhook_url = f'https://{app_id}.test/hook'
    app.triggers_realtime.return_value = True
    app.triggers_realtime_audio_bytes.return_value = False
    app.has_capability.return_value = True
    return app


def _ok_webhook_client(payload: dict) -> MagicMock:
    response = MagicMock(status_code=200, text='')
    response.json.return_value = payload
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_no_notification_response_does_not_log_error(integration_harness, caplog):
    """The documented no-notification webhook response must complete without
    any ERROR-level record from the proactive-notification path.

    On the unfixed code this emitted
    ``App <id> is not proactive_notification or data invalid <uid>`` at ERROR
    for every webhook call whose response omitted ``notification`` — the exact
    production signature ranked by the loop sensor."""
    app = integration_harness.app
    harness_app = _realtime_app('app-noop')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _ok_webhook_client({'session_id': 'abc123'})  # documented no-op shape

    with patch.object(app, 'get_webhook_client', return_value=client), patch.object(
        app, '_process_proactive_notification', integration_harness.proactive_processor
    ):
        with caplog.at_level(logging.ERROR, logger='utils.app_integrations'):
            await app.trigger_realtime_integrations('uid-noop', [{'text': 'hi'}], 'conv-1')

    error_records = [
        r for r in caplog.records if r.levelno >= logging.ERROR and 'proactive_notification' in r.getMessage()
    ]
    assert not error_records, [f'documented no-op response still logs ERROR: {r.getMessage()}' for r in error_records]
    # And the processor is not dispatched for an absent payload at all.
    integration_harness.proactive_processor.assert_not_called()


@pytest.mark.asyncio
async def test_present_valid_notification_still_dispatches(integration_harness):
    """A present, dict notification payload dispatches to the processor with
    the same arguments as before the fix — the happy path is unchanged."""
    app = integration_harness.app
    harness_app = _realtime_app('app-yes')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _ok_webhook_client({'notification': {'prompt': 'Help'}})

    with patch.object(app, 'get_webhook_client', return_value=client), patch.object(
        app, '_process_proactive_notification', integration_harness.proactive_processor
    ):
        await app.trigger_realtime_integrations('uid-yes', [{'text': 'hi'}], 'conv-1')

    integration_harness.proactive_processor.assert_called_once_with('uid-yes', harness_app, {'prompt': 'Help'})


@pytest.mark.asyncio
async def test_non_dict_notification_payload_is_typed_rejection_not_crash(integration_harness, caplog):
    """A present-but-non-mapping notification payload is a typed rejection.

    On the unfixed code the truthiness guard ``or not data`` admitted any
    truthy non-dict (a bare JSON string), so ``data.get('prompt', '')`` raised
    ``AttributeError`` inside the processor and the dispatch boundary's
    ``except Exception: pass`` swallowed it — the notification was silently
    dropped with no log line at all. The fixed processor rejects the payload
    with one typed ERROR naming the actual type."""
    app = integration_harness.app
    harness_app = _realtime_app('app-badtype')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _ok_webhook_client({'notification': 'a bare string is not a prompt template'})

    with patch.object(app, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.ERROR, logger='utils.app_integrations'):
            # Must not raise: the dispatch boundary stays fire-and-forget.
            await app.trigger_realtime_integrations('uid-badtype', [{'text': 'hi'}], 'conv-1')

    typed_rejections = [
        r for r in caplog.records if r.levelno >= logging.ERROR and 'data invalid type=' in r.getMessage()
    ]
    assert typed_rejections, (
        'a present-but-invalid payload must produce one typed ERROR, not an '
        'AttributeError swallowed by the dispatch boundary'
    )
    assert 'str' in typed_rejections[0].getMessage()


def test_empty_notification_payload_rejected_before_llm(integration_harness):
    """A present-but-empty ``notification`` object (``{}``) must not reach the LLM.

    The old truthiness guard rejected this shape (``not data``); the typed
    Mapping validation that replaces it accepts every mapping, including the
    empty one, so the empty check is what preserves the old rejection. Without
    it the processor invokes the LLM on an empty prompt — a billed call that
    can never produce a notification (no ``prompt`` key, no ``params``).
    """
    app_module = integration_harness.app
    empty_app = _realtime_app('app-empty')
    # Scopes resolve to a real list so the only variable under test is the
    # payload guard: an empty mapping must return before any LLM work.
    empty_app.filter_proactive_notification_scopes = MagicMock(return_value=[])

    result = app_module._process_proactive_notification('uid-empty', empty_app, {})

    assert result is None
    app_module.get_llm.assert_not_called()


def test_processor_rejects_missing_capability_as_error(integration_harness, caplog):
    """Direct callers losing the capability gate still get an explicit ERROR:
    the capability half of the old collapsed guard is preserved for callers
    that do not pre-check it (the realtime site does)."""
    app_module = integration_harness.app
    no_cap_app = _realtime_app('app-nocap')
    no_cap_app.has_capability.return_value = False

    with caplog.at_level(logging.ERROR, logger='utils.app_integrations'):
        result = app_module._process_proactive_notification('uid-nocap', no_cap_app, {'prompt': 'x'})

    assert result is None
    assert any(
        'lacks proactive_notification capability' in r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.ERROR
    )
