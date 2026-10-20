"""A transport-dead webhook endpoint must cool down, not re-walk its schedule.

Failure-Class: FC-deterministic-provider-rejection-burns-connect-retries —
transport-failure sibling on the developer-webhook delivery path. The
established class condemns a destination whose answer is deterministic for the
whole credential yet keeps being re-dialed through a per-connect retry
schedule. The 4xx/3xx sibling arms the deterministic rejection hold off the
receiver's own status; a transport-dead endpoint (connect timeout, connection
refused, DNS failure) has no status to classify, so nothing armed and every
delivery replayed the identical 4-attempt (1+5+30)s schedule: four real dials,
~44 seconds of webhook-semaphore occupancy, one
`delivery failed error=ConnectTimeout attempts=4` ERROR and one DLQ write per
delivery (prod pusher 2026-10: x30/30m ConnectTimeout plus x27/30m
ConnectError against one unreachable developer endpoint, x21/30m more on the
realtime-transcript sibling). The outage latch is the wrong shape for the same
reason it was wrong for 4xx: five deliveries to open, one 30-second half-open
probe, then the probe's own failure re-arms it — a dial-walk every ~30 seconds
forever, converging only through the 100-failure per-uid auto-disable.

The transport holddown is the rejection hold's short sibling: a delivery whose
whole schedule exhausted on transport failures arms a 120-second admission
block on the destination's breaker, so the next delivery is a counted, logged
breaker skip and at most one real schedule per holddown window runs — recovery
stays observable, and the per-uid disable ladder keeps converging through the
failures each blocked delivery records (its caller catch still counts status 0).

Guards (transport holddown):
- an exhausted transport delivery raises its exception exactly as before (the
  caller's counting path is untouched) but the destination's breaker now
  refuses admission for the holddown window;
- the blocked follow-up delivery is the standard breaker skip: no dial, the
  per-uid ladder sees one `CircuitBreakerOpen` probe failure, no DLQ write;
- one real schedule per window: after the hold expires the next delivery dials
  again — and, while the endpoint is still dead, re-arms the hold;
- any success clears the hold immediately (the endpoint healed);
- the hold never shortens the deterministic 15-minute rejection hold (max
  semantics), and arming twice does not extend past one window from the last
  arming delivery;
- a receiver answer (4xx/3xx/5xx) never arms the transport holddown — those
  have their own classification — and neither does the SSRF invalid-target
  refusal, which self-heals when the stored URL resolves again.
"""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from utils import webhooks
from utils.http_client import (
    _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS,
    get_webhook_circuit_breaker,
)

PUBLIC_IP = '8.8.8.8'
URL = 'https://receiver.example/hook'
TIMEOUT = httpx.ConnectTimeout('connection timed out')


def _addresses(*ips):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


