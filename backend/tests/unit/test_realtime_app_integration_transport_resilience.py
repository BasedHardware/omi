"""Regression tests: realtime app-integration webhook failures must be typed,
attributed, and given one bounded transport retry.

Production loop sensor (30-min window, pusher service):

    ERROR:utils.app_integrations:App integration error:
    ERROR:utils.app_integrations:Plugin integration error:

Both realtime app-webhook lanes ended in ``logger.error(f"...: {e}")``.
Transport exceptions stringify empty remarkably often (every ``httpx.ConnectError``
raised without a message), so production emitted ERROR records with neither the
app nor the failure kind — impossible to attribute to an app, alert on, or
count by cause. The sibling durable lane in the same file already logged the
solved shape (``app=%s error=%s`` with the type name); the realtime lanes were
a two-site regression of that pattern. Worse, a transport error cost the
delivery outright and ticked the per-URL circuit breaker, so a single 2-second
connect blip on a busy endpoint accumulated toward opening the breaker and
dropping every subsequent delivery.

The fix, covered here:

1. Every realtime failure record carries the app id and a bounded, typed
   error token (``ConnectError`` or ``ConnectError: refused`` — never an
   empty message), in the log line and in the webhook-health record alike.
2. Transport-level faults (``httpx.TransportError``, ``TimeoutError``) get
   exactly one short in-place retry — a transport fault is a property of the
   dial, not of the payload. HTTP responses are never retried (a repeat post
   of the same payload can only reproduce the status), and the send
   semaphore is acquired per attempt so the retry delay cannot hold the
   global webhook concurrency bound hostage.
3. The audio lane's latest-wins supersession stays silent bookkeeping: an
   intentionally abandoned send records neither a breaker failure nor a
   webhook-health failure.
4. Everything that already worked keeps working: SSRF rejection, the open
   breaker short-circuit, non-2xx handling, and journey outcomes.

Failure-Class: new — instance fix; the violated contract is realtime
app-webhook failure attribution and bounded transport retry at
``utils.app_integrations`` ``_async_trigger_realtime_integrations`` and
``_async_trigger_realtime_audio_bytes``.
"""

