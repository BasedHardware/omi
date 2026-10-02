"""Hermetic developer webhook delivery checks: DNS pinning, rejection and safe logs."""

import logging
import socket
import ssl
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from models.users import WebhookType
from utils import http_client, webhooks

PUBLIC_IP = '8.8.8.8'
URL = 'https://receiver.example/hook?token=secret-query'


def _addresses(*ips):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0)) for ip in ips]


@pytest.fixture
def delivery(monkeypatch):
    dns = MagicMock(return_value=_addresses(PUBLIC_IP))
    monkeypatch.setattr(socket, 'getaddrinfo', dns)
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(200))
    monkeypatch.setattr(webhooks, 'get_webhook_client', lambda: client)
    monkeypatch.setattr(webhooks.asyncio, 'sleep', AsyncMock())
    monkeypatch.setattr(webhooks, 'enqueue_dev_webhook_dlq', MagicMock())
    monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
    monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=URL))
    monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', MagicMock(return_value=True))
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())
    monkeypatch.setattr(webhooks, 'disable_user_webhook_db', MagicMock())
    monkeypatch.setattr(webhooks, 'send_notification', MagicMock())
    monkeypatch.setattr(webhooks, '_build_conversation_webhook_payload_sync', MagicMock(return_value={}))
    cb = MagicMock()
    cb.allow_request.return_value = True
    monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', lambda _: cb)
    return client, dns, cb


@pytest.mark.asyncio
async def test_target_that_turns_private_after_save_is_rejected(delivery):
    client, dns, _ = delivery
    dns.side_effect = [_addresses(PUBLIC_IP), _addresses('10.0.0.5')]
    # The setter validates, but stores the original URL instead of this pinned target.
    assert http_client.safe_request_target(URL)[0] == f'https://{PUBLIC_IP}/hook?token=secret-query'
    response = await webhooks._post_dev_webhook('test', URL, retry_delays=(1, 5, 30), idempotency_key='event')
    assert response.status_code == 400
    assert dns.call_count == 2
    client.post.assert_not_awaited()
    webhooks.asyncio.sleep.assert_not_awaited()
    assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 400
    assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['idempotency_key'] == 'event'


@pytest.mark.asyncio
@pytest.mark.parametrize('ips', [(PUBLIC_IP, '169.254.169.254'), ('127.0.0.1', PUBLIC_IP)])
async def test_mixed_public_private_answers_are_rejected(delivery, ips):
    client, dns, _ = delivery
    dns.return_value = _addresses(*ips)
    response = await webhooks._post_dev_webhook('test', URL, retry_delays=(1, 5))
    assert response.status_code == 400
    client.post.assert_not_awaited()
    webhooks.asyncio.sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('first_result', [httpx.Response(503), httpx.ConnectError('connection failed')])
async def test_retry_resolves_and_pins_again_with_stable_idempotency(delivery, first_result):
    client, dns, _ = delivery
    dns.side_effect = [_addresses(PUBLIC_IP), _addresses('1.1.1.1')]
    client.post.side_effect = [first_result, httpx.Response(200)]
    response = await webhooks._post_dev_webhook(
        'test', URL, json={'event': 1}, retry_delays=(1,), idempotency_key='stable-event'
    )
    assert response.status_code == 200
    assert dns.call_count == 2
    calls = client.post.await_args_list
    assert [call.args[0] for call in calls] == [
        f'https://{PUBLIC_IP}/hook?token=secret-query',
        'https://1.1.1.1/hook?token=secret-query',
    ]
    assert [call.kwargs['headers']['Idempotency-Key'] for call in calls] == ['stable-event', 'stable-event']
    assert all(call.kwargs['headers']['Host'] == 'receiver.example' for call in calls)
    assert all(call.kwargs['extensions']['sni_hostname'] == 'receiver.example' for call in calls)
    webhooks.asyncio.sleep.assert_awaited_once_with(1)
    webhooks.enqueue_dev_webhook_dlq.assert_not_called()


