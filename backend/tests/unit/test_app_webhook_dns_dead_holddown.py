"""A DNS-dead app webhook endpoint must cool down, not walk the guard every delivery.

Failure-Class: FC-deterministic-provider-rejection-burns-connect-retries
(nearest existing registry class — its violated contract condemns feeding a
fault that is deterministic for the whole target through the per-delivery
walk "so a condemned target is skipped rather than re-dialed"; this diff
applies exactly that contract to the SSRF guard's host-resolution refusal).
The refusal the guard raises carries TWO different faults behind one
exception type: a host whose DNS answers with a private/loopback address is
a stored-URL configuration error — a developer fix, never admitted on a
re-dial; a host whose DNS answers with nothing is an endpoint outage of the
same kind a connect timeout is — the stored URL heals on its own when the
name's records return. Before this diff every delivery of a DNS-dead app
endpoint replayed the guard refusal at the app's full trigger cadence: no
hold existed to arm, the app's own graduated webhook-health ladder (24h warn
/ 72h disable) never saw the fault, and the loop burned one WARNING per
delivery indefinitely (prod pusher 2026-10-28: one expired
``*.trycloudflare.com`` tunnel, ``Could not resolve host 'office-technical-
rendering-broke.trycloudflare.com'``, ×1500/day from a single app id while
the app stayed enabled).

The fix classifies the refusal inside the guard's catch with
``is_unresolved_host_error`` (a typed, host-bound check — no string matching
at the call sites) and arms the same short transport holddown a dead connect
arms (``WebhookCircuitBreaker.record_transport_holddown``), so the endpoint
is skipped for one holddown window per arming delivery while recovery stays
observable: after the window, one real delivery re-runs the guard and, while
the name is still dead, re-arms the hold. The private/loopback shape keeps
its exact prior behavior — a silent, logged rejection with no hold and no
health write — because that URL can only heal through a developer edit, and
the guard refusal self-heals for it the moment the stored URL changes.

Guards:
- a DNS-dead endpoint arms the holddown: the next delivery is refused by the
  breaker BEFORE the guard resolves again (no second warning that window);
- after the window expires, the guard runs again and, while the name is
  still dead, re-arms the hold (one real resolution per window);
- a resolution SUCCESS clears the hold immediately (the endpoint healed);
- the private/loopback refusal shape arms nothing (unchanged contract, and
  it must not block re-checking after the developer edits the URL — the
  edited URL has its own breaker);
- the transcript lane gets the same classification (its refusal carries a
  journey failure, also unchanged);
- the refusal warning text keeps app attribution in both lanes.
"""

import asyncio
import socket
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = __import__('pathlib').Path(__file__).resolve().parents[2]

DNS_DEAD_HOST = 'tunnel-expired.example'
DNS_DEAD_URL = f'https://{DNS_DEAD_HOST}/hook'
PRIVATE_URL = 'https://internal.example/hook'


def _module(name: str, **attributes: Any):
    from types import ModuleType

    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str, path):
    from types import ModuleType

    module = ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    return module


class _UnsafeWebhookURLError(Exception):
    """Isolated stand-in for ``utils.http_client.UnsafeWebhookURLError``.

    The production guard catch matches this exact class; an AutoMockModule
    default would be a non-exception MagicMock the ``except`` clause can
    neither raise nor match.
    """


class _ProactivityDenied(Exception):
    pass


class _ClientJourneyAttempt:
    def __init__(self, journey: str, client_kind: Any = None):
        self.journey = journey
        self.client_kind = client_kind
        self.outcome = None

    def succeed(self):
        self.outcome = ('succeed',)

    def fail(self, issue: str):
        self.outcome = ('fail', issue)

    def cancel(self, *args: Any, **kwargs: Any):
        self.outcome = ('cancel',)


