"""A deterministically rejecting webhook endpoint must cool down, not re-dial.

Failure-Class: FC-deterministic-provider-rejection-burns-connect-retries —
sibling instance on the developer-webhook delivery path. The established class
condemns a provider whose rejection is deterministic for the whole credential
(an HTTP 402 on the STT WebSocket upgrade) yet keeps being re-dialed through a
per-connect retry schedule while its status was only visible to logging. The
developer-webhook sibling has the same shape with the polarity flipped: the
rejection status IS captured (a final 400/403 from the receiver), but the
admission control keyed to the destination treats it as outage evidence —
5 failures to open, a 30-second half-open probe — so a configuration error that
cannot heal by retrying was re-dialed about twice a minute forever, each probe
logging one `delivery failed status=4xx attempts=N` ERROR and writing one DLQ
entry (prod pusher 2026-10: x58/30m status=400 and x51/30m status=403 for one
dead developer endpoint, for hours).

Guards (rejection hold):
- a final deterministic 4xx that came from a real receiver dial arms the
  destination's rejection hold, so the next delivery for every subscribing
  kind is a counted, logged breaker skip (None), not another network loop;
- the hold is evidence-scoped, not outage-scoped: only the delivery layer's
  deterministic-response classification arms it (the SSRF invalid-target
  refusal self-heals when the stored URL resolves again and arms nothing;
  408/429 stay transient; 5xx keeps the outage path; a receiver 3xx redirect
  is deterministic like the 4xx members and arms the hold), and it clears on
  the first successful delivery;
- once expired, the breaker's own half-open gating admits exactly one real
  probe per recovery window — recovery stays observable;
- the per-uid disable ladder keeps converging under the hold: the arming
  delivery counts its real HTTP 4xx and every skip counts one probe failure,
  so the 100-consecutive-failure auto-disable still fires;
- the outage latch stays independent: a 5xx ramp still opens the breaker on
  its own evidence, and the hold never moves that latch by itself;
- the hold is keyed to the destination (query-stripped, like the breaker
  registry) and shared by every dev-webhook kind that delivers to it.

Guards (duplicate-ERROR fix):
- an exhausted transport-failed delivery logs its terminal ERROR exactly once
  (the delivery layer's `delivery failed error=<Type> attempts=N` line); the
  caller-side handler records the same outcome as an INFO with the webhook
  name and uid — never a second ERROR with less information (the prod
  `...error=ConnectError attempts=4` / `Error sending audio bytes...:
  ConnectError` couplet, x28 + x28 per 30 minutes);
- counted failures, breaker ticks and disable-ladder advances still happen on
  the caller side exactly as before (the helper is log-only).

The existing per-uid ladder and breaker-skip contract
(test_dev_webhook_disable_convergence.py) must stay green unchanged.
"""

import logging
import socket
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from utils import webhooks
from utils.http_client import (
    _WEBHOOK_DETERMINISTIC_REJECTION_COOLDOWN_SECONDS,
    WebhookCircuitBreaker,
    get_webhook_circuit_breaker,
)

PUBLIC_IP = '8.8.8.8'
URL = 'https://receiver.example/hook?token=secret-query'
URL_B = 'https://other-receiver.example/hook'