@pytest.fixture
def delivery_env(monkeypatch):
    """Hermes-free delivery environment: pinned DNS, patched DLQ, no sleeps."""
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_: _addresses(PUBLIC_IP))
    monkeypatch.setattr(webhooks, 'safe_request_targets', lambda url: [(url, {'headers': {}, 'extensions': {}})])
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(200))
    monkeypatch.setattr(webhooks, 'get_pinned_delivery_client', lambda: client)
    monkeypatch.setattr(webhooks.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(webhooks, 'enqueue_dev_webhook_dlq', MagicMock())
    # Fresh breaker registry per test: the delivery layer keys state on the
    # shared per-URL registry, so tests must not leak holds into each other.
    from utils import http_client as http_client_module

    monkeypatch.setattr(http_client_module, '_webhook_circuit_breakers', {})
    return SimpleNamespace(client=client)


async def _deliver(name='test_webhook', url=URL):
    return await webhooks._post_dev_webhook(name, url, retry_delays=(0.1, 0.2, 0.3), dlq_uid='uid')


class TestTransportHolddownArms:
    @pytest.mark.asyncio
    async def test_exhausted_transport_delivery_arms_the_holddown(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker.allow_request() is False, 'the hold must block the next delivery'

    @pytest.mark.asyncio
    async def test_armed_delivery_walks_the_full_schedule_first(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        assert delivery_env.client.post.await_count == 4, 'the arming delivery keeps its full schedule'
        assert webhooks.enqueue_dev_webhook_dlq.call_count == 1, 'one DLQ write for the arming delivery'

    @pytest.mark.asyncio
    async def test_holddown_window_is_the_short_transport_one(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        import time as _time

        breaker.record_success()  # clear, then re-arm through the public seam to measure the window
        breaker.record_transport_holddown()
        remaining = breaker._rejection_until - _time.monotonic()
        assert (
            abs(remaining - _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS) <= 1.0
        ), 'the transport arm must use the short window, not the 15-minute deterministic one'
        assert remaining > _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS - 5.0

    @pytest.mark.asyncio
    async def test_connect_refused_and_dns_failure_arms_too(self, delivery_env):
        for exc in (httpx.ConnectError('refused'), httpx.ConnectTimeout('dns'), httpx.ReadTimeout('idle')):
            from utils import http_client as http_client_module

            http_client_module._webhook_circuit_breakers.clear()
            delivery_env.client.post = AsyncMock(side_effect=exc)
            with pytest.raises(type(exc)):
                await _deliver()
            assert get_webhook_circuit_breaker(URL).allow_request() is False, f'{type(exc).__name__} must arm the hold'


class TestBlockedFollowUpDelivery:
    @pytest.mark.asyncio
    async def test_next_delivery_is_a_counted_breaker_skip(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(200))
        skipped = await _deliver()
        assert skipped is None, 'the blocked delivery is the standard breaker skip'
        delivery_env.client.post.assert_not_awaited()
        assert webhooks.enqueue_dev_webhook_dlq.call_count == 1, 'a skip writes no DLQ entry'

    @pytest.mark.asyncio
    async def test_skip_log_names_the_breaker_not_the_transport(self, delivery_env, caplog):
        import logging

        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        with caplog.at_level(logging.INFO, logger=webhooks.__name__):
            await _deliver()
        assert any('circuit breaker open' in r.getMessage() for r in caplog.records)


class TestRecoveryStaysObservable:
    @pytest.mark.asyncio
    async def test_expired_hold_dials_again_and_re_arms_while_still_dead(self, delivery_env, monkeypatch):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        breaker._rejection_until = 0.0  # window expired
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        assert delivery_env.client.post.await_count == 8, 'one real schedule per window'
        assert breaker.allow_request() is False, 'a still-dead endpoint re-arms the hold'

    @pytest.mark.asyncio
    async def test_success_after_expiry_clears_the_hold(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        breaker._rejection_until = 0.0
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(200))
        response = await _deliver()
        assert response.status_code == 200
        assert breaker.allow_request() is True, 'success proves the endpoint healed'


class TestHoldInteractionContract:
    @pytest.mark.asyncio
    async def test_transport_arm_never_shortens_the_deterministic_hold(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        breaker.record_deterministic_rejection()
        long_until = breaker._rejection_until
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        breaker._rejection_until = long_until
        with pytest.raises(httpx.ConnectTimeout):
            # admit manually: the deterministic hold is still active, so open the gate
            breaker._rejection_until = 0.0
            await _deliver()
        # the delivery re-armed with the max semantics — never BELOW the deterministic window's value
        breaker.record_deterministic_rejection()
        long_until = breaker._rejection_until
        breaker.record_transport_holddown()
        assert breaker._rejection_until >= long_until, 'a transport arm must not cut the 15-minute hold'

    @pytest.mark.asyncio
    async def test_receiver_answer_arms_only_its_own_classification(self, delivery_env):
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))
        response = await _deliver()
        assert response.status_code == 503
        # 5xx is outage evidence: it must not arm the transport holddown.
        # The breaker opens via the outage latch path in the full stack; here
        # the delivery itself must not have written the short-window latch.
        breaker = get_webhook_circuit_breaker(URL)
        breaker._failures = 0
        breaker._state = 'closed'
        assert breaker.allow_request() is True, 'a receiver answer never arms the transport holddown'

    @pytest.mark.asyncio
    async def test_ssrf_refusal_does_not_arm_the_holddown(self, delivery_env, monkeypatch):
        from utils.http_client import UnsafeWebhookURLError

        def refuse(_url):
            raise UnsafeWebhookURLError('private address')

        monkeypatch.setattr(webhooks, 'safe_request_targets', refuse)
        response = await _deliver()
        assert response.status_code == 400, 'invalid stored target keeps its synthetic-400 contract'
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker._rejection_until == 0.0, 'the self-healing SSRF refusal arms nothing'


class TestCallerLadderStillConverges:
    @pytest.mark.asyncio
    async def test_audio_bytes_caller_counts_blocked_deliveries(self, delivery_env, monkeypatch):
        probe_calls = []
        counted = []

        async def fake_probe_failure(uid, wtype):
            probe_calls.append((uid, getattr(wtype, 'value', wtype)))
            return False

        def fake_counted(uid, wtype, status_code, error):
            counted.append((uid, getattr(wtype, 'value', wtype), status_code, error))
            return False

        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', fake_probe_failure)
        monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', fake_counted)
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        # The arming delivery raises inside the delivery layer; the caller catch
        # absorbs it and records the counted failure; the caller never re-raises.
        await webhooks.send_audio_bytes_developer_webhook('uid-1', 8000, bytearray(b'\x00\x00'))
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('blocked delivery must not dial'))
        await webhooks.send_audio_bytes_developer_webhook('uid-1', 8000, bytearray(b'\x00\x00'))
        assert counted == [
            ('uid-1', 'audio_bytes', 0, 'ConnectTimeout')
        ], 'the arming delivery counts its transport failure on the ladder'
        assert probe_calls == [('uid-1', 'audio_bytes')], 'the blocked delivery counts one probe failure on the ladder'

    @pytest.mark.asyncio
    async def test_realtime_transcript_caller_counts_blocked_deliveries(self, delivery_env, monkeypatch):
        probe_calls = []
        counted = []

        async def fake_probe_failure(uid, wtype):
            probe_calls.append((uid, getattr(wtype, 'value', wtype)))
            return False

        def fake_counted(uid, wtype, status_code, error):
            counted.append((uid, getattr(wtype, 'value', wtype), status_code, error))
            return False

        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', fake_probe_failure)
        monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', fake_counted)
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        journeys = []

        def journey_factory(_name, _kind):
            journeys.append(MagicMock())
            return journeys[-1]

        monkeypatch.setattr(webhooks, 'ClientJourneyAttempt', journey_factory)
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.realtime_transcript_webhook('uid-1', [{'text': 'hello'}])
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('blocked delivery must not dial'))
        await webhooks.realtime_transcript_webhook('uid-2', [{'text': 'hello'}])
        assert probe_calls == [('uid-2', 'realtime_transcript')], 'each blocked uid counts its own probe failure'
        # Two deliveries, two journey attempts; the blocked (second) one failed
        # as dependency_unavailable — a gate answer, not an upstream rejection.
        assert len(journeys) == 2
        assert journeys[1].fail.call_args.args == ('dependency_unavailable',)

    @pytest.mark.asyncio
    async def test_memory_created_caller_counts_blocked_deliveries(self, delivery_env, monkeypatch):
        probe_calls = []

        async def fake_probe_failure(uid, wtype):
            probe_calls.append((uid, getattr(wtype, 'value', wtype)))
            return False

        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', fake_probe_failure)
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        monkeypatch.setattr(webhooks, '_build_conversation_webhook_payload_sync', MagicMock(return_value={}))
        journey = MagicMock()
        monkeypatch.setattr(webhooks, 'ClientJourneyAttempt', MagicMock(return_value=journey))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.conversation_created_webhook('uid-1', MagicMock(is_locked=False, client_platform='mobile_ios'))
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('blocked delivery must not dial'))
        await webhooks.conversation_created_webhook('uid-2', MagicMock(is_locked=False, client_platform='mobile_ios'))
        assert probe_calls == [('uid-2', 'memory_created')], 'the blocked memory-created delivery counts too'