@pytest.mark.asyncio
async def test_retry_that_turns_private_stops_and_discards_previous_response(delivery):
    client, dns, _ = delivery
    dns.side_effect = [_addresses(PUBLIC_IP), _addresses('192.168.1.10')]
    client.post.return_value = httpx.Response(503)
    response = await webhooks._post_dev_webhook('test', URL, retry_delays=(1, 5, 30))
    assert response.status_code == 400
    assert client.post.await_count == 1
    assert dns.call_count == 2
    webhooks.asyncio.sleep.assert_awaited_once_with(1)
    assert webhooks.enqueue_dev_webhook_dlq.call_args.kwargs['status_code'] == 400


@pytest.mark.asyncio
async def test_host_port_and_sni_override_untrusted_kwargs_without_mutating_them(delivery):
    client, _, _ = delivery
    headers = {'host': 'wrong.example', 'Content-Type': 'application/json', 'Idempotency-Key': 'supplied'}
    extensions = {'sni_hostname': 'wrong.example', 'custom': 'value'}
    await webhooks._post_dev_webhook(
        'test', 'https://receiver.example:8443/hook', headers=headers, extensions=extensions, retry_delays=()
    )
    call = client.post.await_args
    assert call.args[0] == f'https://{PUBLIC_IP}:8443/hook'
    assert call.kwargs['headers'] == {
        'Host': 'receiver.example:8443',
        'Content-Type': 'application/json',
        'Idempotency-Key': 'supplied',
    }
    assert call.kwargs['extensions'] == {'sni_hostname': 'receiver.example', 'custom': 'value'}
    assert headers['host'] == 'wrong.example'
    assert extensions['sni_hostname'] == 'wrong.example'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'url',
    [
        'http://localhost/hook',
        'ftp://receiver.example/hook',
        'http://[bad-ipv6/x',
        'https://receiver.example:bad/hook',
        'https://receiver.example:70000/hook',
    ],
)
async def test_legacy_invalid_stored_url_returns_rejection(delivery, url):
    client, dns, _ = delivery
    dns.return_value = _addresses('127.0.0.1' if 'localhost' in url else PUBLIC_IP)
    response = await webhooks._post_dev_webhook('test', url, retry_delays=(1, 5, 30))
    assert response.status_code == 400
    client.post.assert_not_awaited()
    webhooks.asyncio.sleep.assert_not_awaited()
    webhooks.enqueue_dev_webhook_dlq.assert_called_once()


@pytest.mark.asyncio
async def test_unresolvable_stored_host_is_non_retryable(delivery):
    client, dns, _ = delivery
    dns.side_effect = socket.gaierror('no records')
    response = await webhooks._post_dev_webhook('test', URL, retry_delays=(1, 5))
    assert response.status_code == 400
    assert dns.call_count == 1
    client.post.assert_not_awaited()
    webhooks.asyncio.sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_redirect_is_not_followed_even_if_client_or_caller_enables_it(delivery, monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
        monkeypatch.setattr(webhooks, 'get_webhook_client', lambda: client)
        response = await webhooks._post_dev_webhook('test', URL, retry_delays=(), follow_redirects=True)
    assert response.status_code == 302
    assert len(seen) == 1
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers['Host'] == 'receiver.example'
    assert seen[0].extensions['sni_hostname'] == 'receiver.example'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 400])
async def test_success_and_failure_logs_redact_userinfo_query_and_fragment(delivery, caplog, status):
    client, _, _ = delivery
    client.post.return_value = httpx.Response(status)
    with caplog.at_level(logging.INFO, logger=webhooks.__name__):
        await webhooks._post_dev_webhook(
            'test',
            'https://secret-user:secret-password@receiver.example/hook?token=secret-query#secret-fragment',
            retry_delays=(),
        )
    assert 'url=https://receiver.example/hook' in caplog.text
    for secret in ('secret-user', 'secret-password', 'secret-query', 'secret-fragment'):
        assert secret not in caplog.text


async def _deliver(kind):
    if kind == WebhookType.memory_created:
        await webhooks.conversation_created_webhook('uid', MagicMock(is_locked=False, client_platform='mobile_ios'))
    elif kind == WebhookType.day_summary:
        await webhooks.day_summary_webhook('uid', 'summary')
    elif kind == WebhookType.realtime_transcript:
        await webhooks.realtime_transcript_webhook('uid', [{'text': 'hello'}])
    elif kind == WebhookType.audio_bytes:
        await webhooks.send_audio_bytes_developer_webhook('uid', 8000, bytearray(b'\x00\x00'))
    else:
        await webhooks.button_event_webhook(
            'uid', button_event='single', device_id='device', event_id='event', timestamp='2026-10-03T00:00:00Z'
        )


