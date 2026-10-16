"""A dead developer webhook must be retired, not probed forever.

Failure-Class: FC-dev-webhook-circuit-blocks-disable-counter
(new class declared in this diff; the nearest existing class,
FC-automated-disable-without-reachable-recovery, covers the opposite latch —
an automated disable whose clearing control is unreachable — not a disable
that never fires while a delivery guard absorbs the failures it should count.)

Guards:
- deliveries the per-URL circuit breaker skips still advance the per-uid
  disable counter, and never re-poison the breaker (each dev-webhook kind is
  wired separately, so each gets its own guard; a recovery probe closes the
  circuit on the next call);
- the skip is signalled as None — a skipped delivery has no HTTP response, so
  no synthetic status can be mistaken for a receiver's real answer;
- reaching the threshold through skipped probes fires the one-time
  auto-disable notification, exactly like a counted delivery;
- attempts= in the final delivery ERROR log reports dials actually made:
  a one-attempt deterministic 404 no longer claims the full retry schedule;
- healthy deliveries keep their counted POSTs, success recording, and
  response-notification handling unchanged.
"""

import logging
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from models.users import WebhookType
from utils import webhooks
from utils.http_client import UnsafeWebhookURLError

PUBLIC_IP = '8.8.8.8'
URL = 'https://receiver.example/hook?token=secret-query'