def _addresses(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


@pytest.fixture
def delivery_env(monkeypatch):
    dns = MagicMock(return_value=_addresses(PUBLIC_IP))
    monkeypatch.setattr(socket, 'getaddrinfo', dns)
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(200))
    monkeypatch.setattr(webhooks, 'get_pinned_delivery_client', lambda: client)
    monkeypatch.setattr(webhooks.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(webhooks, 'enqueue_dev_webhook_dlq', MagicMock())
    monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
    monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
    monkeypatch.setattr(webhooks, 'disable_user_webhook_db', MagicMock())
    monkeypatch.setattr(webhooks, 'send_notification', MagicMock())
    monkeypatch.setattr(webhooks, '_build_conversation_webhook_payload_sync', MagicMock(return_value={}))

    class _FakeHealth:
        """In-memory disable ladder: True exactly on the call that hits threshold."""

        def __init__(self, threshold=4):
            self.threshold = threshold
            self.calls = []

        def __call__(self, uid, wtype, status_code, error):
            count = 1 + sum(1 for existing in self.calls if existing[0] == uid)
            self.calls.append((uid, getattr(wtype, 'value', wtype), status_code, error))
            return count == self.threshold

    health = _FakeHealth(threshold=4)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', health)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())
    return SimpleNamespace(client=client, dns=dns, health=health)


def _real_breaker(monkeypatch, url=URL):
    """The real per-URL breaker registry entry for ``url``.

    Production code already resolves its breaker through
    ``get_webhook_circuit_breaker``, so no patching: this only fetches the
    live registry entry the delivery under test will use.
    """
    return get_webhook_circuit_breaker(url)


async def _dial_once_arming(client, breaker, name='test_webhook', url=URL, status=400):
    """One delivery that really dials and gets the deterministic answer."""
    client.post = AsyncMock(return_value=httpx.Response(status))
    response = await webhooks._post_dev_webhook(name, url, retry_delays=(), idempotency_key='arm', dlq_uid='uid')
    assert response is not None and response.status_code == status
    assert client.post.await_count == 1
    return response


class TestHoldArmsPerKind:
    """Each dev-webhook kind is wired separately, so each gets its own guard."""

    @pytest.mark.asyncio
    async def test_memory_created_400_arms_and_next_delivery_skips(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))
            delivery_env.client.post.assert_not_awaited()
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_day_summary_400_arms_and_next_delivery_skips(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.day_summary_webhook('uid', 'summary')
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.day_summary_webhook('uid', 'summary')
            delivery_env.client.post.assert_not_awaited()
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_realtime_transcript_400_arms_and_next_delivery_skips(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(403))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            delivery_env.client.post.assert_not_awaited()
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_audio_bytes_400_arms_and_next_delivery_skips(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
            delivery_env.client.post.assert_not_awaited()
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_button_event_400_arms_and_next_delivery_skips(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.button_event_webhook(
                'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-19T00:00:00Z'
            )
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.button_event_webhook(
                'uid', button_event='single', device_id='d', event_id='e2', timestamp='2026-10-19T00:00:01Z'
            )
            delivery_env.client.post.assert_not_awaited()
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_is_shared_across_kinds_on_one_destination(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.day_summary_webhook('uid', 'summary')
            delivery_env.client.post.assert_not_awaited()  # hold is destination-keyed, not kind-keyed
        finally:
            breaker.record_success()


class TestHoldSkipClassification:
    @pytest.mark.asyncio
    async def test_skip_is_typed_none_not_synthetic_status(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            skipped = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1,))
            assert skipped is None
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_skip_writes_no_dlq_and_runs_no_retry_sleep(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            webhooks.enqueue_dev_webhook_dlq.reset_mock()
            delivery_env.client.post.reset_mock()
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1, 0.2), dlq_uid='uid')
            delivery_env.client.post.assert_not_awaited()
            webhooks.asyncio.sleep.assert_not_awaited()
            webhooks.enqueue_dev_webhook_dlq.assert_not_called()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_skip_log_redacts_query_secrets(self, delivery_env, monkeypatch, caplog):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            with caplog.at_level(logging.INFO, logger=webhooks.__name__):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert 'circuit breaker open' in caplog.text
            assert 'receiver.example/hook' in caplog.text
            assert 'secret-query' not in caplog.text
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_realtime_transcript_skip_fails_journey_dependency_unavailable(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        journey = MagicMock()
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            with patch.object(webhooks, 'ClientJourneyAttempt', MagicMock(return_value=journey)):
                await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            journey.fail.assert_called_once_with('dependency_unavailable')
            journey.succeed.assert_not_called()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_skip_does_not_poison_the_breaker(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            snapshot = (breaker._failures, breaker._state, breaker._half_open_in_flight)
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert (breaker._failures, breaker._state, breaker._half_open_in_flight) == snapshot
        finally:
            breaker.record_success()


class TestLadderUnderHold:
    @pytest.mark.asyncio
    async def test_realtime_ladder_counts_arming_delivery_then_probes_to_disable(self, delivery_env, monkeypatch):
        from models.users import WebhookType

        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            for _ in range(3):
                await webhooks.realtime_transcript_webhook('uid', [{'text': 'muted'}])
            delivery_env.client.post.assert_not_awaited()

            assert [call[2] for call in delivery_env.health.calls] == [400, 0, 0, 0]
            assert [call[3] for call in delivery_env.health.calls] == [
                'HTTP 400',
                'CircuitBreakerOpen',
                'CircuitBreakerOpen',
                'CircuitBreakerOpen',
            ]
            webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.realtime_transcript)
            webhooks.send_notification.assert_called_once()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_audio_bytes_hold_skip_counts_once_across_chunks(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            # 20000 bytes at 8000 Hz spans several 1-second chunks if delivered.
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(20000))
            delivery_env.client.post.assert_not_awaited()
            assert [call[2] for call in delivery_env.health.calls] == [400, 0], 'one delivery trigger counts once'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_day_summary_ladder_converges_under_hold(self, delivery_env, monkeypatch):
        from models.users import WebhookType

        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.day_summary_webhook('uid', 'one')

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            for _ in range(3):
                await webhooks.day_summary_webhook('uid', 'more')
            delivery_env.client.post.assert_not_awaited()
            assert [call[2] for call in delivery_env.health.calls] == [400, 0, 0, 0]
            webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.day_summary)
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_button_event_ladder_converges_under_hold(self, delivery_env, monkeypatch):
        from models.users import WebhookType

        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.button_event_webhook(
                'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-19T00:00:00Z'
            )

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            for event_id in ('e2', 'e3', 'e4'):
                await webhooks.button_event_webhook(
                    'uid', button_event='single', device_id='d', event_id=event_id, timestamp='2026-10-19T00:00:01Z'
                )
            delivery_env.client.post.assert_not_awaited()
            assert [call[2] for call in delivery_env.health.calls] == [400, 0, 0, 0]
            webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.button_event)
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_memory_created_ladder_converges_under_hold(self, delivery_env, monkeypatch):
        from models.users import WebhookType

        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            for _ in range(3):
                await webhooks.conversation_created_webhook(
                    'uid', MagicMock(is_locked=False, client_platform='mobile_ios')
                )
            delivery_env.client.post.assert_not_awaited()
            assert [call[2] for call in delivery_env.health.calls] == [400, 0, 0, 0]
            webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.memory_created)
        finally:
            breaker.record_success()


