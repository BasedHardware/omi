"""A redirecting developer-webhook endpoint must cool down, not re-dial.

Failure-Class: FC-deterministic-provider-rejection-burns-connect-retries —
sibling instance on the developer-webhook delivery path. The established class
condemns re-dialing an endpoint whose answer cannot change on a repeat post
(the STT 402 upgrade refusal; the developer-webhook 400/403 rejection hold).
The un-latched sibling lives one status class lower: a receiver that answers
the POST with a redirect (301/302/307/308). Deliveries pin the destination IP
and set ``follow_redirects=False`` by design, so a redirect is a terminal
not-delivered answer from a host that IS up — the stored URL points somewhere
else, and repeating the same POST reproduces the same redirect forever. The
retry classifier only recognized deterministic 4xx, so every delivery to a
redirecting URL walked the full 4-attempt schedule (4 dials plus the 1s/5s/30s
sleeps — ~40 s of semaphore, per-uid lock and queue time) and landed one
terminal ERROR plus one DLQ write per delivery; the audio-bytes webhook fires
every few seconds per active user, so one misconfigured URL produced a
continuous dial-and-ERROR loop. The app-webhook health path already learned
this lesson: ``record_app_webhook_failure`` special-cases 3xx as
redirect-not-followed instead of counting outage evidence.

Guards (redirect determinism in the delivery layer):
- a 3xx answer from a real receiver dial ends the delivery after exactly one
  dial — no retry walk, because a stored redirect cannot change on a repeat;
- the destination's rejection hold arms off that answer, so the next delivery
  for every subscribing kind is a counted, logged breaker skip (None) and the
  endpoint cools down for the deterministic-rejection cooldown with one real
  recovery probe per window;
- the terminal evidence is unchanged: one ERROR with the redirect status and
  one DLQ entry carrying that status;
- the per-uid disable ladder keeps counting the real 3xx exactly as before —
  this change alters dial behavior only, not the auto-disable policy;
- 408/429 stay transient and walk the retry schedule; deterministic 4xx keep
  their existing single-dial + hold behavior; a success still clears the hold,
  so fixing the stored URL recovers on the next delivery.
"""

import asyncio
import logging
import socket
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from utils import webhooks
from utils.http_client import get_webhook_circuit_breaker

PUBLIC_IP = '8.8.8.8'
PUBLIC_IP_B = '8.8.4.4'
URL = 'https://receiver.example/hook?token=secret-query'
URL_B = 'https://other-receiver.example/hook'