import asyncio as _asyncio
import logging
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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

    The production SSRF guard catches this exact class to reject non-public
    webhook URLs without tripping the circuit breaker; an AutoMockModule
    default would be a non-exception MagicMock the ``except`` clause can neither
    raise nor match.
    """


class _ProactivityDenied(Exception):
    """Isolated stand-in for ``config.proactivity_v2.ProactivityDenied``."""


class _ClientJourneyAttempt:
    """Records the outcome the production code reports for the delivery."""

    def __init__(self, journey: str, client_kind: Any = None):
        self.journey = journey
        self.client_kind = client_kind
        self.outcome = None

    def succeed(self) -> None:
        self.outcome = ('succeed',)

    def fail(self, issue: str) -> None:
        self.outcome = ('fail', issue)

    def cancel(self, *args: Any, **kwargs: Any) -> None:
        self.outcome = ('cancel',)


@pytest.fixture
def integration_harness() -> Iterator[SimpleNamespace]:
    """Load the production coordinator fresh, with every blocking dependency
    stubbed, mirroring the sanctioned isolation harness used by
    test_proactive_notification_absent_payload.py."""
    get_available_apps = MagicMock(return_value=[])

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
        'utils.observability': _package('utils.observability', BACKEND_DIR / 'utils' / 'observability'),
        'database': _package('database', BACKEND_DIR / 'database'),
        'models': _package('models', BACKEND_DIR / 'models'),
        'config': _package('config', BACKEND_DIR / 'config'),
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
            incr_daily_notification_count=MagicMock(),
            get_daily_notification_count=MagicMock(return_value=0),
            publish_proactive_message=MagicMock(),
        ),
        'database.apps': _auto_module(
            'database.apps',
            get_app_by_id_db=MagicMock(return_value=None),
            record_app_usage=MagicMock(),
        ),
        'database.webhook_health': _module(
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
            add_app_message=MagicMock(return_value={'id': 'msg-1'}),
            get_app_messages=MagicMock(return_value=[]),
        ),
        'database.goals': _auto_module('database.goals', get_user_goals=MagicMock(return_value=[])),
        'database.users': _auto_module(
            'database.users',
            get_user_language_preference=MagicMock(return_value='en'),
        ),
        'database.mentor_gate_state': _auto_module('database.mentor_gate_state'),
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
        'models.transcript_segment': _module(
            'models.transcript_segment',
            transcript_segment_for_client=lambda segment: segment,
        ),
        'utils.http_client': _auto_module(
            'utils.http_client',
            get_webhook_client=MagicMock(),
            get_webhook_circuit_breaker=MagicMock(return_value=circuit_breaker),
            get_webhook_semaphore=MagicMock(return_value=_asyncio.Semaphore(10)),
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
        'utils.journey_metrics_contract': _module(
            'utils.journey_metrics_contract',
            ClientKind=str,
            bounded_client_kind=lambda kind: kind,
            resolve_client_kind=lambda **_kwargs: 'unknown',
        ),
        'utils.observability.journeys': _module(
            'utils.observability.journeys',
            ClientJourneyAttempt=_ClientJourneyAttempt,
        ),
        'utils.observability.fallback': _module(
            'utils.observability.fallback',
            record_fallback=MagicMock(),
        ),
        'utils.proactivity_flags': _auto_module('utils.proactivity_flags'),
        'utils.mentor_admission': _auto_module(
            'utils.mentor_admission',
            mentor_plan_allows_evaluation=MagicMock(return_value=True),
        ),
        'config.proactivity_v2': _module(
            'config.proactivity_v2',
            ProactivityDenied=_ProactivityDenied,
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
            send_notification_async=AsyncMock(return_value=None),
        ),
        'utils.notification_dispatch': _auto_module(
            'utils.notification_dispatch',
            dispatch_notification=MagicMock(),
            dispatch_notification_async=AsyncMock(return_value=None),
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
            process_mentor_notification=MagicMock(return_value=None),
        ),
    }

    with stub_modules(stubs):
        app_integrations = load_module_fresh(
            'utils.app_integrations',
            str(BACKEND_DIR / 'utils' / 'app_integrations.py'),
        )
        yield SimpleNamespace(
            app=app_integrations,
            get_available_apps=get_available_apps,
            circuit_breaker=circuit_breaker,
        )


def _realtime_app(app_id: str = 'app-1') -> MagicMock:
    """An enabled external-integration app with a reachable webhook — the
    population the production signature was emitted for."""
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


def _audio_app(app_id: str = 'app-audio') -> MagicMock:
    app = _realtime_app(app_id)
    app.triggers_realtime.return_value = False
    app.triggers_realtime_audio_bytes.return_value = True
    return app


def _client_posting(side_effects: Any) -> MagicMock:
    """A webhook client whose ``post`` returns/raises the given outcome(s).

    A single response becomes ``return_value``; a single exception instance or
    a list (responses and/or exceptions, consumed in call order) becomes
    ``side_effect``. Passing a bare MagicMock response as ``side_effect`` would
    *call* it (MagicMock is callable) and hand back a fresh child mock whose
    ``status_code`` is not an int."""
    client = MagicMock()
    if isinstance(side_effects, list):
        client.post = AsyncMock(side_effect=side_effects)
    elif isinstance(side_effects, BaseException):
        client.post = AsyncMock(side_effect=side_effects)
    else:
        client.post = AsyncMock(return_value=side_effects)
    return client


def _ok_response(status_code: int = 200, payload: Any = None) -> MagicMock:
    response = MagicMock(status_code=status_code, text='')
    response.json.return_value = payload or {}
    return response


def _error_records(caplog, marker: str) -> list:
    return [r for r in caplog.records if r.levelno >= logging.ERROR and marker in r.getMessage()]


def _warning_records(caplog, marker: str) -> list:
    return [r for r in caplog.records if r.levelno == logging.WARNING and marker in r.getMessage()]


@pytest.mark.asyncio
async def test_empty_connect_error_is_typed_and_attributed(integration_harness, caplog):
    """The headline signature: a message-less httpx.ConnectError must produce
    an ERROR record naming the app and the exception type — never the bare
    ``App integration error: `` line the sensor ranked.

    On the unfixed code the record text was ``App integration error: `` (empty
    exception string): no app id, no failure kind, unattributable."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-blind')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(httpx.ConnectError(''))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.ERROR, logger='utils.app_integrations'):
            await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    records = _error_records(caplog, 'App integration error')
    assert records, 'expected the transport failure to be logged at ERROR'
    message = records[0].getMessage()
    assert 'app=app-blind' in message, f'app id missing from failure log: {message!r}'
    assert 'ConnectError' in message, f'exception type missing from failure log: {message!r}'
    assert not any(
        r.getMessage().rstrip().endswith('App integration error:') for r in records
    ), 'the unattributed empty-message signature must not come back'