def _addresses(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


class _FakeHealth:
    """In-memory record_dev_webhook_failure: True exactly once at ``threshold``.

    Mirrors the Redis ladder's transition contract: the disable action fires on
    the call that reaches the threshold, and later failures return False again
    (the script latches disabled='1' and answers 0).
    """

    def __init__(self, threshold=3):
        self.threshold = threshold
        self.calls = []

    def __call__(self, uid, wtype, status_code, error):
        key = (uid, getattr(wtype, 'value', wtype))
        count = 1 + sum(1 for existing in self.calls if existing[:2] == key)
        self.calls.append((uid, key[1], status_code, error))
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
    health = _FakeHealth(threshold=3)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', health)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())
    cb = MagicMock()
    cb.allow_request.return_value = True
    monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', lambda _: cb)
    return SimpleNamespace(client=client, dns=dns, cb=cb, health=health)


class TestBreakerSkipCountsTowardDisable:
    """Each caller is wired separately, so each kind gets its own guard."""

    @pytest.mark.asyncio
    async def test_realtime_transcript_skip_is_counted(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
        assert delivery_env.health.calls == [('uid', 'realtime_transcript', 0, 'CircuitBreakerOpen')]
        delivery_env.client.post.assert_not_awaited()
        webhooks.record_dev_webhook_success.assert_not_called()
        delivery_env.cb.record_failure.assert_not_called()
        delivery_env.cb.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_bytes_skip_is_counted(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
        assert delivery_env.health.calls == [('uid', 'audio_bytes', 0, 'CircuitBreakerOpen')]
        delivery_env.client.post.assert_not_awaited()
        webhooks.record_dev_webhook_success.assert_not_called()
        delivery_env.cb.record_failure.assert_not_called()
        delivery_env.cb.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_created_skip_is_counted(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))
        assert delivery_env.health.calls == [('uid', 'memory_created', 0, 'CircuitBreakerOpen')]
        delivery_env.client.post.assert_not_awaited()
        webhooks.record_dev_webhook_success.assert_not_called()
        delivery_env.cb.record_failure.assert_not_called()
        delivery_env.cb.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_day_summary_skip_is_counted(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        await webhooks.day_summary_webhook('uid', 'summary')
        assert delivery_env.health.calls == [('uid', 'day_summary', 0, 'CircuitBreakerOpen')]
        delivery_env.client.post.assert_not_awaited()
        webhooks.record_dev_webhook_success.assert_not_called()
        delivery_env.cb.record_failure.assert_not_called()
        delivery_env.cb.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_button_event_skip_is_counted(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        await webhooks.button_event_webhook(
            'uid', button_event='single', device_id='device', event_id='event', timestamp='2026-10-03T00:00:00Z'
        )
        assert delivery_env.health.calls == [('uid', 'button_event', 0, 'CircuitBreakerOpen')]
        delivery_env.client.post.assert_not_awaited()
        webhooks.record_dev_webhook_success.assert_not_called()
        delivery_env.cb.record_failure.assert_not_called()
        delivery_env.cb.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_sends_no_network_no_dlq_redacted_info(self, delivery_env, caplog):
        delivery_env.cb.allow_request.return_value = False
        with caplog.at_level(logging.INFO, logger=webhooks.__name__):
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
        delivery_env.client.post.assert_not_awaited()
        webhooks.asyncio.sleep.assert_not_awaited()
        webhooks.enqueue_dev_webhook_dlq.assert_not_called()
        assert 'circuit breaker open' in caplog.text
        assert 'receiver.example/hook' in caplog.text
        assert 'secret-query' not in caplog.text

    @pytest.mark.asyncio
    async def test_threshold_reached_via_probes_disables_and_notifies_once(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        for _ in range(3):
            await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])

        assert len(delivery_env.health.calls) == 3
        webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.realtime_transcript)
        webhooks.send_notification.assert_called_once()
        notify_args = webhooks.send_notification.call_args[0]
        assert notify_args[0] == 'uid'
        assert 'Auto-Disabled' in notify_args[1]


class TestSkipIsTypedNotSyntheticStatus:
    """A skipped delivery has no HTTP response; None is the only honest signal."""

    @pytest.mark.asyncio
    async def test_post_dev_webhook_returns_none_on_open_breaker(self, delivery_env):
        delivery_env.cb.allow_request.return_value = False
        response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1,))
        assert response is None

    @pytest.mark.asyncio
    async def test_post_dev_webhook_never_returns_synthetic_skip_status(self, delivery_env):
        """Guard the historical 503-sentinel shape: while the breaker admits a
        request, no synthetic skip status may appear — a receiver's genuine
        503 must keep flowing through the real failure path."""
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))
        response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=())
        assert response is not None
        assert response.status_code == 503
        webhooks.enqueue_dev_webhook_dlq.assert_called_once()

    @pytest.mark.asyncio
    async def test_receiver_genuine_503_still_records_failure_and_poisons_breaker(self, delivery_env):
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))
        await webhooks.day_summary_webhook('uid', 'summary')
        assert delivery_env.health.calls == [('uid', 'day_summary', 503, 'HTTP 503')]
        delivery_env.cb.record_failure.assert_called_once()
        webhooks.record_dev_webhook_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_receiver_genuine_503_on_audio_bytes_counts_failure(self, delivery_env):
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))
        await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
        assert delivery_env.health.calls == [('uid', 'audio_bytes', 503, 'HTTP 503')]
        delivery_env.cb.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsafe_target_refusal_counts_http_400_not_breaker_skip(self, delivery_env):
        """The invalid-target refusal is a REAL counted failure: breaker poison
        and the HTTP 400 classification — the exact contrast to the skip."""
        with patch('utils.webhooks.safe_request_targets', MagicMock(side_effect=UnsafeWebhookURLError('private'))):
            await webhooks.day_summary_webhook('uid', 'summary')
        assert delivery_env.health.calls == [('uid', 'day_summary', 400, 'HTTP 400')]
        delivery_env.cb.record_failure.assert_called_once()
        assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 400

    @pytest.mark.asyncio
    async def test_full_schedule_exhaustion_still_reports_attempts_4(self, delivery_env, caplog):
        """Honesty must not undercount: three transient 503s plus a final
        deterministic 404 really dial four times and report attempts=4."""
        delivery_env.client.post = AsyncMock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503), httpx.Response(404)]
        )
        with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
            response = await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1, 0.2, 0.3))

        assert response.status_code == 404
        assert delivery_env.client.post.await_count == 4
        assert 'attempts=4' in caplog.text
        assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 404

    @pytest.mark.asyncio
    async def test_audio_bytes_skip_terminates_chunk_loop_after_one_count(self, delivery_env):
        """One delivery trigger counts once: the breaker skip ends the chunk
        loop instead of counting a skip per chunk."""
        delivery_env.cb.allow_request.return_value = False
        # 20000 bytes at 8000 Hz spans several 1-second chunks if delivered.
        await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(20000))
        assert len(delivery_env.health.calls) == 1
        assert delivery_env.health.calls[0] == ('uid', 'audio_bytes', 0, 'CircuitBreakerOpen')

    @pytest.mark.asyncio
    async def test_mixed_real_failures_and_skips_converge_on_one_ladder(self, delivery_env):
        """Real counted failures and skips accumulate in the same per-uid
        counter: two genuine 503s then a breaker skip reaches the threshold."""
        delivery_env.cb.allow_request.side_effect = [True, True, False]
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(503))

        await webhooks.day_summary_webhook('uid', 'one')
        await webhooks.day_summary_webhook('uid', 'two')
        await webhooks.day_summary_webhook('uid', 'three')

        assert [call[2:] for call in delivery_env.health.calls] == [
            (503, 'HTTP 503'),
            (503, 'HTTP 503'),
            (0, 'CircuitBreakerOpen'),
        ]
        webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.day_summary)
        webhooks.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_bytes_threshold_via_skips_disables(self, delivery_env):
        """The audio branch's disable wiring (inside the chunk loop, before the
        early return) fires the one-time disable exactly like other kinds."""
        delivery_env.cb.allow_request.return_value = False
        for _ in range(3):
            await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))

        webhooks.disable_user_webhook_db.assert_called_once_with('uid', WebhookType.audio_bytes)
        webhooks.send_notification.assert_called_once()
        assert len(delivery_env.health.calls) == 3