def _addresses(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


class _FakeHealth:
    """In-memory disable ladder: True exactly on the call that hits threshold."""

    def __init__(self, threshold=4):
        self.threshold = threshold
        self.calls = []

    def __call__(self, uid, wtype, status_code, error):
        count = 1 + sum(1 for existing in self.calls if existing[0] == uid)
        self.calls.append((uid, getattr(wtype, 'value', wtype), status_code, error))
        return count == self.threshold


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

    health = _FakeHealth(threshold=4)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', health)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())
    return SimpleNamespace(client=client, dns=dns, health=health)


async def _dial(name='test_webhook', url=URL, status=307, retry_delays=(1.0, 5.0, 30.0), client=None):
    if client is not None:
        client.post = AsyncMock(return_value=httpx.Response(status))
    return await webhooks._post_dev_webhook(name, url, retry_delays=retry_delays, idempotency_key='k', dlq_uid='uid')


class TestRedirectSingleDial:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [301, 302, 307, 308])
    async def test_redirect_answer_dials_once_no_retry_walk(self, delivery_env, status):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            response = await _dial(status=status, client=delivery_env.client)
            assert response is not None and response.status_code == status
            assert delivery_env.client.post.await_count == 1, 'a stored redirect cannot change on a retry'
            assert not webhooks.asyncio.sleep.await_count, 'no retry sleeps for a deterministic answer'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_redirect_writes_one_dlq_entry_with_the_redirect_status(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            response = await _dial(status=307, client=delivery_env.client)
            assert response is not None and response.status_code == 307
            webhooks.enqueue_dev_webhook_dlq.assert_called_once()
            kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
            assert kwargs['status_code'] == 307
            assert kwargs['webhook_name'] == 'test_webhook'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_redirect_terminal_error_logged_once(self, delivery_env, caplog):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
                response = await _dial(status=301, client=delivery_env.client)
            assert response is not None and response.status_code == 301
            errors = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert len(errors) == 1, 'one terminal ERROR per delivery, unchanged from the 4xx latch'
            assert 'status=301' in errors[0].getMessage()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_transient_408_still_walks_full_schedule(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            response = await _dial(status=408, client=delivery_env.client)
            assert response is not None and response.status_code == 408
            assert delivery_env.client.post.await_count == 4, '408 keeps the retry schedule'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_server_503_still_walks_full_schedule(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            response = await _dial(status=503, client=delivery_env.client)
            assert response is not None and response.status_code == 503
            assert delivery_env.client.post.await_count == 4, '5xx keeps the retry schedule'
        finally:
            breaker.record_success()


class TestRedirectArmsTheHold:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [301, 302, 307, 308])
    async def test_hold_blocks_the_next_delivery_as_a_counted_skip(self, delivery_env, status):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            await _dial(status=status, client=delivery_env.client)
            assert breaker.allow_request() is False, 'the redirect arms the destination rejection hold'

            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            skipped = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1,))
            assert skipped is None, 'the held delivery is a typed skip, not a synthetic status'
            delivery_env.client.post.assert_not_awaited()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_does_not_poison_the_breaker(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            await _dial(status=307, client=delivery_env.client)
            snapshot = (breaker._failures, breaker._state, breaker._half_open_in_flight)
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert (
                breaker._failures,
                breaker._state,
                breaker._half_open_in_flight,
            ) == snapshot, 'the skip must not move the outage latch'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_is_per_destination(self, delivery_env):
        breaker_a = get_webhook_circuit_breaker(URL)
        breaker_b = get_webhook_circuit_breaker(URL_B)
        try:
            await _dial(status=307, client=delivery_env.client)
            assert breaker_a.allow_request() is False

            delivered = await _dial(url=URL_B, status=200, retry_delays=(), client=delivery_env.client)
            assert delivered.status_code == 200, 'a different destination is not held'
        finally:
            breaker_a.record_success()
            breaker_b.record_success()

    @pytest.mark.asyncio
    async def test_success_after_expired_hold_recovers(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            await _dial(status=307, client=delivery_env.client)
            assert breaker.allow_request() is False

            # Cooldown expired, the outage latch's half-open admits the probe,
            # and the developer fixed the stored URL: the endpoint answers 200.
            # The caller drives the success path, so dial through one kind.
            breaker._rejection_until = 0.0
            breaker._state = 'half_open'
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.day_summary_webhook('uid', 'fixed')
            assert delivery_env.client.post.await_count == 1
            assert breaker.allow_request() is True
            assert breaker._rejection_until == 0.0, 'success clears the hold'
        finally:
            breaker.record_success()


class TestLadderPolicyUnchanged:
    @pytest.mark.asyncio
    async def test_audio_bytes_redirect_counts_the_real_status_on_the_ladder(self, delivery_env):
        from models.users import WebhookType

        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00' * 100))
            assert delivery_env.client.post.await_count == 1
            assert delivery_env.health.calls == [
                ('uid', WebhookType.audio_bytes.value, 307, 'HTTP 307')
            ], 'the ladder counts the real redirect status — no auto-disable policy change'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_realtime_transcript_redirect_counts_the_real_status_on_the_ladder(self, delivery_env):
        from models.users import WebhookType

        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(301))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            assert delivery_env.client.post.await_count == 1
            assert delivery_env.health.calls == [('uid', WebhookType.realtime_transcript.value, 301, 'HTTP 301')]
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_audio_bytes_ladder_converges_to_disable_under_redirect_hold(self, delivery_env):
        from models.users import WebhookType

        breaker = get_webhook_circuit_breaker(URL)
        try:
            # Arming delivery counts the real 307; the hold then turns every
            # further trigger into one counted skip, so the 100-failure
            # ladder still converges (threshold faked at 4 here).
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            for _ in range(3):
                await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(20000))
            delivery_env.client.post.assert_not_awaited()
            assert [call[2] for call in delivery_env.health.calls] == [307, 0, 0, 0]
            webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.audio_bytes)
            webhooks.send_notification.assert_called_once()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_redirect_is_still_never_followed(self, delivery_env):
        """Pinning contract unchanged (test_webhook_delivery_pinning pins the
        same property): the redirect answer comes from the pinned destination
        and the delivery never dials the Location target."""
        seen = []

        def handle(request):
            seen.append(request)
            return httpx.Response(307, headers={'Location': 'http://127.0.0.1/private'})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
            breaker = get_webhook_circuit_breaker(URL)
            try:
                import utils.webhooks as wh

                original = wh.get_pinned_delivery_client
                wh.get_pinned_delivery_client = lambda: client
                try:
                    response = await webhooks._post_dev_webhook('test', URL, retry_delays=(), follow_redirects=True)
                finally:
                    wh.get_pinned_delivery_client = original
                assert response.status_code == 307
                assert len(seen) == 1
                assert seen[0].url.host == PUBLIC_IP, 'the dial went to the pinned IP, never the Location target'
            finally:
                breaker.record_success()