@pytest.mark.asyncio
async def test_transport_blip_recovers_without_recording_failure(integration_harness, caplog):
    """One connect blip must not cost the delivery: the send is retried once,
    succeeds, and no breaker or webhook-health failure is recorded.

    On the unfixed code the first ConnectError abandoned the delivery, ticked
    the breaker, and logged an ERROR — a busy-but-healthy endpoint accumulated
    failures toward the open-breaker state on transient blips alone."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-blip')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting([httpx.ConnectError('connection reset'), _ok_response()])

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.WARNING, logger='utils.app_integrations'):
            await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 2, 'exactly one retry after a transport fault'
    integration_harness.circuit_breaker.record_failure.assert_not_called()
    integration_harness.circuit_breaker.record_success.assert_called_once()
    app_module.record_app_webhook_failure.assert_not_called()
    app_module.record_app_webhook_success.assert_called_once()
    retries = _warning_records(caplog, 'App integration transport retry')
    assert retries and 'app=app-blip' in retries[0].getMessage()
    assert not _error_records(caplog, 'App integration error')


@pytest.mark.asyncio
async def test_audio_lane_empty_connect_error_is_typed_and_attributed(integration_harness, caplog):
    """The sibling signature: the audio-bytes lane must not emit the bare
    ``Plugin integration error: `` line either."""
    app_module = integration_harness.app
    harness_app = _audio_app('app-audio-blind')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(httpx.ConnectError(''))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.ERROR, logger='utils.app_integrations'):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    records = _error_records(caplog, 'Plugin integration error')
    assert records, 'expected the audio transport failure to be logged at ERROR'
    message = records[0].getMessage()
    assert 'app=app-audio-blind' in message, f'app id missing from failure log: {message!r}'
    assert 'ConnectError' in message, f'exception type missing from failure log: {message!r}'


@pytest.mark.asyncio
async def test_exhausted_transport_retries_fail_typed_with_single_failure_recorded(integration_harness, caplog):
    """When the retry also fails, exactly one breaker tick and one
    webhook-health failure are recorded — the retry must not multiply the
    bookkeeping — and the final ERROR still names the app and the type."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-dead')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(httpx.ConnectError(''))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.WARNING, logger='utils.app_integrations'):
            await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 2, 'one initial dial plus one bounded retry'
    integration_harness.circuit_breaker.record_failure.assert_called_once()
    app_module.record_app_webhook_failure.assert_called_once()
    failure_args = app_module.record_app_webhook_failure.call_args
    assert failure_args.args[0] == 'app-dead'
    assert failure_args.args[1] == 0
    assert 'ConnectError' in failure_args.args[2]
    retries = _warning_records(caplog, 'App integration transport retry')
    assert len(retries) == 1, 'the retry itself is warned exactly once, with attribution'
    assert 'app=app-dead' in retries[0].getMessage()
    final_errors = _error_records(caplog, 'App integration error')
    assert final_errors and 'app=app-dead' in final_errors[0].getMessage()


