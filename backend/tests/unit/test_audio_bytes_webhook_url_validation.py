"""Hermetic unit tests for audio bytes developer webhook URL validation (#20666).

Ensures that configured audio-bytes webhook URLs accepted during configuration
(including root URLs with queries omitting explicit slashes and bracketed IPv6 literals)
are not prematurely rejected before delivery in send_audio_bytes_developer_webhook.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

if 'prometheus_client' in sys.modules:
    setattr(sys.modules['prometheus_client'], 'disable_created_metrics', lambda: None)

# Ensure hermetic execution without requiring live database or cloud SDKs
_STUB = (
    'database',
    'google',
    'firebase_admin',
    'redis',
    'prometheus_client',
    'fcm_django',
    'pusher',
    'anthropic',
    'openai',
    'utils.notifications',
    'utils.conversations.render',
)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_PRE_EXISTING_MODULES = set(sys.modules.keys())
_finder = _Finder()
sys.meta_path.insert(0, _finder)
try:
    from models.users import WebhookType
    from utils import webhooks
finally:
    sys.meta_path.remove(_finder)


def teardown_module(module=None):
    """Restore sys.modules to prevent stubs from leaking into subsequent test files."""
    for key in list(sys.modules.keys()):
        if key not in _PRE_EXISTING_MODULES:
            sys.modules.pop(key, None)


@pytest.mark.parametrize(
    'url,expected',
    [
        # Path-free query on root hostname (Issue #20666 synthetic repro 1)
        ('https://hooks.example.com?token=synthetic', True),
        ('https://hooks.example.com/?token=synthetic', True),
        ('https://hooks.example.com:8443?token=synthetic', True),
        # Bracketed public IPv6 literal (Issue #20666 synthetic repro 2)
        ('https://[2606:4700:4700::1111]/audio', True),
        ('https://[2606:4700:4700::1111]:8080/audio', True),
        ('https://[2606:4700:4700::1111]?token=synthetic', True),
        ('https://[2606:4700:4700::1111]', True),
        # Dotted IPv4-mapped IPv6 literals
        ('https://[::ffff:8.8.8.8]/', True),
        ('https://[::ffff:8.8.8.8]:8443/audio', True),
        ('https://[::ffff:198.51.100.1]?token=synthetic', True),
        # Standard hostnames and IPv4
        ('http://localhost:8000/webhook', True),
        ('http://198.51.100.1:8080/audio', True),
        ('http://198.51.100.1:8080?token=xyz', True),
        ('https://example.com', True),
        ('https://example.com/', True),
        ('https://example.com/audio/stream', True),
        ('https://example.com#fragment', True),
        # Invalid schemes and malformed candidates
        ('', False),
        (None, False),
        (12345, False),
        ('not-a-url', False),
        ('ftp://example.com/audio', False),
        ('javascript:alert(1)', False),
        ('https://example.com with spaces', False),
        ('https://[invalid-ipv6-chars]/audio', False),
        # Valid bracket characters that fail urlsplit IPv6 parsing (exercises ValueError handler)
        ('https://[::::]/', False),
        ('https://[::1::1]/', False),
    ],
)
def test_is_valid_audio_bytes_webhook_url(url, expected):
    """Verify _is_valid_audio_bytes_webhook_url correctly validates target formats."""
    assert webhooks._is_valid_audio_bytes_webhook_url(url) is expected


@pytest.mark.parametrize(
    'configured_url,expected_prefix',
    [
        (
            'https://hooks.example.com?token=synthetic',
            'https://hooks.example.com?token=synthetic&sample_rate=16000&uid=u1',
        ),
        (
            'https://[2606:4700:4700::1111]/audio',
            'https://[2606:4700:4700::1111]/audio?sample_rate=16000&uid=u1',
        ),
    ],
)
def test_send_audio_bytes_developer_webhook_delivers_query_and_ipv6_urls(monkeypatch, configured_url, expected_prefix):
    """Verify delivery proceeds for root-query and IPv6 URLs without premature rejection."""

    async def _run():
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value=configured_url))

        cb = MagicMock()
        cb.allow_request.return_value = True
        monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', lambda _: cb)

        post_mock = AsyncMock(return_value=httpx.Response(200))
        monkeypatch.setattr(webhooks, '_post_dev_webhook', post_mock)
        monkeypatch.setattr(webhooks, 'record_dev_webhook_success', MagicMock())

        sample_rate = 16000
        pcm_data = bytearray(b'\x00\x00' * sample_rate)

        await webhooks.send_audio_bytes_developer_webhook('u1', sample_rate, pcm_data)

        assert post_mock.await_count == 1
        call_args = post_mock.await_args
        assert call_args.args[0] == 'send_audio_bytes_developer_webhook'
        assert call_args.args[1] == expected_prefix
        cb.record_success.assert_called_once()
        webhooks.record_dev_webhook_success.assert_called_once_with('u1', WebhookType.audio_bytes)

    import asyncio

    asyncio.run(_run())


def test_send_audio_bytes_developer_webhook_rejects_malformed_url(monkeypatch):
    """Verify malformed or unsafe scheme URL returns early without delivery attempt."""

    async def _run():
        monkeypatch.setattr(webhooks, 'user_webhook_status_db', MagicMock(return_value=True))
        monkeypatch.setattr(webhooks, 'get_user_webhook_db', MagicMock(return_value='ftp://example.com/audio'))

        post_mock = AsyncMock()
        monkeypatch.setattr(webhooks, '_post_dev_webhook', post_mock)

        await webhooks.send_audio_bytes_developer_webhook('u1', 16000, bytearray(b'\x00\x00' * 16000))
        post_mock.assert_not_awaited()

    import asyncio

    asyncio.run(_run())