class TestDestinationSharing:
    @pytest.mark.asyncio
    async def test_hold_is_shared_by_every_kind_on_one_destination(self, delivery_env, monkeypatch):
        """The breaker (and so the hold) is keyed to the URL: one dead endpoint
        blocks every subscribing kind, and one healed endpoint unblocks them all."""
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.realtime_transcript_webhook('uid-1', [{'text': 'hello'}])
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker.allow_request() is False, 'the realtime arm blocks the shared destination'
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('shared hold must block every kind'))
        skipped = await webhooks.day_summary_webhook('uid-1', 'summary')
        assert skipped is None, 'the day-summary delivery rides the same hold'
        skipped = await webhooks.button_event_webhook(
            'uid-1', button_event='single', device_id='d', event_id='e', timestamp='2026-10-20T00:00:00Z'
        )
        assert skipped is None, 'the button-event delivery rides the same hold'

    @pytest.mark.asyncio
    async def test_success_from_any_kind_clears_the_hold_for_all(self, delivery_env, monkeypatch):
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.realtime_transcript_webhook('uid-1', [{'text': 'hello'}])
        breaker = get_webhook_circuit_breaker(URL)
        breaker._rejection_until = 0.0  # window elapsed
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(200))
        await webhooks.day_summary_webhook('uid-1', 'summary')
        assert breaker.allow_request() is True, 'any kind success proves the destination healed'