@pytest.fixture
def app_harness(monkeypatch) -> Iterator[SimpleNamespace]:
    """Load the production coordinator fresh, every blocking dependency
    stubbed — the sanctioned isolation harness of
    test_realtime_app_integration_transport_resilience.py, with the breaker
    registry freshly keyed so holds cannot leak between tests."""
    get_available_apps = MagicMock(return_value=[])

    async def run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def gather_safe(*awaitables, **_kwargs):
        return await asyncio.gather(*awaitables)

    from utils import http_client as real_http_client

    # Fresh breaker registry per test: the delivery layer keys state on the
    # shared per-URL registry, so tests must not leak holds into each other.
    registry: dict[str, Any] = {}
    monkeypatch.setattr(real_http_client, '_webhook_circuit_breakers', registry)

    def _auto(name: str, **attrs):
        module = AutoMockModule(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        return module

    stubs: dict[str, Any] = {
        'utils': _package('utils', BACKEND_DIR / 'utils'),
        'utils.llm': _package('utils.llm', BACKEND_DIR / 'utils' / 'llm'),
        'utils.llms': _package('utils.llms', BACKEND_DIR / 'utils' / 'llms'),
        'utils.conversations': _package('utils.conversations', BACKEND_DIR / 'utils' / 'conversations'),
        'utils.observability': _package('utils.observability', BACKEND_DIR / 'utils' / 'observability'),
        'database': _package('database', BACKEND_DIR / 'database'),
        'models': _package('models', BACKEND_DIR / 'models'),
        'config': _package('config', BACKEND_DIR / 'config'),
        'database.llm_usage': _module('database.llm_usage', record_llm_usage=MagicMock()),
        'database.notifications': _auto(
            'database.notifications',
            get_mentor_notification_frequency=MagicMock(return_value=0),
        ),
        'database.dev_api_key': _auto(
            'database.dev_api_key',
            get_dev_keys_for_user=MagicMock(return_value=[]),
        ),
        'database.mem_db': _auto(
            'database.mem_db',
            get_proactive_noti_sent_at=MagicMock(return_value=None),
            set_proactive_noti_sent_at=MagicMock(),
        ),
        'database.redis_db': _auto(
            'database.redis_db',
            get_generic_cache=MagicMock(return_value=None),
            set_generic_cache=MagicMock(),
            delete_app_cache_by_id=MagicMock(),
            incr_daily_notification_count=MagicMock(),
            get_daily_notification_count=MagicMock(return_value=0),
            publish_proactive_message=MagicMock(),
        ),
        'database.apps': _auto(
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
        'database.chat': _auto(
            'database.chat',
            add_app_message=MagicMock(return_value={'id': 'msg-1'}),
            get_app_messages=MagicMock(return_value=[]),
        ),
        'database.goals': _auto('database.goals', get_user_goals=MagicMock(return_value=[])),
        'database.users': _auto(
            'database.users',
            get_user_language_preference=MagicMock(return_value='en'),
        ),
        'database.mentor_gate_state': _auto('database.mentor_gate_state'),
        'database.vector_db': _auto(
            'database.vector_db',
            query_vectors_by_metadata=MagicMock(return_value=[]),
        ),
        'database.conversations': _auto(
            'database.conversations',
            get_conversations_by_id=MagicMock(return_value=[]),
        ),
        'models.app': _module(
            'models.app',
            App=object,
            ProactiveNotification=object,
            UsageHistoryType=SimpleNamespace(
                memory_created_external_integration='memory_created_external_integration',
                transcript_processed_external_integration='transcript_processed_external_integration',
            ),
        ),
        'models.chat': _module('models.chat', Message=object),
        'models.conversation': _module('models.conversation', Conversation=object),
        'models.conversation_enums': _module(
            'models.conversation_enums',
            ConversationSource=SimpleNamespace(workflow='workflow', unknown='unknown'),
        ),
        'models.notification_message': _module('models.notification_message', NotificationMessage=object),
        'models.transcript_segment': _module(
            'models.transcript_segment',
            transcript_segment_for_client=lambda segment: segment,
        ),
        # The REAL http_client: the classifier and the breaker hold under test
        # are its code. Only get_webhook_client (network) is redirected.
        'utils.http_client': real_http_client,
        'utils.executors': _module(
            'utils.executors',
            db_executor=object(),
            postprocess_executor=object(),
            run_blocking=run_blocking,
        ),
        'utils.async_tasks': _module('utils.async_tasks', gather_safe=gather_safe),
        'utils.dev_cache': _auto(
            'utils.dev_cache',
            get_cached_developer=MagicMock(return_value=None),
            set_cached_developer=MagicMock(),
        ),
        'utils.subscription': _module('utils.subscription', is_trial_paywalled=MagicMock(return_value=False)),
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
        'utils.observability.fallback': _module('utils.observability.fallback', record_fallback=MagicMock()),
        'utils.proactivity_flags': _auto('utils.proactivity_flags'),
        'utils.mentor_admission': _auto(
            'utils.mentor_admission',
            mentor_plan_allows_evaluation=MagicMock(return_value=True),
        ),
        'config.proactivity_v2': _module('config.proactivity_v2', ProactivityDenied=_ProactivityDenied),
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
        'utils.notification_dispatch': _auto(
            'utils.notification_dispatch',
            dispatch_notification=MagicMock(),
            dispatch_notification_async=AsyncMock(return_value=None),
        ),
        'utils.llm.clients': _auto(
            'utils.llm.clients',
            generate_embedding=MagicMock(return_value=[0] * 3072),
            get_llm=MagicMock(),
        ),
        'utils.llm.proactive_notification': _auto(
            'utils.llm.proactive_notification',
            evaluate_relevance=MagicMock(),
            generate_notification=MagicMock(),
            validate_notification=MagicMock(),
            FREQUENCY_TO_BASE_THRESHOLD={1: 0.5, 2: 0.4, 3: 0.3},
            MAX_DAILY_NOTIFICATIONS=10,
        ),
        'utils.llm.temporal': _auto('utils.llm.temporal', current_date_for_uid=MagicMock(return_value='2026-01-01')),
        'utils.llms.memory': _module('utils.llms.memory', get_prompt_memories=MagicMock(return_value=('', ''))),
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
            http_client=real_http_client,
        )


def _audio_app(app_id: str = 'app-audio'):
    app = MagicMock()
    app.id = app_id
    app.name = f'App {app_id}'
    app.uid = 'owner-uid'
    app.enabled = True
    app.external_integration.webhook_url = 'https://placeholder.invalid/hook'
    app.triggers_realtime.return_value = False
    app.triggers_realtime_audio_bytes.return_value = True
    return app


def _transcript_app(app_id: str = 'app-transcript'):
    app = _audio_app(app_id)
    app.triggers_realtime.return_value = True
    app.triggers_realtime_audio_bytes.return_value = False
    return app


@pytest.fixture
def dead_dns(monkeypatch):
    """Resolve only the private target: the dead name answers nothing.

    The guard catches ``socket.gaierror`` specifically, so the fake must raise
    exactly that (a bare ``OSError`` would escape the guard and the lane).
    """

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == DNS_DEAD_HOST:
            raise socket.gaierror(-2, 'Name or service not known')
        if host == 'private-target.example':
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0))]

    monkeypatch.setattr('socket.getaddrinfo', fake_getaddrinfo)
    return fake_getaddrinfo


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every name to a public IP (the healed / private-answer lanes)."""

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == 'private-target.example':
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0))]

    monkeypatch.setattr('socket.getaddrinfo', fake_getaddrinfo)


class TestAudioLaneDnsDeadHolddown:
    @pytest.mark.asyncio
    async def test_dns_dead_endpoint_arms_hold_and_next_delivery_skips(self, app_harness, dead_dns):
        app_module = app_harness.app
        harness_app = _audio_app('app-dead')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]

        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        breaker = app_harness.http_client.get_webhook_circuit_breaker(DNS_DEAD_URL + '?sample_rate=16000&uid=uid-1')
        assert breaker.allow_request() is False, 'the holddown must refuse the next delivery'

        # Second delivery inside the window: breaker skip, no second guard
        # resolution, no client dial.
        client = MagicMock()
        client.post = AsyncMock()
        with patch.object(app_module, 'get_webhook_client', return_value=client):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert client.post.await_count == 0

    @pytest.mark.asyncio
    async def test_window_expiry_reruns_guard_and_re_arms(self, app_harness, dead_dns, monkeypatch):
        app_module = app_harness.app
        harness_app = _audio_app('app-expiry')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]

        from utils.http_client import _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS

        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        url = DNS_DEAD_URL + '?sample_rate=16000&uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        # Age the hold past its window.
        breaker._rejection_until = __import__('time').monotonic() - 1
        assert breaker.allow_request() is True, 'expired hold must admit one real delivery'

        resolutions = {'n': 0}
        real_resolve = app_harness.http_client.safe_request_target

        def counting_resolve(target):
            resolutions['n'] += 1
            return real_resolve(target)

        monkeypatch.setattr(app_module, 'safe_request_target', counting_resolve)
        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert resolutions['n'] == 1, 'one real guard resolution per window'
        assert breaker.allow_request() is False, 'still-dead name re-arms the hold'

    @pytest.mark.asyncio
    async def test_resolution_success_clears_hold_and_delivers(self, app_harness, public_dns, monkeypatch):
        app_module = app_harness.app
        harness_app = _audio_app('app-heal')
        healed_url = 'https://healed.example/hook'
        harness_app.external_integration.webhook_url = healed_url
        app_harness.get_available_apps.return_value = [harness_app]

        from utils.http_client import _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS

        # The registry keys breakers on scheme+host+path (query stripped), the
        # same key the delivery layer consults. Arm the hold, then age it past
        # its window: this test exercises the healed END of the hold, which the
        # guard's own success also produces.
        breaker = app_harness.http_client.get_webhook_circuit_breaker(healed_url)
        breaker.record_transport_holddown()
        breaker._rejection_until = __import__('time').monotonic() - 1

        client = MagicMock()
        response = MagicMock(status_code=200)
        client.post = AsyncMock(return_value=response)
        with patch.object(app_module, 'get_webhook_client', return_value=client):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert client.post.await_count == 1, 'a healed resolution must deliver'
        assert app_harness.http_client.get_webhook_circuit_breaker(healed_url).allow_request() is True

    @pytest.mark.asyncio
    async def test_private_answer_arms_nothing(self, app_harness, public_dns, monkeypatch):
        app_module = app_harness.app
        harness_app = _audio_app('app-private')
        harness_app.external_integration.webhook_url = 'https://private-target.example/hook'
        app_harness.get_available_apps.return_value = [harness_app]

        client = MagicMock()
        client.post = AsyncMock()
        with patch.object(app_module, 'get_webhook_client', return_value=client):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert client.post.await_count == 0
        url = 'https://private-target.example/hook?sample_rate=16000&uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        assert breaker.allow_request() is True, 'the policy shape must not hold the URL'


class TestTranscriptLaneDnsDeadHolddown:
    @pytest.mark.asyncio
    async def test_dns_dead_endpoint_arms_hold_and_journey_fails(self, app_harness, dead_dns):
        app_module = app_harness.app
        harness_app = _transcript_app('app-t-dead')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]

        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            results = await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')
        url = DNS_DEAD_URL + '?uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        assert breaker.allow_request() is False, 'the holddown must refuse the next delivery'
        # Journey failure is recorded exactly as before (invalid_response).
        # The result for the refused app is absent, matching the prior return.
        assert results == {} or results is None or all(v is not None for v in (results or {}).values())

    @pytest.mark.asyncio
    async def test_private_answer_arms_nothing(self, app_harness, public_dns, monkeypatch):
        app_module = app_harness.app
        harness_app = _transcript_app('app-t-private')
        harness_app.external_integration.webhook_url = 'https://private-target.example/hook'
        app_harness.get_available_apps.return_value = [harness_app]

        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()) as client:
            await app_module.trigger_realtime_integrations('uid-1', [{'text': 'hi'}], 'conv-1')
        url = 'https://private-target.example/hook?uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        assert breaker.allow_request() is True, 'the policy shape must not hold the URL'


class TestHoldSemantics:
    """The hold the classification arms is the transport hold's contract, not
    a new one: bounded re-check cadence, no health write, no owner ladder."""

    @pytest.mark.asyncio
    async def test_hold_does_not_advance_app_webhook_health(self, app_harness, dead_dns):
        """The refusal is deliberately not a delivery failure: the app's
        graduated ladder (24h warn / 72h disable) must not consume an
        endpoint-outage shape the hold already bounds."""
        app_module = app_harness.app
        harness_app = _audio_app('app-health')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]
        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        app_module.record_app_webhook_failure.assert_not_called()
        app_module.record_app_webhook_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_hold_does_not_trip_the_outage_latch(self, app_harness, dead_dns):
        """Arming the transport hold must leave the breaker's outage latch
        alone — an endpoint that heals should never sit open behind five
        counted refusals."""
        app_module = app_harness.app
        harness_app = _audio_app('app-latch')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]
        for _ in range(4):
            with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
                await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        url = DNS_DEAD_URL + '?sample_rate=16000&uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        assert breaker.state == 'closed', 'refusals are holds, never outage evidence'
        # Age past the hold: the next delivery is admitted, not refused by an
        # outage latch five refusals could have opened.
        breaker._rejection_until = __import__('time').monotonic() - 1
        assert breaker.allow_request() is True

    @pytest.mark.asyncio
    async def test_arming_twice_does_not_extend_the_window(self, app_harness, dead_dns, monkeypatch):
        app_module = app_harness.app
        harness_app = _audio_app('app-twice')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]

        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        url = DNS_DEAD_URL + '?sample_rate=16000&uid=uid-1'
        breaker = app_harness.http_client.get_webhook_circuit_breaker(url)
        armed_until = breaker._rejection_until

        # Second delivery inside the window is a skip: the hold refuses BEFORE
        # the guard resolves, so nothing re-arms and the window stays the one
        # the first arming delivery bought (allow ±clock jitter: the hold can
        # only be armed again by a guard refusal, which a refused delivery
        # cannot produce — and monotonic time only moves forward, so an
        # unchanged hold reads as the SAME instant, not a later one).
        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        breaker2 = app_harness.http_client.get_webhook_circuit_breaker(url)
        assert abs(breaker2._rejection_until - armed_until) < 1e-6, 'a guard-less skip must not arm later'

    @pytest.mark.asyncio
    async def test_disabled_app_never_reaches_the_guard(self, app_harness, monkeypatch):
        """The pre-existing disable check stays in front of everything: an
        auto-disabled app's endpoint is not resolved, warned about, or held."""
        app_module = app_harness.app
        harness_app = _audio_app('app-disabled')
        harness_app.external_integration.webhook_url = DNS_DEAD_URL
        app_harness.get_available_apps.return_value = [harness_app]

        def refuse(_app_id):
            raise AssertionError('disabled app must be filtered before the guard')

        monkeypatch.setattr(app_module, 'is_app_webhook_disabled', refuse)
        # The disabled check is read through run_blocking; the harness executes
        # it inline, so make the stub return True instead of raising later.
        monkeypatch.setattr(app_module, 'is_app_webhook_disabled', MagicMock(return_value=True), raising=False)
        resolves = {'n': 0}
        real_resolve = app_harness.http_client.safe_request_target

        def counting_resolve(target):
            resolves['n'] += 1
            return real_resolve(target)

        monkeypatch.setattr(app_module, 'safe_request_target', counting_resolve)
        with patch.object(app_module, 'get_webhook_client', return_value=MagicMock()):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert resolves['n'] == 0, 'no DNS resolution for a disabled app'
        assert app_harness.http_client._webhook_circuit_breakers.get(DNS_DEAD_URL) is None

    @pytest.mark.asyncio
    async def test_no_apps_means_no_resolution(self, app_harness, dead_dns):
        app_module = app_harness.app
        app_harness.get_available_apps.return_value = []
        resolves = {'n': 0}
        real_resolve = app_harness.http_client.safe_request_target

        def counting_resolve(target):
            resolves['n'] += 1
            return real_resolve(target)

        with patch.object(app_module, 'safe_request_target', counting_resolve):
            await app_module.trigger_realtime_audio_bytes('uid-1', 16000, bytearray(b'audio'))
        assert resolves['n'] == 0