class TestClassificationHelpers:
    def test_deterministic_4xx_members(self):
        assert webhooks._is_deterministic_rejection(400)
        assert webhooks._is_deterministic_rejection(415)
        assert not webhooks._is_deterministic_rejection(408)
        assert not webhooks._is_deterministic_rejection(429)
        assert not webhooks._is_deterministic_rejection(500)

    def test_redirect_members(self):
        for status in (300, 301, 302, 303, 307, 308, 399):
            assert webhooks._is_redirect_answer(status)
        assert not webhooks._is_redirect_answer(200)
        assert not webhooks._is_redirect_answer(400)

    def test_unretryable_union(self):
        assert webhooks._is_unretryable_receiver_answer(302)
        assert webhooks._is_unretryable_receiver_answer(415)
        assert not webhooks._is_unretryable_receiver_answer(408)
        assert not webhooks._is_unretryable_receiver_answer(503)


class TestStatusRetryMatrix:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'status,expected_dials',
        [
            (200, 1),
            (201, 1),
            (204, 1),
            (301, 1),
            (302, 1),
            (304, 1),
            (307, 1),
            (308, 1),
            (399, 1),
            (400, 1),
            (401, 1),
            (403, 1),
            (404, 1),
            (410, 1),
            (415, 1),
            (422, 1),
            (408, 4),
            (429, 4),
            (500, 4),
            (502, 4),
            (503, 4),
        ],
    )
    async def test_dial_count_by_status_class(self, delivery_env, status, expected_dials):
        """The whole classification in one table: 2xx delivered, 3xx redirect
        and deterministic 4xx are one-dial answers (a repeat post cannot
        change them), 408/429 and 5xx keep the full retry schedule."""
        breaker = get_webhook_circuit_breaker(f'https://matrix.example/hook-{status}')
        url = f'https://matrix.example/hook-{status}'
        try:
            delivery_env.dns.return_value = _addresses(f'8.8.{status % 256}.{(status // 256) % 256}')
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(status))
            response = await webhooks._post_dev_webhook(
                'test_webhook', url, retry_delays=(1.0, 5.0, 30.0), idempotency_key='k', dlq_uid='uid'
            )
            assert response is not None and response.status_code == status
            assert delivery_env.client.post.await_count == expected_dials
        finally:
            breaker.record_success()


