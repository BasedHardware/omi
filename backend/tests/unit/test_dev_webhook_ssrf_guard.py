"""Developer/user webhooks must not be configured against a non-public address (SSRF).

The app-webhook path rejects a private/loopback/link-local/metadata target with ``safe_request_target``
(``utils/app_integrations.py``); the developer/user webhook setter stored any URL, so the backend would
later POST transcript data from inside the network to an internal address, and ``realtime_transcript_webhook``
relayed an internal ``{"message": …}`` response back to the user (exfiltration + internal probing).

DNS is mocked, so these tests are deterministic and make no network calls.
"""

import socket

import pytest
from fastapi import HTTPException

from models.users import WebhookType
from routers import users as users_router
from utils.http_client import UnsafeWebhookURLError


def _resolve_to(monkeypatch, ip: str) -> None:
    monkeypatch.setattr(
        'utils.http_client.socket.getaddrinfo',
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0))],
    )


def test_set_user_webhook_rejects_a_private_target(monkeypatch):
    _resolve_to(monkeypatch, '10.0.0.5')

    stored = []
    monkeypatch.setattr(users_router, 'set_user_webhook_db', lambda *args, **kwargs: stored.append(args))

    request = users_router.SetUserWebhookUrlRequest(url='http://internal.example/hook')
    with pytest.raises(HTTPException) as exc_info:
        users_router.set_user_webhook_endpoint(WebhookType.realtime_transcript, request, uid='uid-1')

    assert exc_info.value.status_code == 400
    assert stored == [], 'a non-public webhook URL must not be stored'


def test_set_user_webhook_rejects_a_loopback_target(monkeypatch):
    _resolve_to(monkeypatch, '127.0.0.1')
    monkeypatch.setattr(users_router, 'set_user_webhook_db', lambda *args, **kwargs: None)

    request = users_router.SetUserWebhookUrlRequest(url='http://localhost/hook')
    with pytest.raises(HTTPException) as exc_info:
        users_router.set_user_webhook_endpoint(WebhookType.realtime_transcript, request, uid='uid-1')

    assert exc_info.value.status_code == 400


def test_set_user_webhook_rejects_a_malformed_url(monkeypatch):
    """A malformed URL (invalid IPv6 literal) raises ValueError in the shared validator, not
    UnsafeWebhookURLError; it must still be a clean 400, never a 500."""
    monkeypatch.setattr(users_router, 'set_user_webhook_db', lambda *args, **kwargs: None)

    request = users_router.SetUserWebhookUrlRequest(url='http://[bad-ipv6/x')
    with pytest.raises(HTTPException) as exc_info:
        users_router.set_user_webhook_endpoint(WebhookType.realtime_transcript, request, uid='uid-1')

    assert exc_info.value.status_code == 400


def test_set_user_webhook_accepts_a_public_target(monkeypatch):
    _resolve_to(monkeypatch, '8.8.8.8')

    stored = []
    monkeypatch.setattr(users_router, 'set_user_webhook_db', lambda *args, **kwargs: stored.append(args))
    monkeypatch.setattr(users_router, 'enable_user_webhook_db', lambda *args, **kwargs: None)
    monkeypatch.setattr(users_router, 'record_dev_webhook_success', lambda *args, **kwargs: None)

    request = users_router.SetUserWebhookUrlRequest(url='https://public.example/hook')
    result = users_router.set_user_webhook_endpoint(WebhookType.realtime_transcript, request, uid='uid-1')
    assert result == {'status': 'ok'}
    assert len(stored) == 1


def test_set_user_webhook_allows_clearing(monkeypatch):
    # Empty URL means "disable"; it must not trip the address check.
    disabled = []
    monkeypatch.setattr(users_router, 'set_user_webhook_db', lambda *args, **kwargs: None)
    monkeypatch.setattr(users_router, 'disable_user_webhook_db', lambda *args, **kwargs: disabled.append(args))

    request = users_router.SetUserWebhookUrlRequest(url='')
    assert users_router.set_user_webhook_endpoint(WebhookType.realtime_transcript, request, uid='uid-1') == {
        'status': 'ok'
    }
    assert len(disabled) == 1