class TestSkipLogHygiene:
    @pytest.mark.asyncio
    async def test_skip_log_keeps_query_secrets_out(self, delivery_env, caplog):
        import logging

        url_with_secret = URL + '?token=super-secret-query'
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook('test_webhook', url_with_secret, retry_delays=(0.1,), dlq_uid='uid')
        with caplog.at_level(logging.INFO, logger=webhooks.__name__):
            await webhooks._post_dev_webhook('test_webhook', url_with_secret, retry_delays=(0.1,), dlq_uid='uid')
        assert any('circuit breaker open' in r.getMessage() for r in caplog.records)
        assert all(
            'super-secret-query' not in r.getMessage() for r in caplog.records
        ), 'the skip line must keep the redaction contract'

    @pytest.mark.asyncio
    async def test_arming_delivery_keeps_the_single_terminal_error(self, delivery_env, caplog):
        """The hold must not add logging: the arming delivery's evidence stays
        exactly one terminal ERROR, as the duplicate-ERROR fix requires."""
        import logging

        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
            with pytest.raises(httpx.ConnectTimeout):
                await _deliver()
        errors = [r.getMessage() for r in caplog.records]
        assert sum('delivery failed' in line for line in errors) == 1, 'exactly one terminal ERROR'
        assert 'delivery failed error=ConnectTimeout attempts=4' in errors[0]


class TestScheduleSemanticsUnchanged:
    @pytest.mark.asyncio
    async def test_mid_schedule_recovery_never_arms(self, delivery_env):
        """If any attempt of the schedule reaches HTTP and succeeds, the
        delivery succeeds and arms nothing — a flapping endpoint that answers
        on retry keeps today's behavior."""
        responses = [TIMEOUT, httpx.Response(200)]
        delivery_env.client.post = AsyncMock(
            side_effect=lambda *a, **k: responses.pop(0) if responses else httpx.Response(200)
        )
        response = await _deliver()
        assert response.status_code == 200
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker.allow_request() is True, 'a converged delivery arms nothing'

    @pytest.mark.asyncio
    async def test_transient_4xx_receiver_answers_walk_retries_and_arm_nothing(self, delivery_env):
        """408/429 stay transient at the same boundary the deterministic hold
        excludes them; the transport holddown must not swallow them either."""
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(429))
        response = await _deliver()
        assert response.status_code == 429
        assert delivery_env.client.post.await_count == 4, 'the full schedule still walked for a transient 4xx'
        breaker = get_webhook_circuit_breaker(URL)
        breaker._failures = 0
        breaker._state = 'closed'
        assert breaker.allow_request() is True, 'a transient receiver answer arms no transport hold'


class TestAudioBytesChunkLoop:
    @pytest.mark.asyncio
    async def test_multi_chunk_payload_aborts_on_the_arming_raise(self, delivery_env, monkeypatch):
        """A transport exception out of chunk 1 aborts the whole multi-chunk
        delivery (the caller's catch returns, it does not continue): a dead
        endpoint costs ONE schedule per delivery, not one per chunk, and the
        counted failure lands exactly once."""
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        counted = []

        def fake_counted(uid, wtype, status_code, error):
            counted.append((uid, getattr(wtype, 'value', wtype), status_code, error))
            return False

        monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', fake_counted)
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        sample_rate = 8000
        payload = bytearray(b'\x00' * (sample_rate * 2 * 2))  # two 1-second chunks
        await webhooks.send_audio_bytes_developer_webhook('uid-1', sample_rate, payload)
        assert delivery_env.client.post.await_count == 4, 'only the first chunk walks a full schedule'
        assert counted == [
            ('uid-1', 'audio_bytes', 0, 'ConnectTimeout')
        ], 'the delivery counts its transport failure exactly once'
        assert (
            get_webhook_circuit_breaker(URL).allow_request() is False
        ), 'the armed hold waits for the NEXT delivery, not the next chunk'