class TestHoldScope:
    @pytest.mark.asyncio
    async def test_unsafe_target_refusal_does_not_arm_the_hold(self, delivery_env, monkeypatch):
        """The invalid-target refusal synthesizes a 400 without a real dial,
        and the delivery path re-validates the stored target every attempt:
        a fixed URL or recovered DNS self-heals on the next delivery, so the
        hold must stay response-sourced and arm nothing here."""
        breaker = _real_breaker(monkeypatch)
        try:
            from utils.http_client import UnsafeWebhookURLError

            with patch('utils.webhooks.safe_request_targets', MagicMock(side_effect=UnsafeWebhookURLError('no'))):
                refused = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert refused.status_code == 400
            assert breaker.allow_request() is True, 'no network answer, no rejection hold'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    @pytest.mark.parametrize('transient_status', [408, 429])
    async def test_transient_4xx_does_not_arm_the_hold(self, delivery_env, monkeypatch, transient_status):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(transient_status))
            response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert response.status_code == transient_status
            assert breaker.allow_request() is True, 'the transient 4xx members keep the retry schedule'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_server_5xx_does_not_arm_the_hold(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))
            response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert response.status_code == 503
            assert breaker.allow_request() is True, 'a 5xx outage must not arm the rejection hold'
            assert breaker._rejection_until == 0.0
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    @pytest.mark.parametrize('redirect_status', [301, 302, 307, 308])
    async def test_redirect_3xx_arms_the_hold(self, delivery_env, monkeypatch, redirect_status):
        """A redirect is a deterministic receiver answer: deliveries pin the
        destination and never follow redirects, so a stored redirect is a
        not-delivered answer no repeat post can change (the delivery layer
        classifies it with the deterministic 4xx members). It arms the hold,
        and the next delivery is a counted breaker skip."""
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(redirect_status))
            response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert response.status_code == redirect_status
            assert breaker.allow_request() is False
            skipped = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert skipped is None, 'the redirect hold makes the next delivery a counted skip'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_is_per_destination(self, delivery_env, monkeypatch):
        breaker_a = _real_breaker(monkeypatch)
        breaker_b = get_webhook_circuit_breaker(URL_B)
        try:
            await _dial_once_arming(delivery_env.client, breaker_a)
            assert breaker_a.allow_request() is False

            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200))
            delivered = await webhooks._post_dev_webhook('test_webhook', URL_B, retry_delays=())
            assert delivered.status_code == 200, 'a different destination is not held'
        finally:
            breaker_a.record_success()
            breaker_b.record_success()

    @pytest.mark.asyncio
    async def test_hold_covers_the_query_stripped_registry_key(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker, url=URL + '&extra=1')
            delivered = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert delivered is None, 'the hold uses the breaker registry key, which strips the query'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [400, 401, 403, 404, 410, 422])
    async def test_deterministic_statuses_arm_the_hold(self, delivery_env, monkeypatch, status):
        breaker = _real_breaker(monkeypatch, f'https://arm.example/hook-{status}')
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(status))
            await webhooks._post_dev_webhook('test_webhook', f'https://arm.example/hook-{status}', retry_delays=())
            assert breaker.allow_request() is False
        finally:
            breaker.record_success()