class TestRedirectHoldPerKind:
    """Every dev-webhook kind arms the destination hold off a redirect and its
    next trigger is a counted skip — the same per-kind wiring the 4xx hold
    tests pin, because the kinds are wired separately."""

    @staticmethod
    async def _call_kind(kind, status_mock):
        if kind == 'memory':
            await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))
        elif kind == 'day':
            await webhooks.day_summary_webhook('uid', 'summary')
        elif kind == 'realtime':
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
        elif kind == 'audio':
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
        else:
            await webhooks.button_event_webhook(
                'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-20T00:00:00Z'
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize('kind', ['memory', 'day', 'realtime', 'audio', 'button'])
    async def test_redirect_arms_hold_and_next_trigger_skips(self, delivery_env, kind):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await self._call_kind(kind, None)
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await self._call_kind(kind, None)
            delivery_env.client.post.assert_not_awaited()  # the next delivery is a hold skip
            assert delivery_env.health.calls[-1][2:] == (0, 'CircuitBreakerOpen')
        finally:
            breaker.record_success()


class TestRedirectLadderPerKind:
    """The redirect counts the real 3xx status on each kind's ladder — dial
    behavior changed, auto-disable policy did not."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'kind,wtype_value,status',
        [
            ('memory', 'memory_created', 301),
            ('day', 'day_summary', 302),
            ('realtime', 'realtime_transcript', 307),
            ('audio', 'audio_bytes', 308),
            ('button', 'button_event', 304),
        ],
    )
    async def test_ladder_counts_real_redirect_status(self, delivery_env, kind, wtype_value, status):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(status))
            await TestRedirectHoldPerKind._call_kind(kind, None)
            assert delivery_env.client.post.await_count == 1
            assert delivery_env.health.calls == [('uid', wtype_value, status, f'HTTP {status}')]
        finally:
            breaker.record_success()


class TestRedirectEvidenceContracts:
    @pytest.mark.asyncio
    async def test_dlq_payload_names_sink_status_uid_and_keeps_idempotency_key(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook(
                'realtime_transcript_webhook',
                URL,
                json={'segments': []},
                retry_delays=(1.0,),
                idempotency_key='ik-1',
                dlq_uid='uid',
            )
            kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
            assert kwargs['status_code'] == 307
            assert kwargs['webhook_name'] == 'realtime_transcript_webhook'
            assert kwargs['idempotency_key'] == 'ik-1'
            assert kwargs['uid'] == 'uid'
            assert kwargs['error'] == 'HTTP 307'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_terminal_log_reports_attempts_one_and_redacts_query(self, delivery_env, caplog):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(1.0, 5.0, 30.0), dlq_uid='uid')
            assert 'delivery failed status=307 attempts=1' in caplog.text
            assert 'url=https://receiver.example/hook' in caplog.text
            assert 'secret-query' not in caplog.text
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_no_retry_warning_lines_for_a_redirect(self, delivery_env, caplog):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            with caplog.at_level(logging.WARNING, logger=webhooks.__name__):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(1.0, 5.0, 30.0), dlq_uid='uid')
            assert not any(
                'retrying in' in r.getMessage() for r in caplog.records
            ), 'the deterministic answer skips the whole retry walk'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_single_terminal_error_per_redirect_delivery(self, delivery_env, caplog):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(302))
            with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(1.0, 5.0, 30.0), dlq_uid='uid')
            errors = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert len(errors) == 1
            webhooks.enqueue_dev_webhook_dlq.assert_called_once()
        finally:
            breaker.record_success()


class TestRedirectKindObservability:
    @pytest.mark.asyncio
    async def test_realtime_redirect_fails_journey_as_upstream_rejected(self, delivery_env):
        journey = MagicMock()
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            with patch.object(webhooks, 'ClientJourneyAttempt', MagicMock(return_value=journey)):
                await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            journey.fail.assert_called_once_with('upstream_rejected')
            journey.succeed.assert_not_called()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_memory_created_redirect_counts_breaker_failure_once(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            failures_before = breaker._failures
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='ios'))
            assert breaker._failures == failures_before + 1, 'the caller still counts the terminal answer'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_audio_bytes_redirect_logs_no_exhausted_info(self, delivery_env, caplog):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            with caplog.at_level(logging.INFO, logger=webhooks.__name__):
                await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
            assert not any(
                'dev webhook delivery exhausted' in r.getMessage() for r in caplog.records
            ), 'a redirect is a receiver answer, not a transport failure'
        finally:
            breaker.record_success()


class TestRedirectInteractionContracts:
    @pytest.mark.asyncio
    async def test_multi_ip_destination_dials_only_the_first_address(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.dns.return_value = _addresses(PUBLIC_IP, PUBLIC_IP_B)
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert response.status_code == 307
            assert delivery_env.client.post.await_count == 1, 'the host answered; other IPs serve the same host'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_open_breaker_skips_before_any_redirect_dial(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert breaker.allow_request() is False

            delivery_env.client.post.reset_mock()
            webhooks.enqueue_dev_webhook_dlq.reset_mock()
            skipped = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(1.0,), dlq_uid='uid')
            assert skipped is None
            delivery_env.client.post.assert_not_awaited()
            webhooks.enqueue_dev_webhook_dlq.assert_not_called()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_idempotency_key_attached_to_the_single_redirect_dial(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook(
                'test_webhook', URL, retry_delays=(), idempotency_key='ik-9', dlq_uid='uid'
            )
            request_kwargs = delivery_env.client.post.call_args.kwargs
            assert request_kwargs['headers']['Idempotency-Key'] == 'ik-9'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_shared_across_kinds_for_redirects(self, delivery_env):
        breaker_a = get_webhook_circuit_breaker(URL)
        breaker_b = get_webhook_circuit_breaker(URL_B)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(301))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            assert delivery_env.client.post.await_count == 1

            delivery_env.client.reset_mock()
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))
            await webhooks.day_summary_webhook('uid', 'summary')
            delivery_env.client.post.assert_not_awaited()  # the hold is destination-keyed, not kind-keyed
        finally:
            breaker_a.record_success()
            breaker_b.record_success()


class TestPerKindSingleDialOnSchedule:
    """Each kind's trigger dials exactly once for a redirect even with the full
    default retry schedule configured — the burn the classification removes."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('kind', ['memory', 'day', 'realtime', 'audio', 'button'])
    async def test_kind_trigger_dials_once_with_default_schedule(self, delivery_env, kind):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await TestRedirectHoldPerKind._call_kind(kind, None)
            assert delivery_env.client.post.await_count == 1
            assert not webhooks.asyncio.sleep.await_count, 'no retry sleeps'
        finally:
            breaker.record_success()


class TestRedirectChunkAndBatchContracts:
    @pytest.mark.asyncio
    async def test_audio_bytes_multi_chunk_payload_stops_after_first_redirect(self, delivery_env):
        """20000 bytes at 8 kHz spans several 1-second chunks; the first
        chunk's redirect ends the whole delivery — one dial, one ladder count,
        remaining chunks never sent."""
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(20000))
            assert delivery_env.client.post.await_count == 1
            assert [call[2] for call in delivery_env.health.calls] == [307]
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_realtime_multi_segment_batch_is_one_dial(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'a'}, {'text': 'b'}, {'text': 'c'}])
            assert delivery_env.client.post.await_count == 1
            payload = delivery_env.client.post.call_args.kwargs['json']
            assert len(payload['segments']) == 3, 'the whole batch rides the single dial'
        finally:
            breaker.record_success()