class TestConcurrentDeliveries:
    @pytest.mark.asyncio
    async def test_simultaneous_deliveries_to_a_dead_endpoint_each_raise_once(self, delivery_env):
        """Two in-flight deliveries for the same dead destination both keep
        their own terminal evidence; the hold arms once (idempotent latch)."""
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        outcomes = await asyncio.gather(_deliver(), _deliver(), return_exceptions=True)
        assert all(
            isinstance(o, httpx.ConnectTimeout) for o in outcomes
        ), 'every in-flight delivery raises its own fault'
        assert delivery_env.client.post.await_count == 8, 'both schedules really walked'
        assert webhooks.enqueue_dev_webhook_dlq.call_count == 2, 'each exhausted delivery writes its own DLQ entry'
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker.allow_request() is False, 'the latch holds after concurrent arming'


class TestBreakerUnitContract:
    """Unit-level pins on the new breaker seam, mirroring the rejection-hold
    suite's breaker pins so the two holds stay behaviorally aligned."""

    def test_fresh_breaker_starts_without_a_transport_hold(self):
        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        assert breaker.allow_request() is True
        assert breaker._rejection_until == 0.0

    def test_transport_hold_blocks_admission_immediately(self):
        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_transport_holddown()
        assert breaker.allow_request() is False

    def test_transport_hold_blocks_even_while_the_outage_latch_is_closed(self):
        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_transport_holddown()
        assert breaker._state == 'closed', 'the hold is evidence-specific, not outage-scoped'
        assert breaker.allow_request() is False

    def test_unit_success_resets_the_transport_hold(self):
        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_transport_holddown()
        breaker.record_success()
        assert breaker.allow_request() is True
        assert breaker._rejection_until == 0.0

    def test_transport_arm_does_not_suppress_failure_accounting(self):
        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        failures_before = breaker._failures
        breaker.record_transport_holddown()
        breaker.record_failure()
        assert breaker._failures == failures_before + 1, 'the outage latch keeps counting through the hold'

    def test_held_breaker_still_refreshes_last_access_time(self):
        import time as _time

        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_transport_holddown()
        before = breaker._last_access_time
        _time.sleep(0.001)
        assert breaker.allow_request() is False
        assert breaker._last_access_time > before, 'idle-eviction must not reap a held destination as unused'

    def test_repeated_arming_extends_the_window_from_the_latest_delivery(self):
        import time as _time

        from utils.http_client import WebhookCircuitBreaker

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_transport_holddown()
        first = breaker._rejection_until
        _time.sleep(0.001)
        breaker.record_transport_holddown()
        assert breaker._rejection_until > first, 'a second dead window re-arms from its own delivery'

    def test_transport_arm_cannot_shorten_a_taller_latch(self):
        import time as _time

        from utils.http_client import (
            _WEBHOOK_DETERMINISTIC_REJECTION_COOLDOWN_SECONDS,
            WebhookCircuitBreaker,
        )

        breaker = WebhookCircuitBreaker(URL)
        breaker.record_deterministic_rejection()
        long_until = breaker._rejection_until
        _time.sleep(0.001)
        breaker.record_transport_holddown()
        assert breaker._rejection_until == long_until, 'the short arm must leave the 15-minute latch untouched'

    def test_transport_uses_its_own_module_cooldown(self):
        from utils.http_client import (
            _WEBHOOK_DETERMINISTIC_REJECTION_COOLDOWN_SECONDS,
            _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS,
        )

        assert (
            _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS < _WEBHOOK_DETERMINISTIC_REJECTION_COOLDOWN_SECONDS
        ), 'transport deadness heals; a configuration error does not — the windows must differ'