@pytest.mark.asyncio
async def test_http_status_is_never_retried(integration_harness):
    """A non-2xx HTTP answer is a property of the payload/target, not of the
    dial: it must get no transport retry — the callers' status handling (breaker
    tick, webhook health, journey outcome) sees it once."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-500')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(_ok_response(status_code=500))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 1, 'HTTP responses are never retried'
    integration_harness.circuit_breaker.record_failure.assert_called_once()
    app_module.record_app_webhook_failure.assert_called_once()
    assert app_module.record_app_webhook_failure.call_args.args[1] == 500


@pytest.mark.asyncio
async def test_timeout_gets_the_same_bounded_transport_retry(integration_harness):
    """Read timeouts ride the same dial-fault path: one retry, then the typed
    failure — TimeoutError keeps its journey classification upstream."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-slow')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting([TimeoutError(), _ok_response()])

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 2
    integration_harness.circuit_breaker.record_failure.assert_not_called()


@pytest.mark.asyncio
async def test_audio_lane_retry_succeeds_after_transport_blip(integration_harness):
    """The audio lane gets the same bounded retry; the superseded check inside
    ``send_once`` re-runs per attempt, so a retry cannot duplicate a send the
    newer call already replaced."""
    app_module = integration_harness.app
    harness_app = _audio_app('app-audio-blip')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting([httpx.ConnectError('reset'), _ok_response()])

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    assert client.post.await_count == 2
    integration_harness.circuit_breaker.record_failure.assert_not_called()
    integration_harness.circuit_breaker.record_success.assert_called_once()
    app_module.record_app_webhook_failure.assert_not_called()


@pytest.mark.asyncio
async def test_audio_lane_superseded_send_is_silent_bookkeeping(integration_harness):
    """A send superseded by a newer call after acquiring the semaphore is an
    intentional abandon: no breaker tick, no webhook-health failure, no ERROR.

    On the unfixed code the bare ``return`` made this path silent already, but
    it was also untyped: the supersession was implemented as a mid-send return
    inside the semaphore block, which the retry helper cannot express — the
    typed signal is what lets the send participate in the bounded retry
    without turning a supersession into a recorded failure."""
    app_module = integration_harness.app
    harness_app = _audio_app('app-superseded')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(_ok_response())
    # The latest-wins gate rejects once the semaphore has been acquired.
    checks = {'calls': 0}

    def flip_after_first(_uid, _version):
        checks['calls'] += 1
        return checks['calls'] > 1

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with patch.object(app_module, 'latest_wins_check', side_effect=flip_after_first):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    client.post.assert_not_awaited()
    integration_harness.circuit_breaker.record_failure.assert_not_called()
    app_module.record_app_webhook_failure.assert_not_called()
    integration_harness.circuit_breaker.record_success.assert_not_called()