class TestRedirectRecoveryProbe:
    @pytest.mark.asyncio
    async def test_expired_hold_admits_exactly_one_probe(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert breaker.allow_request() is False

            breaker._rejection_until = 0.0
            breaker._state = 'half_open'
            assert breaker.allow_request() is True, 'the probe is admitted once'
            assert breaker.allow_request() is False, 'a second concurrent probe is blocked'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_probe_redirect_re_arms_the_hold(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            breaker._rejection_until = 0.0
            breaker._state = 'half_open'
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert breaker.allow_request() is False, 'the probe found the same redirect and re-arms'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_hold_blocks_even_with_an_open_outage_latch(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            for _ in range(5):
                breaker.record_failure()
            assert breaker.state == 'open'
            breaker._last_failure_time = time.monotonic() - 31
            assert breaker.state == 'half_open'
            assert breaker.allow_request() is False, 'the redirect hold gates the half-open probe too'
        finally:
            breaker.record_success()


class TestRedirectNoSleepContract:
    @pytest.mark.asyncio
    async def test_asyncio_sleep_never_awaited_for_redirect_schedule(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(301))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(1.0, 5.0, 30.0), dlq_uid='uid')
            webhooks.asyncio.sleep.assert_not_awaited(), 'the 1s/5s/30s walk never starts'
        finally:
            breaker.record_success()


class TestLadderFallbackParityForRedirects:
    def test_non_lua_fallback_counts_redirect_status(self, monkeypatch):
        """fakeredis-style deployments take the non-Lua fallback; a redirect
        must advance it exactly like a 4xx so both redis modes agree."""
        from database import webhook_health

        store = {}

        class _Fake:
            def hget(self, key, field):
                return store.get((key, field))

            def hset(self, key, mapping=None, field=None, value=None):
                if mapping:
                    for k, v in mapping.items():
                        store[(key, k)] = v
                else:
                    store[(key, field)] = value

            def hincrby(self, key, field, amount):
                current = int(store.get((key, field)) or 0) + amount
                store[(key, field)] = str(current)
                return current

            def expire(self, key, ttl):
                pass

        monkeypatch.setattr(webhook_health, 'r', _Fake())
        should_disable = webhook_health._record_dev_webhook_failure_fallback('uid', 'audio_bytes', 307, 'HTTP 307')
        assert should_disable is False
        assert store[('dev_webhook_health:uid:audio_bytes', 'last_status')] == '307'
        assert store[('dev_webhook_health:uid:audio_bytes', 'failure_count')] == '1'

    def test_app_webhook_sibling_routes_redirect_to_notice_not_ladder(self, monkeypatch):
        """The documented asymmetry the delivery layer now mirrors: the
        app-webhook health path classifies a 3xx as redirect-not-followed
        (action 4, notify only) instead of outage evidence."""
        from database import webhook_health

        stored = {}

        class _Fake:
            def hset(self, key, mapping=None):
                stored[key] = mapping

            def expire(self, key, ttl):
                pass

            def set(self, key, value, nx=False, ex=None):
                if key in stored:
                    return False
                stored[key] = value
                return True

        monkeypatch.setattr(webhook_health, 'r', _Fake())
        action = webhook_health.record_app_webhook_failure('app-1', 307, 'HTTP 307')
        assert action == webhook_health.ACTION_REDIRECT_NOT_FOLLOWED
        assert any('app_webhook_redirect_notice' in key for key in stored), 'a notice is armed, not a failure count'
        assert not any(
            'app_webhook_health' in key and 'failure_count' in stored.get(key, {}) for key in stored
        ), 'the redirect never advances the disable ladder'

    def test_app_webhook_ladder_still_counts_4xx(self, monkeypatch):
        from database import webhook_health

        mock_script = MagicMock(return_value=0)
        with patch('database.webhook_health._get_failure_script', return_value=mock_script):
            action = webhook_health.record_app_webhook_failure('app-1', 400, 'HTTP 400')
        assert action == 0
        mock_script.assert_called_once(), '4xx keeps the failure ladder'


class TestRedirectClassificationBoundary:
    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [299, 400])
    async def test_statuses_around_the_3xx_boundary_keep_their_class(self, delivery_env, status):
        """299 is not defined; 400 is the deterministic 4xx anchor. Neither is
        a redirect member — the boundary is exact [300, 400)."""
        assert webhooks._is_redirect_answer(status) is False
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(status))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            # both are one-dial answers (299 rides the 2xx... never happens in
            # practice; 400 rides the 4xx latch) — the assertion here is the
            # helper boundary, not the dial count.
            assert delivery_env.client.post.await_count == 1
        finally:
            breaker.record_success()