class TestDaySummaryKindWiring:
    @pytest.mark.asyncio
    async def test_day_summary_caller_counts_blocked_deliveries(self, delivery_env, monkeypatch):
        probe_calls = []

        async def fake_probe_failure(uid, wtype):
            probe_calls.append((uid, getattr(wtype, 'value', wtype)))
            return False

        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', fake_probe_failure)
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.day_summary_webhook('uid-1', 'summary')
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('blocked delivery must not dial'))
        await webhooks.day_summary_webhook('uid-2', 'summary')
        assert probe_calls == [('uid-2', 'day_summary')], 'the blocked day-summary delivery counts its probe failure'

    @pytest.mark.asyncio
    async def test_button_event_caller_counts_blocked_deliveries(self, delivery_env, monkeypatch):
        probe_calls = []

        async def fake_probe_failure(uid, wtype):
            probe_calls.append((uid, getattr(wtype, 'value', wtype)))
            return False

        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', fake_probe_failure)
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.button_event_webhook(
            'uid-1', button_event='double', device_id='d', event_id='e1', timestamp='2026-10-20T00:00:00Z'
        )
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('blocked delivery must not dial'))
        await webhooks.button_event_webhook(
            'uid-2', button_event='double', device_id='d', event_id='e2', timestamp='2026-10-20T00:00:01Z'
        )
        assert probe_calls == [('uid-2', 'button_event')], 'the blocked button-event delivery counts its probe failure'

    @pytest.mark.asyncio
    async def test_blocked_button_event_keeps_its_idempotency_key_for_retry(self, delivery_env, monkeypatch):
        """The skip is not a delivery: the event's idempotency key was never
        consumed by a receiver, so the replayed event carries the same key."""
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        deliveries = iter([TIMEOUT, TIMEOUT, httpx.Response(200), httpx.Response(200)])

        async def first_dead_then_healthy(_url, **_kwargs):
            outcome = next(deliveries)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        delivery_env.client.post = AsyncMock(side_effect=first_dead_then_healthy)
        await webhooks.button_event_webhook(
            'uid-1', button_event='single', device_id='d', event_id='evt-9', timestamp='2026-10-20T00:00:00Z'
        )
        await webhooks.button_event_webhook(
            'uid-1', button_event='single', device_id='d', event_id='evt-9', timestamp='2026-10-20T00:00:00Z'
        )
        keys = [
            call.kwargs['headers'].get('Idempotency-Key')
            for call in delivery_env.client.post.await_args_list
            if isinstance(call.kwargs.get('headers'), dict)
        ]
        assert 'evt-9' in keys, 'the retry after the hold dials with the event id as the idempotency key'


class TestEnvDrivenSchedule:
    @pytest.mark.asyncio
    async def test_env_retry_schedule_changes_walk_length_not_the_arm(self, delivery_env, monkeypatch):
        """The arming decision is schedule-length independent: a 1-attempt
        env schedule arms the same hold the default 4-attempt one does."""
        monkeypatch.setenv('DEV_WEBHOOK_RETRY_DELAYS', '0.5')
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook('test_webhook', URL, dlq_uid='uid')
        assert delivery_env.client.post.await_count == 2, 'the env schedule really drove the walk'
        assert get_webhook_circuit_breaker(URL).allow_request() is False

    @pytest.mark.asyncio
    async def test_invalid_env_schedule_falls_back_and_still_arms(self, delivery_env, monkeypatch):
        monkeypatch.setenv('DEV_WEBHOOK_RETRY_DELAYS', 'not-a-number')
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook('test_webhook', URL, dlq_uid='uid')
        assert delivery_env.client.post.await_count == 4, 'the default schedule drove the walk'
        assert get_webhook_circuit_breaker(URL).allow_request() is False