class TestHoldRecovery:
    @pytest.mark.asyncio
    async def test_probe_success_after_expiry_clears_hold_and_ladder_resets(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            assert breaker.allow_request() is False

            # Cooldown expired and the outage latch's half-open admits the
            # probe; the endpoint was fixed and answers 200.
            breaker._rejection_until = 0.0
            breaker._state = 'half_open'
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.day_summary_webhook('uid', 'fixed')
            assert delivery_env.client.post.await_count == 1
            webhooks.record_dev_webhook_success.assert_called_once()
            assert breaker.allow_request() is True
            assert breaker._rejection_until == 0.0
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_clears_only_on_success_not_on_skip(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert breaker.allow_request() is False, 'a skip is not recovery evidence'

            breaker.record_success()
            assert breaker.allow_request() is True
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_expired_hold_admits_normal_admission_on_quiet_breaker(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            assert breaker.allow_request() is False

            # Expiry with no outage evidence: the breaker is back to closed
            # semantics, so admission resumes until the next answer.
            breaker._rejection_until = 0.0
            assert breaker.allow_request() is True
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_dominates_the_open_outage_latch_until_expiry(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            await _dial_once_arming(delivery_env.client, breaker)
            for _ in range(5):
                breaker.record_failure()
            assert breaker.state == 'open'
            breaker._last_failure_time = time.monotonic() - 31
            assert breaker.state == 'half_open'
            assert breaker.allow_request() is False, 'the hold gates even the half-open probe'

            breaker._rejection_until = 0.0
            assert breaker.allow_request() is True, 'after expiry the latch takes over'
            assert breaker.allow_request() is False, 'and still admits exactly one probe per window'
        finally:
            breaker.record_success()

    def test_outage_latch_independent_of_hold(self):
        cb = WebhookCircuitBreaker('hold-independent.example/hook')
        cb.record_deterministic_rejection()
        assert cb.allow_request() is False
        # The hold alone never moves the outage latch: a fresh breaker reading
        # the same state must still report closed once the hold expires.
        cb._rejection_until = 0.0
        assert cb.state == 'closed'
        assert cb.allow_request() is True


class TestHoldUnit:
    def test_hold_blocks_admission_immediately(self):
        cb = WebhookCircuitBreaker('unit.example/hook')
        assert cb.allow_request() is True
        cb.record_deterministic_rejection()
        assert cb.allow_request() is False
        assert cb.state == 'closed', 'the hold is not outage evidence'

    def test_hold_blocks_while_the_latch_is_still_closed(self):
        cb = WebhookCircuitBreaker('unit-closed.example/hook')
        cb.record_failure()
        cb.record_deterministic_rejection()
        assert cb.state == 'closed'
        assert cb.allow_request() is False

    def test_unit_success_resets_the_hold(self):
        cb = WebhookCircuitBreaker('unit2.example/hook')
        cb.record_deterministic_rejection()
        cb.record_success()
        assert cb.allow_request() is True

    def test_record_rejection_uses_the_module_cooldown(self):
        cb = WebhookCircuitBreaker('unit3.example/hook')
        before = time.monotonic()
        cb.record_deterministic_rejection()
        assert cb._rejection_until == pytest.approx(before + _WEBHOOK_DETERMINISTIC_REJECTION_COOLDOWN_SECONDS, abs=0.5)

    def test_hold_does_not_suppress_failure_accounting(self):
        cb = WebhookCircuitBreaker('unit4.example/hook')
        cb.record_deterministic_rejection()
        for _ in range(5):
            cb.record_failure()
        assert cb.state == 'open'

    def test_held_breaker_still_refreshes_last_access_time(self):
        cb = WebhookCircuitBreaker('unit5.example/hook')
        cb.record_deterministic_rejection()
        seen = cb.last_access_time
        assert cb.allow_request() is False
        assert cb.last_access_time >= seen, 'a held but active breaker must stay eviction-safe'

    def test_fresh_breaker_starts_without_a_hold(self):
        cb = WebhookCircuitBreaker('unit6.example/hook')
        assert cb._rejection_until == 0.0
        assert cb.allow_request() is True


class TestSingleTerminalError:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'kind_call,webhook_name',
        [
            (lambda: webhooks.day_summary_webhook('uid', 'summary'), 'day_summary_webhook'),
            (
                lambda: webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}]),
                'realtime_transcript_webhook',
            ),
            (
                lambda: webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00')),
                'send_audio_bytes_developer_webhook',
            ),
            (
                lambda: webhooks.button_event_webhook(
                    'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-19T00:00:00Z'
                ),
                'button_event_webhook',
            ),
            (
                lambda: webhooks.conversation_created_webhook(
                    'uid', MagicMock(is_locked=False, client_platform='mobile_ios')
                ),
                'memory_created_webhook',
            ),
        ],
    )
    async def test_transport_exhaustion_logs_single_terminal_error(
        self, delivery_env, monkeypatch, caplog, kind_call, webhook_name
    ):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(side_effect=httpx.ConnectError('refused'))
            with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
                outcome = await kind_call()
                if isinstance(outcome, httpx.Response):
                    raise RuntimeError('exhausted transport delivery must not return a response')

            error_lines = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
            assert sum('delivery failed' in line for line in error_lines) == 1, 'exactly one terminal ERROR'
            assert not any('Error sending' in line for line in error_lines), 'the paired caller ERROR is gone'
            assert f'{webhook_name}: delivery failed error=ConnectError attempts=4' in caplog.text
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_deterministic_arming_delivery_reports_attempts_one(self, delivery_env, monkeypatch, caplog):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1, 0.2, 0.3), dlq_uid='uid')
            assert 'delivery failed status=400 attempts=1' in caplog.text
            assert 'retrying in' not in caplog.text
        finally:
            breaker.record_success()