class TestPerKindDlqForRedirect:
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
                    'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-20T00:00:00Z'
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
    async def test_kind_redirect_writes_one_dlq_entry_with_kind_name(self, delivery_env, kind_call, webhook_name):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await kind_call()
            assert webhooks.enqueue_dev_webhook_dlq.call_count == 1
            kwargs = webhooks.enqueue_dev_webhook_dlq.call_args.kwargs
            assert kwargs['webhook_name'] == webhook_name
            assert kwargs['status_code'] == 307
        finally:
            breaker.record_success()


class TestRedirectCallerSideContracts:
    @pytest.mark.asyncio
    async def test_memory_created_redirect_is_not_a_dependency_skip(self, delivery_env):
        """A 3xx came from the receiver: the journey records upstream_rejected,
        never the breaker-skip classification."""
        journey = MagicMock()
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            with patch.object(webhooks, 'ClientJourneyAttempt', MagicMock(return_value=journey)):
                await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='ios'))
            assert journey.fail.call_args_list == [
                call('upstream_rejected')
            ], 'a receiver answer is upstream_rejected, never the breaker-skip classification'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_day_summary_redirect_takes_no_success_notification_path(self, delivery_env):
        """A 3xx is not delivered: the 200-only in-band message notification
        must not fire and record_dev_webhook_success must not run."""
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(302, json={'message': 'hello there'}))
            await webhooks.day_summary_webhook('uid', 'summary')
            webhooks.send_notification.assert_not_called()
            webhooks.record_dev_webhook_success.assert_not_called()
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_audio_bytes_redirect_returns_without_draining_the_queue(self, delivery_env):
        """The chunk loop returns after the first chunk's redirect instead of
        retrying the remaining chunks — the delivery trigger ends there."""
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(50000))
            # 50000 bytes at 8 kHz spans four 1-second chunks; the redirect on
            # chunk one ends the delivery with a single dial.
            assert delivery_env.client.post.await_count == 1
            assert [call[2] for call in delivery_env.health.calls] == [307]
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_button_event_redirect_releases_the_serialization_lock(self, delivery_env):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks.button_event_webhook(
                'uid', button_event='single', device_id='d', event_id='e', timestamp='2026-10-20T00:00:00Z'
            )
            lock = await webhooks._get_button_event_send_lock('uid', 'd')
            assert not lock.locked(), 'a failed delivery must not hold the per-device lock'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_redirect_from_real_dial_arms_after_a_refusal_did_not(self, delivery_env, monkeypatch):
        """Evidence scoping stays response-sourced: the SSRF synthetic 400 arms
        nothing, and a later real 307 from the same destination does."""
        breaker = get_webhook_circuit_breaker(URL)
        try:
            from utils.http_client import UnsafeWebhookURLError

            with patch('utils.webhooks.safe_request_targets', MagicMock(side_effect=UnsafeWebhookURLError('no'))):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
            assert breaker.allow_request() is True, 'the refusal arms nothing'

            delivery_env.client.post = AsyncMock(return_value=httpx.Response(307))
            await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(), dlq_uid='uid')
            assert breaker.allow_request() is False, 'the real receiver answer arms the hold'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    @pytest.mark.parametrize('status', [301, 307, 308])
    async def test_redirect_counts_exactly_one_breaker_failure_per_delivery(self, delivery_env, status):
        breaker = get_webhook_circuit_breaker(URL)
        try:
            failures_before = breaker._failures
            delivery_env.client.post = AsyncMock(return_value=httpx.Response(status))
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
            assert (
                breaker._failures == failures_before + 1
            ), 'the caller counts the terminal answer once; the hold carries the cooldown'
        finally:
            breaker.record_success()

    @pytest.mark.asyncio
    async def test_redirect_delivery_completes_without_the_retry_wall_clock(self, delivery_env):
        """A redirect delivery with the default schedule finishes in bounded
        time — no 36 s of sleeps — even though the endpoint answered late."""
        breaker = get_webhook_circuit_breaker(URL)
        try:

            async def _slow_redirect(url, **kwargs):
                await asyncio.sleep(0)
                return httpx.Response(307)

            delivery_env.client.post = _slow_redirect
            started = time.monotonic()
            response = await webhooks._post_dev_webhook(
                'test_webhook', URL, retry_delays=(1.0, 5.0, 30.0), dlq_uid='uid'
            )
            elapsed = time.monotonic() - started
            assert response.status_code == 307
            assert elapsed < 1.0, 'one dial, no schedule: the delivery cannot absorb the retry delays'
        finally:
            breaker.record_success()