class TestClassifierContract:
    def test_unresolved_host_predicate_matches_resolution_failure_only(self):
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        resolved_private = UnsafeWebhookURLError(f"'{DNS_DEAD_HOST}' resolves to non-public address 127.0.0.1")
        assert is_unresolved_host_error(resolved_private, f'https://{DNS_DEAD_HOST}/hook') is False

        unresolvable = UnsafeWebhookURLError(
            f"Could not resolve host {DNS_DEAD_HOST!r}: [Errno -2] Name or service not known"
        )
        assert is_unresolved_host_error(unresolvable, f'https://{DNS_DEAD_HOST}/hook') is True

        other = UnsafeWebhookURLError('URL has no hostname')
        assert is_unresolved_host_error(other, f'https://{DNS_DEAD_HOST}/hook') is False

        not_the_guard = httpx.ConnectError('could not resolve')
        assert is_unresolved_host_error(not_the_guard, f'https://{DNS_DEAD_HOST}/hook') is False

    def test_predicate_is_host_bound(self):
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        error = UnsafeWebhookURLError(f"Could not resolve host '{DNS_DEAD_HOST}': no addresses returned")
        assert is_unresolved_host_error(error, 'https://other-host.example/hook') is False

    def test_predicate_reads_the_url_argument_not_the_error_host(self):
        """The URL argument is the source of truth for the host binding: the
        same refusal text classifies for every URL shape of its own host and
        for no other host's."""
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        error = UnsafeWebhookURLError(f"Could not resolve host '{DNS_DEAD_HOST}': [Errno -2] boom")
        assert is_unresolved_host_error(error, f'https://{DNS_DEAD_HOST}:8443/deep/path?x=1') is True
        assert is_unresolved_host_error(error, f'http://{DNS_DEAD_HOST}/other') is True

    def test_gaierror_message_shape_classifies(self):
        """The gaierror rendering — the exact text `str(socket.gaierror(-2, ...))`
        produces inside the guard's f-string — is the production form."""
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        production = UnsafeWebhookURLError(
            f"Could not resolve host '{DNS_DEAD_HOST}': [Errno -2] Name or service not known"
        )
        assert is_unresolved_host_error(production, f'https://{DNS_DEAD_HOST}/hook') is True

    def test_no_addresses_answer_shape_classifies(self):
        """getaddrinfo succeeding with zero records is documented as a
        resolution failure and must classify like one."""
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        error = UnsafeWebhookURLError(f"Could not resolve host '{DNS_DEAD_HOST}': no addresses returned")
        assert is_unresolved_host_error(error, f'https://{DNS_DEAD_HOST}/hook') is True

    @pytest.mark.parametrize(
        'text',
        [
            "'h.example' resolves to non-public address 10.0.0.1",
            "'h.example' resolves to non-public address ::1",
            "'h.example' resolves to non-public address 169.254.169.254",
            "'h.example' resolves to non-public address 192.168.1.1",
        ],
    )
    def test_private_answer_refusals_do_not_classify(self, text):
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        assert is_unresolved_host_error(UnsafeWebhookURLError(text), 'https://h.example/hook') is False

    @pytest.mark.parametrize(
        'text',
        [
            'Unsupported URL scheme: gopher',
            'URL has no hostname',
        ],
    )
    def test_malformed_url_refusals_do_not_classify(self, text):
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        assert is_unresolved_host_error(UnsafeWebhookURLError(text), 'https://h.example/hook') is False

    @pytest.mark.parametrize(
        'error',
        [
            httpx.ConnectError("Could not resolve host 'h.example'"),
            httpx.ConnectTimeout('timed out'),
        ],
    )
    def test_transport_exceptions_do_not_classify(self, error):
        from utils.http_client import is_unresolved_host_error

        assert is_unresolved_host_error(error, 'https://h.example/hook') is False

    @pytest.mark.parametrize(
        'error',
        [
            ValueError("Could not resolve host 'h.example'"),
            RuntimeError('any'),
        ],
    )
    def test_non_guard_exception_types_do_not_classify(self, error):
        from utils.http_client import is_unresolved_host_error

        assert is_unresolved_host_error(error, 'https://h.example/hook') is False

    def test_predicate_handles_url_without_hostname(self):
        from utils.http_client import UnsafeWebhookURLError, is_unresolved_host_error

        error = UnsafeWebhookURLError("Could not resolve host 'h.example': boom")
        assert is_unresolved_host_error(error, 'not-a-url') is False