class TestPinnedTargetWalk:
    @pytest.mark.asyncio
    async def test_multi_address_endpoint_walks_addresses_within_one_attempt(self, delivery_env, monkeypatch):
        """Every safe resolved address gets one dial per attempt before the
        attempt counts as transport-dead; the hold arms on the exhausted walk."""
        import socket as _socket

        monkeypatch.setattr(
            webhooks,
            'safe_request_targets',
            lambda url: [
                (url, {'headers': {}, 'extensions': {}}),
                (url, {'headers': {}, 'extensions': {}}),
            ],
        )
        monkeypatch.setattr(
            socket,
            'getaddrinfo',
            lambda *_: [
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, '', (PUBLIC_IP, 0)),
                (_socket.AF_INET, _socket.SOCK_STREAM, 6, '', ('8.8.4.4', 0)),
            ],
        )
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        # 4 attempts x 2 addresses = 8 dials for a dual-stack dead endpoint.
        assert delivery_env.client.post.await_count == 8, 'each attempt tried every safe address'
        assert get_webhook_circuit_breaker(URL).allow_request() is False

    @pytest.mark.asyncio
    async def test_second_address_success_on_the_first_attempt_never_arms(self, delivery_env, monkeypatch):
        """The address walk exists so one dead answer does not kill delivery;
        a walk that converges on a later address succeeds and arms nothing."""
        monkeypatch.setattr(
            webhooks,
            'safe_request_targets',
            lambda url: [
                (url, {'headers': {}, 'extensions': {}}),
                (url, {'headers': {}, 'extensions': {}}),
            ],
        )

        async def post(_url, **_kwargs):
            if delivery_env.client.post.await_count == 1:
                raise TIMEOUT
            return httpx.Response(200)

        delivery_env.client.post = AsyncMock(side_effect=post)
        response = await _deliver()
        assert response.status_code == 200
        assert get_webhook_circuit_breaker(URL).allow_request() is True


class TestHoldAndOutageLatchIndependence:
    @pytest.mark.asyncio
    async def test_transport_hold_does_not_stop_the_outage_latch_from_opening(self, delivery_env):
        """The arm writes no breaker failure: a destination that is ALSO failing
        through counted receiver paths must still open the outage latch on its
        own evidence, exactly like the deterministic hold's contract."""
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker._state == 'closed', 'arming the hold does not touch the outage latch'
        for _ in range(5):
            breaker.record_failure()
        assert breaker._state == 'open', 'the outage latch opens on its own counted evidence'

    @pytest.mark.asyncio
    async def test_expired_hold_admits_a_real_schedule_not_just_a_probe(self, delivery_env):
        """Unlike the outage latch's single half-open probe, an expired
        transport hold admits a full delivery schedule — recovery needs one
        real walk, and success or re-arming both stay observable."""
        walks = iter(
            [TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT]
            + [httpx.Response(500), httpx.Response(500), httpx.Response(500), httpx.Response(500)]
        )

        async def first_dead_then_500(_url, **_kwargs):
            outcome = next(walks)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        delivery_env.client.post = AsyncMock(side_effect=first_dead_then_500)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        breaker._rejection_until = 0.0
        response = await _deliver()
        assert response.status_code == 500, 'the post-expiry delivery dialled all attempts'
        assert delivery_env.client.post.await_count == 8