class TestProbeFailureHelperContract:
    @pytest.mark.asyncio
    async def test_helper_without_uid_is_a_noop(self):
        with patch.object(webhooks, 'record_dev_webhook_failure') as fail:
            assert await webhooks._record_dev_webhook_probe_failure(None, WebhookType.audio_bytes) is False
        fail.assert_not_called()

    @pytest.mark.asyncio
    async def test_helper_delegates_transport_failure_convention(self):
        with patch.object(webhooks, 'record_dev_webhook_failure', return_value=True) as fail:
            assert await webhooks._record_dev_webhook_probe_failure('uid', WebhookType.audio_bytes) is True
        fail.assert_called_once_with('uid', WebhookType.audio_bytes, 0, 'CircuitBreakerOpen')


class TestAttemptsLogHonesty:
    @pytest.mark.asyncio
    async def test_deterministic_rejection_reports_only_dials_made(self, delivery_env, caplog):
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(404))
        with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
            response = await webhooks._post_dev_webhook(
                'test_webhook', URL, retry_delays=(0.1, 0.2, 0.3), idempotency_key='event-404', dlq_uid='uid'
            )

        assert response.status_code == 404
        assert delivery_env.client.post.await_count == 1, 'deterministic 4xx stays single-attempt'
        assert 'attempts=1' in caplog.text, 'must not claim the full 4-attempt schedule'
        assert 'retrying in' not in caplog.text
        webhooks.asyncio.sleep.assert_not_awaited()
        assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 404
        assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['idempotency_key'] == 'event-404'

    @pytest.mark.asyncio
    async def test_connect_failure_reports_only_dials_made(self, delivery_env, caplog):
        delivery_env.client.post = AsyncMock(side_effect=httpx.ConnectError('refused'))
        with caplog.at_level(logging.ERROR, logger=webhooks.__name__):
            with pytest.raises(httpx.ConnectError):
                await webhooks._post_dev_webhook('test_webhook', URL, retry_delays=(0.1,))

        assert delivery_env.client.post.await_count == 2
        assert 'attempts=2' in caplog.text


class TestHealthyPathUnchanged:
    @pytest.mark.asyncio
    async def test_healthy_delivery_keeps_post_success_and_no_failure_count(self, delivery_env):
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))

        await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])

        assert delivery_env.client.post.await_count == 1
        webhooks.record_dev_webhook_success.assert_called_once()
        assert delivery_env.health.calls == []
        delivery_env.cb.record_success.assert_called_once()
        delivery_env.cb.record_failure.assert_not_called()
        webhooks.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_recovery_probe_closes_circuit_without_breaker_poison(self, delivery_env):
        delivery_env.cb.allow_request.side_effect = [False, True]
        delivery_env.client.post = AsyncMock(return_value=httpx.Response(200, json={}))

        await webhooks.realtime_transcript_webhook('uid', [{'text': 'first'}])
        await webhooks.realtime_transcript_webhook('uid', [{'text': 'second'}])

        # First call: skip counted. Second call: real delivery succeeds.
        assert delivery_env.health.calls == [('uid', 'realtime_transcript', 0, 'CircuitBreakerOpen')]
        assert delivery_env.client.post.await_count == 1
        webhooks.record_dev_webhook_success.assert_called_once()
        delivery_env.cb.record_success.assert_called_once()
        delivery_env.cb.record_failure.assert_not_called()