@pytest.mark.asyncio
async def test_ssrf_rejection_and_open_breaker_unchanged(integration_harness, caplog):
    """The guards around the send keep their contracts: a non-public URL is
    rejected with no failure recorded, and an open breaker short-circuits
    before any dial."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-guarded')
    integration_harness.get_available_apps.return_value = [harness_app]

    def reject_unsafe(url):
        raise app_module.UnsafeWebhookURLError('private address')

    with patch.object(app_module, 'safe_request_target', side_effect=reject_unsafe):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')
    integration_harness.circuit_breaker.record_failure.assert_not_called()

    integration_harness.circuit_breaker.allow_request.return_value = False
    client = _client_posting(_ok_response())
    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')
    client.post.assert_not_awaited()
    integration_harness.circuit_breaker.record_failure.assert_not_called()


@pytest.mark.asyncio
async def test_success_path_unchanged_after_restructure(integration_harness, caplog):
    """The healthy path behaves exactly as before: one dial, success recorded,
    message consumed, no retry or error records."""
    app_module = integration_harness.app
    harness_app = _realtime_app('app-happy')
    integration_harness.get_available_apps.return_value = [harness_app]
    client = _client_posting(_ok_response(payload={'message': 'all good'}))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.WARNING, logger='utils.app_integrations'):
            result = await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 1
    integration_harness.circuit_breaker.record_success.assert_called_once()
    app_module.record_app_webhook_success.assert_called_once()
    assert result == [{'id': 'msg-1'}]
    assert not _warning_records(caplog, 'transport retry')
    assert not _error_records(caplog, 'App integration error')


@pytest.mark.asyncio
async def test_transport_error_token_is_bounded_and_typed(integration_harness):
    """The token builder itself: type always present, message only when
    non-empty, newlines collapsed, overlong messages truncated."""
    app_module = integration_harness.app
    assert app_module._transport_error_str(httpx.ConnectError('')) == 'ConnectError'
    assert app_module._transport_error_str(httpx.ConnectError('refused')) == 'ConnectError: refused'
    collapsed = app_module._transport_error_str(ValueError('line one\nline two'))
    assert collapsed == 'ValueError: line one line two'
    assert len(app_module._transport_error_str(ValueError('x' * 500))) <= len('ValueError: ') + 120


class _JourneyRecorder:
    """Patches ``ClientJourneyAttempt`` and records every reported outcome."""

    instances: list

    def __init__(self, journey: str, client_kind: Any = None):
        self.journey = journey
        self.client_kind = client_kind
        self.outcome = None
        _JourneyRecorder.instances.append(self)

    def succeed(self) -> None:
        self.outcome = ('succeed',)

    def fail(self, issue: str) -> None:
        self.outcome = ('fail', issue)

    def cancel(self, *args: Any, **kwargs: Any) -> None:
        self.outcome = ('cancel',)


@pytest.fixture
def journeys(integration_harness):
    _JourneyRecorder.instances = []
    with patch.object(integration_harness.app, 'ClientJourneyAttempt', _JourneyRecorder):
        yield _JourneyRecorder.instances


@pytest.mark.asyncio
async def test_journey_outcome_provider_error_on_exhausted_connect_error(integration_harness, journeys):
    """After the bounded retry is spent, a connect failure is classified
    ``provider_error`` — not silently dropped without a journey record."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-j1')]
    client = _client_posting(httpx.ConnectError(''))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert len(journeys) == 1
    assert journeys[0].outcome == ('fail', 'provider_error')


@pytest.mark.asyncio
async def test_journey_outcome_timeout_classification_after_retry_exhaustion(integration_harness, journeys):
    """A timeout that survives the retry keeps the existing
    ``upstream_timeout`` classification (the retry must not reclassify it)."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-j2')]
    client = _client_posting(TimeoutError())

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 2
    assert journeys[0].outcome == ('fail', 'upstream_timeout')


@pytest.mark.asyncio
async def test_journey_outcome_upstream_rejected_on_5xx(integration_harness, journeys):
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-j3')]
    client = _client_posting(_ok_response(status_code=503))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert journeys[0].outcome == ('fail', 'upstream_rejected')


@pytest.mark.asyncio
async def test_journey_outcome_success_on_200(integration_harness, journeys):
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-j4')]
    client = _client_posting(_ok_response())

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert journeys[0].outcome == ('succeed',)


@pytest.mark.asyncio
async def test_journey_outcome_dependency_unavailable_on_open_breaker(integration_harness, journeys):
    """An open breaker never dials and reports ``dependency_unavailable`` —
    unchanged by the retry restructure."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-j5')]
    integration_harness.circuit_breaker.allow_request.return_value = False
    client = _client_posting(_ok_response())

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    client.post.assert_not_awaited()
    assert journeys[0].outcome == ('fail', 'dependency_unavailable')


@pytest.mark.asyncio
async def test_external_app_usage_recorded_on_success(integration_harness):
    """Success bookkeeping is untouched: an app owned by another user records
    ``transcript_processed_external_integration`` usage for the conversation."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-usage')]
    client = _client_posting(_ok_response())

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-77')

    app_module.record_app_usage.assert_called_once()
    usage_args = app_module.record_app_usage.call_args
    assert usage_args.args[0] == 'uid-1' and usage_args.args[1] == 'app-usage'
    assert usage_args.args[2] == app_module.UsageHistoryType.transcript_processed_external_integration
    assert usage_args.kwargs.get('conversation_id') == 'conv-77'


@pytest.mark.asyncio
async def test_message_notification_dispatched_on_success(integration_harness):
    """A webhook response carrying a ``message`` still fans out the app
    notification — the retry wrapper changed nothing about the payload path."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-msg')]
    client = _client_posting(_ok_response(payload={'message': 'hello there'}))
    notify = AsyncMock(return_value=None)

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with patch.object(app_module, 'send_app_notification_async', notify):
            await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    notify.assert_awaited_once()
    assert notify.await_args.args[3] == 'hello there'