class TestArmingEvidenceContract:
    @pytest.mark.asyncio
    async def test_arming_dlq_carries_the_transport_convention(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
        assert kwargs['status_code'] == 0, 'a transport failure has no HTTP status'
        assert kwargs['error'] == 'ConnectTimeout', 'the DLQ names the fault class'

    @pytest.mark.asyncio
    async def test_arming_dlq_carries_idempotency_key_and_payload(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook(
                'test_webhook', URL, retry_delays=(0.1,), json={'k': 'v'}, idempotency_key='idem-1', dlq_uid='uid'
            )
        kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
        assert kwargs['idempotency_key'] == 'idem-1'
        assert kwargs['payload'] == {'k': 'v'}

    @pytest.mark.asyncio
    async def test_empty_retry_delays_single_attempt_still_arms(self, delivery_env):
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
        assert delivery_env.client.post.await_count == 1
        assert get_webhook_circuit_breaker(URL).allow_request() is False

    @pytest.mark.asyncio
    async def test_valueerror_from_target_resolution_arms_nothing(self, delivery_env, monkeypatch):
        def explode(_url):
            raise ValueError('bad url shape')

        monkeypatch.setattr(webhooks, 'safe_request_targets', explode)
        response = await _deliver()
        assert response.status_code == 400, 'invalid target keeps the synthetic-400 contract'
        assert get_webhook_circuit_breaker(URL)._rejection_until == 0.0, 'a config-shaped refusal arms nothing'

    @pytest.mark.asyncio
    async def test_arm_while_breaker_already_open_keeps_open_state(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        for _ in range(5):
            breaker.record_failure()
        assert breaker._state == 'open'
        delivery_env.client.post = AsyncMock(side_effect=AssertionError('open breaker means no dial'))
        skipped = await _deliver()
        assert skipped is None, 'the open breaker still dominates admission'
        assert breaker._state == 'open', 'a blocked delivery cannot arm or mutate the latch'


class TestBlockedDeliveryHealthNeutrality:
    @pytest.mark.asyncio
    async def test_blocked_audio_bytes_delivery_records_no_false_success(self, delivery_env, monkeypatch):
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', MagicMock(return_value=False))
        success = MagicMock()
        monkeypatch.setattr(webhooks, 'record_dev_webhook_success', success)
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.send_audio_bytes_developer_webhook('uid-1', 8000, bytearray(b'\x00\x00'))
        success.assert_not_called(), 'a dead delivery must not reset the webhook-health row'

    @pytest.mark.asyncio
    async def test_blocked_realtime_journey_names_the_app_delivery_lane(self, delivery_env, monkeypatch):
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        factory = MagicMock()
        monkeypatch.setattr(webhooks, 'ClientJourneyAttempt', factory)
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        await webhooks.realtime_transcript_webhook('uid-1', [{'text': 'hello'}])
        assert factory.call_args.args[0] == 'app_webhook_delivery'

    @pytest.mark.asyncio
    async def test_hold_needs_no_sleeps_to_arm(self, delivery_env, monkeypatch):
        """The arming is decided by the raised fault, not by clock elapse;
        the suite's zero-sleep runs prove no real-time dependency."""
        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with pytest.raises(httpx.ConnectTimeout):
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.01, 0.01, 0.01), dlq_uid='uid')
        assert get_webhook_circuit_breaker(URL).allow_request() is False


class TestHoldClassificationBoundaries:
    @pytest.mark.asyncio
    async def test_timeouts_then_deterministic_answer_takes_the_deterministic_path(self, delivery_env):
        """A walk that eventually reaches HTTP and gets a deterministic 4xx
        ends in the 4xx machinery (unretryable answer, one dial-equivalent
        ERROR with the real status), never the transport arm."""
        outcomes = iter([TIMEOUT, TIMEOUT, TIMEOUT, httpx.Response(402)])

        async def walk(_url, **_kwargs):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        delivery_env.client.post = AsyncMock(side_effect=walk)
        response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1, 0.2, 0.3), dlq_uid='uid')
        assert response.status_code == 402
        kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
        assert kwargs['status_code'] == 402, 'the receiver answer feeds the DLQ'
        breaker = get_webhook_circuit_breaker(URL)
        assert breaker._rejection_until > 0, 'the deterministic arm fired'
        assert (
            breaker._rejection_until - breaker.last_access_time > _WEBHOOK_TRANSPORT_HOLDDOWN_SECONDS
        ), 'the DETERMINISTIC window is active, not the short transport one'

    @pytest.mark.asyncio
    async def test_arming_error_reports_real_dials_not_schedule_slots(self, delivery_env, caplog):
        import logging

        delivery_env.client.post = AsyncMock(side_effect=TIMEOUT)
        with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
            with pytest.raises(httpx.ConnectTimeout):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
        line = next(r.getMessage() for r in caplog.records if 'delivery failed' in r.getMessage())
        assert 'attempts=1' in line, 'a single-attempt schedule claims its one real dial'

    @pytest.mark.asyncio
    async def test_healthy_receiver_after_expiry_writes_no_dlq(self, delivery_env):
        walks = iter([TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT] + [httpx.Response(200)] * 4)

        async def dead_then_healthy(_url, **_kwargs):
            outcome = next(walks)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        delivery_env.client.post = AsyncMock(side_effect=dead_then_healthy)
        with pytest.raises(httpx.ConnectTimeout):
            await _deliver()
        breaker = get_webhook_circuit_breaker(URL)
        breaker._rejection_until = 0.0
        response = await _deliver()
        assert response.status_code == 200
        assert webhooks.enqueue_dev_webhook_dlq.call_count == 1, 'recovery writes no new DLQ entry'