WEBHOOK_TYPES = [
    WebhookType.memory_created,
    WebhookType.day_summary,
    WebhookType.realtime_transcript,
    WebhookType.audio_bytes,
    WebhookType.button_event,
]


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', WEBHOOK_TYPES)
async def test_invalid_destination_uses_existing_health_disable_and_notification_path(delivery, kind):
    client, dns, cb = delivery
    dns.return_value = _addresses('10.0.0.5')
    await _deliver(kind)
    client.post.assert_not_awaited()
    webhooks.asyncio.sleep.assert_not_awaited()
    cb.record_failure.assert_called_once_with()
    cb.record_success.assert_not_called()
    webhooks.record_dev_webhook_failure.assert_called_once_with('uid', kind, 400, 'HTTP 400')
    webhooks.record_dev_webhook_success.assert_not_called()
    webhooks.disable_user_webhook_db.assert_called_once_with('uid', kind)
    webhooks.send_notification.assert_called_once()
    webhooks.enqueue_dev_webhook_dlq.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', WEBHOOK_TYPES)
async def test_circuit_open_logs_redact_url(delivery, caplog, kind):
    client, _, cb = delivery
    cb.allow_request.return_value = False
    with caplog.at_level(logging.INFO, logger=webhooks.__name__):
        await _deliver(kind)
    assert 'https://receiver.example/hook' in caplog.text
    assert 'secret-query' not in caplog.text
    assert '?uid=' not in caplog.text
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_exception_logs_do_not_echo_a_url_from_the_transport(delivery, caplog, monkeypatch):
    client, _, _ = delivery
    client.post.side_effect = httpx.ConnectError(f'failed to reach {URL}')
    monkeypatch.setattr(webhooks, '_get_dev_webhook_retry_delays', lambda: ())
    with caplog.at_level(logging.INFO, logger=webhooks.__name__):
        await webhooks.day_summary_webhook('uid', 'summary')
    assert 'secret-query' not in caplog.text
    assert 'ConnectError' in caplog.text


class _Network:
    """Fake httpcore network: run actual HTTPX request construction without sockets."""

    def __init__(self):
        self.connects = []
        self.tls_names = []

    async def connect_tcp(self, **kwargs):
        self.connects.append((kwargs['host'], kwargs['port']))
        return _Stream(self)


class _Stream:
    def __init__(self, network):
        self.network = network

    async def read(self, max_bytes, timeout=None):
        return b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'

    async def write(self, buffer, timeout=None):
        pass

    async def aclose(self):
        pass

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        assert ssl_context.check_hostname is True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        self.network.tls_names.append(server_hostname)
        return self

    def get_extra_info(self, info):
        return None


@pytest.fixture
async def pinned_client(delivery, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.example:8080')
    monkeypatch.setattr(http_client, '_get_client', lambda name, factory: factory())
    network = _Network()
    async with http_client.get_webhook_client() as client:
        client._transport._pool._network_backend = network
        monkeypatch.setattr(webhooks, 'get_webhook_client', lambda: client)
        yield client, network


@pytest.mark.asyncio
async def test_pinned_ip_connects_and_each_hostname_gets_tls_verification(pinned_client):
    client, network = pinned_client
    # No environment proxy may replace the pinned direct connection.
    assert client._mounts == {}
    for host in ('first.example', 'second.example'):
        response = await webhooks._post_dev_webhook('test', f'https://{host}/hook', retry_delays=())
        assert response.status_code == 200
    assert network.connects == [(PUBLIC_IP, 443), (PUBLIC_IP, 443)]
    assert network.tls_names == ['first.example', 'second.example']


@pytest.mark.asyncio
async def test_pinning_preserves_legacy_url_basic_auth(delivery, monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(webhooks, 'get_webhook_client', lambda: client)
        response = await webhooks._post_dev_webhook('test', 'https://user:pass@receiver.example/hook', retry_delays=())
    assert response.status_code == 200
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers['Authorization'] == 'Basic dXNlcjpwYXNz'
    assert seen[0].headers['Host'] == 'receiver.example'