@pytest.mark.asyncio
async def test_proactive_notification_dispatched_when_present(integration_harness):
    """A present ``notification`` payload still reaches the processor under the
    capability gate (the documented with-notification contract shape)."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-proactive')]
    client = _client_posting(_ok_response(payload={'notification': {'prompt': 'Help'}}))
    processor = MagicMock(return_value='proactive result')

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with patch.object(app_module, '_process_proactive_notification', processor):
            with patch.object(app_module, 'track_usage', MagicMock()):
                await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    processor.assert_called_once_with(
        'uid-1', integration_harness.get_available_apps.return_value[0], {'prompt': 'Help'}
    )


@pytest.mark.asyncio
async def test_audio_lane_5xx_never_retried(integration_harness):
    """Audio lane symmetry: a 500 is answered once — status handling, breaker
    tick, and webhook-health record all fire exactly once, no transport retry."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_audio_app('app-audio-500')]
    client = _client_posting(_ok_response(status_code=502))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    assert client.post.await_count == 1
    integration_harness.circuit_breaker.record_failure.assert_called_once()
    app_module.record_app_webhook_failure.assert_called_once()
    assert app_module.record_app_webhook_failure.call_args.args[1] == 502


@pytest.mark.asyncio
async def test_audio_lane_non_transport_exception_typed_no_retry(integration_harness):
    """A non-transport exception is not a dial fault: no retry, and the
    failure log names the app and the exception type (never the bare
    ``Plugin integration error: `` signature)."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_audio_app('app-audio-boom')]
    client = _client_posting(RuntimeError('codec exploded'))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    assert client.post.await_count == 1, 'non-transport faults are not retried'
    app_module.record_app_webhook_failure.assert_called_once()
    assert 'RuntimeError' in app_module.record_app_webhook_failure.call_args.args[2]


@pytest.mark.asyncio
async def test_transcript_lane_non_transport_exception_typed_no_retry(integration_harness):
    """Transcript lane: a generic exception from the send gets one dial, a
    single recorded failure, and a typed, attributed ERROR."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-boom')]
    client = _client_posting(RuntimeError('encoder exploded'))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 1
    integration_harness.circuit_breaker.record_failure.assert_called_once()
    app_module.record_app_webhook_failure.assert_called_once()
    assert 'RuntimeError' in app_module.record_app_webhook_failure.call_args.args[2]


@pytest.mark.asyncio
async def test_send_helper_returns_response_without_retry_and_raises_after_exhaustion(integration_harness):
    """The helper contract in isolation: a response short-circuits (no retry),
    and an exception that survives every attempt is re-raised with its original
    type so upstream classification (e.g. TimeoutError) keeps working."""
    app_module = integration_harness.app
    good = _ok_response()
    response = await app_module._send_with_transport_retry('app-x', _asyncio_sleep_free(good))
    assert response is good

    async def always_raise():
        raise httpx.ConnectError('nope')

    with pytest.raises(httpx.ConnectError):
        await app_module._send_with_transport_retry('app-x', always_raise)


def _asyncio_sleep_free(response):
    async def send_once():
        return response

    return send_once