class TestCallerOutcomeObservability:
    @pytest.mark.asyncio
    async def test_audio_bytes_exhaustion_info_names_sink_and_uid(self, delivery_env, monkeypatch, caplog):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(side_effect=httpx.ConnectError('refused'))
            with caplog.at_level(logging.INFO, logger=webhooks.__name__):
                await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))

            infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
            assert any(
                'dev webhook delivery exhausted' in line
                and 'send_audio_bytes_developer_webhook' in line
                and 'uid=uid' in line
                for line in infos
            ), 'the caller-side outcome stays observable at INFO with sink + uid'
            # Counted-failure path untouched: the ladder saw the ConnectError.
            assert delivery_env.health.calls == [('uid', 'audio_bytes', 0, 'ConnectError')]
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_memory_created_exhaustion_info_names_sink(self, delivery_env, monkeypatch, caplog):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(side_effect=httpx.ConnectError('refused'))
            with caplog.at_level(logging.INFO, logger=webhooks.__name__):
                await webhooks.conversation_created_webhook(
                    'uid', MagicMock(is_locked=False, client_platform='mobile_ios')
                )
            infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
            assert any('dev webhook delivery exhausted' in line and 'memory_created_webhook' in line for line in infos)
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_exhausted_info_appears_once_per_delivery(self, delivery_env, monkeypatch, caplog):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(side_effect=httpx.ConnectError('refused'))
            with caplog.at_level(logging.INFO, logger=webhooks.__name__):
                await webhooks.day_summary_webhook('uid', 'summary')
            exhausted = [r.getMessage() for r in caplog.records if 'dev webhook delivery exhausted' in r.getMessage()]
            assert len(exhausted) == 1
        finally:
            breaker.record_success()

    def test_helper_without_uid_logs_unknown(self, caplog):
        with caplog.at_level(logging.INFO, logger=webhooks.__name__):
            webhooks._log_dev_webhook_transport_failure('day_summary_webhook', httpx.ConnectError('refused'))
        assert any('uid=unknown' in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_arming_delivery_still_writes_dlq_with_response_status(self, delivery_env, monkeypatch):
        breaker = _real_breaker(monkeypatch)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(400))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), idempotency_key='e1', dlq_uid='uid')
            assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 400
            assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['idempotency_key'] == 'e1'
        finally:
            breaker.record_success()