@pytest.mark.asyncio
async def test_audio_lane_superseded_before_semaphore_dials_nothing(integration_harness):
    """Supersession before the semaphore is still the plain silent skip: no
    dial, no bookkeeping."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_audio_app('app-early-out')]
    client = _client_posting(_ok_response())

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with patch.object(app_module, 'latest_wins_check', MagicMock(return_value=False)):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    client.post.assert_not_awaited()
    integration_harness.circuit_breaker.record_failure.assert_not_called()
    app_module.record_app_webhook_failure.assert_not_called()


@pytest.mark.asyncio
async def test_semaphore_released_during_retry_delay(integration_harness):
    """The send semaphore is acquired and released per attempt: the retry
    delay happens OUTSIDE the semaphore, so one destination's connect blip
    cannot serialize the whole webhook fan-out behind it."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_realtime_app('app-sem')]
    client = _client_posting([httpx.ConnectError('reset'), _ok_response()])
    events: list = []

    class TrackedSemaphore:
        def __init__(self):
            self._sem = _asyncio.Semaphore(10)

        async def __aenter__(self):
            events.append('acquire')
            return await self._sem.__aenter__()

        async def __aexit__(self, *args):
            events.append('release')
            return await self._sem.__aexit__(*args)

    async def fake_sleep(delay):
        events.append(f'sleep:{delay}')

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with patch.object(app_module, 'get_webhook_semaphore', MagicMock(return_value=TrackedSemaphore())):
            with patch('utils.app_integrations.asyncio.sleep', fake_sleep):
                await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert events == ['acquire', 'release', 'sleep:0.5', 'acquire', 'release'], events


@pytest.mark.asyncio
async def test_transport_retry_budget_is_one_short_retry(integration_harness):
    """Pin the retry budget itself: exactly one dial-fault retry at a short
    delay. A longer schedule belongs to the durable/developer-webhook lanes;
    the realtime lanes must stay bounded to protect live latency."""
    app_module = integration_harness.app
    assert app_module._TRANSPORT_RETRY_DELAYS == (0.5,)


@pytest.mark.asyncio
async def test_audio_lane_exhausted_connect_records_single_typed_failure(integration_harness, caplog):
    """Audio lane exhaustion symmetry: two dials, one breaker tick, one typed
    webhook-health failure, one attributed ERROR."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_audio_app('app-audio-dead')]
    client = _client_posting(httpx.ConnectError(''))

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.WARNING, logger='utils.app_integrations'):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    assert client.post.await_count == 2
    integration_harness.circuit_breaker.record_failure.assert_called_once()
    app_module.record_app_webhook_failure.assert_called_once()
    assert 'ConnectError' in app_module.record_app_webhook_failure.call_args.args[2]
    final_errors = _error_records(caplog, 'Plugin integration error')
    assert final_errors and 'app=app-audio-dead' in final_errors[0].getMessage()


@pytest.mark.asyncio
async def test_retry_warning_names_app_and_attempt_budget(integration_harness, caplog):
    """The in-flight retry is observable at WARNING with the app id and the
    attempt budget — operators can see the blip without an ERROR page."""
    app_module = integration_harness.app
    integration_harness.get_available_apps.return_value = [_audio_app('app-audio-warn')]
    client = _client_posting([httpx.ConnectError('reset'), _ok_response()])

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        with caplog.at_level(logging.WARNING, logger='utils.app_integrations'):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))

    retries = _warning_records(caplog, 'App integration transport retry')
    assert len(retries) == 1
    message = retries[0].getMessage()
    assert 'app=app-audio-warn' in message
    assert 'attempt=1/2' in message
    assert not _error_records(caplog, 'Plugin integration error')


@pytest.mark.asyncio
async def test_one_failing_app_does_not_block_sibling_apps(integration_harness):
    """Fan-out isolation is preserved under the retry wrapper: an app stuck in
    connect-error retries and fails alone while a healthy sibling still
    receives its delivery and records success."""
    app_module = integration_harness.app
    dead = _realtime_app('app-dead-sibling')
    alive = _realtime_app('app-alive-sibling')
    integration_harness.get_available_apps.return_value = [dead, alive]

    async def post(url, *args, **kwargs):
        if 'app-dead-sibling' in str(url):
            raise httpx.ConnectError('refused')
        return _ok_response()

    client = MagicMock()
    client.post = AsyncMock(side_effect=post)

    with patch.object(app_module, 'get_webhook_client', return_value=client):
        await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')

    assert client.post.await_count == 3  # dead: 2 dials, alive: 1
    app_module.record_app_webhook_success.assert_called_once()
    assert app_module.record_app_webhook_success.call_args.args[0] == 'app-alive-sibling'
    app_module.record_app_webhook_failure.assert_called_once()
    assert app_module.record_app_webhook_failure.call_args.args[0] == 'app-dead-sibling'
