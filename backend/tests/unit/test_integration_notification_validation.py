"""POST /v1/integrations/notification must return 400 (not 500) when message is missing.

It read data['message'] via direct subscript, so a body without message raised KeyError -> 500.
routers/notifications.py has a heavy import graph, so we import it under a stub finder.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


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
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from routers import notifications as notif_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)

from fastapi import HTTPException  # noqa: E402
from models.other import SendAppNotificationRequest  # noqa: E402


def test_missing_message_returns_400():
    with pytest.raises(HTTPException) as e:
        notif_mod.send_app_notification_to_user(
            request=MagicMock(),
            data=SendAppNotificationRequest(aid='app1', message='', uid='uid1'),
            authorization=None,
        )
    assert e.value.status_code == 400


class _FakeRedis:
    """Minimal in-memory redis with integer counter semantics for check_rate_limit."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)  # None when absent, like redis

    def setex(self, key, ttl, value):
        self.store[key] = int(value)

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]


def test_check_rate_limit_allows_full_hourly_quota():
    # Regression: the first request seeded the counter to 1 AND then incremented it, so it consumed two
    # tokens -> only MAX-1 notifications were ever allowed and the remaining header was off by one.
    # routers/integration.py::check_rate_limit is a byte-identical twin fixed the same way.
    fake = _FakeRedis()
    max_n = notif_mod.MAX_NOTIFICATIONS_PER_HOUR
    with patch.object(notif_mod, 'redis_client', fake):
        results = [notif_mod.check_rate_limit('app1', 'uid1') for _ in range(max_n + 1)]

    allowed = [r[0] for r in results]
    assert allowed[:max_n] == [True] * max_n  # full quota deliverable
    assert allowed[max_n] is False  # only the (max_n + 1)th request is throttled
    assert results[0][1] == max_n - 1  # first send reports the full remaining quota, not one short


# --- POST /v1/notification: campaign attribution convention (#12645) -------------
#
# `data.data` is forwarded to FCM untouched, so campaign_id is a convention rather
# than transport. A campaign send that omits it is indistinguishable afterwards
# from an untracked send, and the gap only surfaces once the campaign is over.


def test_campaign_send_without_campaign_id_returns_400(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'admin-key')

    with pytest.raises(HTTPException) as e:
        notif_mod.send_notification_to_user(
            data={'uid': 'uid1', 'title': 't', 'body': 'b', 'data': {'kind': 'campaign'}},
            secret_key='admin-key',
        )

    assert e.value.status_code == 400
    assert 'campaign_id' in e.value.detail


def test_campaign_send_with_campaign_id_forwards_the_payload_untouched(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'admin-key')
    payload = {'kind': 'campaign', 'campaign_id': 'macos-push-2026-09-02', 'navigate_to': '/chat'}

    with patch.object(notif_mod, 'send_notification') as send:
        result = notif_mod.send_notification_to_user(
            data={'uid': 'uid1', 'title': 't', 'body': 'b', 'data': payload},
            secret_key='admin-key',
        )

    assert result == {'status': 'Ok'}
    send.assert_called_once_with('uid1', 't', 'b', payload)


def test_non_campaign_send_does_not_require_a_campaign_id(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', 'admin-key')

    with patch.object(notif_mod, 'send_notification') as send:
        result = notif_mod.send_notification_to_user(
            data={'uid': 'uid1', 'title': 't', 'body': 'b', 'data': {'navigate_to': '/chat'}},
            secret_key='admin-key',
        )

    assert result == {'status': 'Ok'}
    send.assert_called_once_with('uid1', 't', 'b', {'navigate_to': '/chat'})


def test_campaign_send_with_a_null_data_body_does_not_500(monkeypatch):
    # "data": null used to reach send_notification, which tolerates it. The new
    # campaign gate must not turn that into an AttributeError -> HTTP 500.
    monkeypatch.setenv('ADMIN_KEY', 'admin-key')

    with patch.object(notif_mod, 'send_notification') as send:
        result = notif_mod.send_notification_to_user(
            data={'uid': 'uid1', 'title': 't', 'body': 'b', 'data': None},
            secret_key='admin-key',
        )

    assert result == {'status': 'Ok'}
    send.assert_called_once_with('uid1', 't', 'b', {})


@pytest.mark.parametrize(
    'campaign_id',
    [
        'has spaces',
        'has\nnewline',
        'hash#char',
        '   ',
        'x' * 65,
    ],
)
def test_campaign_id_the_download_route_would_reject_is_refused_at_send(monkeypatch, campaign_id):
    # The download CTA constrains campaign_id. Accepting one here that it rejects
    # would let the send succeed and the CTA 400, losing the attribution outright.
    monkeypatch.setenv('ADMIN_KEY', 'admin-key')

    with pytest.raises(HTTPException) as e:
        notif_mod.send_notification_to_user(
            data={
                'uid': 'uid1',
                'title': 't',
                'body': 'b',
                'data': {'kind': 'campaign', 'campaign_id': campaign_id},
            },
            secret_key='admin-key',
        )

    assert e.value.status_code == 400
    assert 'campaign_id' in e.value.detail


def test_sender_and_download_route_share_one_campaign_id_rule():
    # Both ends must read the same constants, not two literals that can drift: a
    # sender that accepts what the CTA rejects loses the attribution silently.
    import campaign_attribution

    assert notif_mod.CAMPAIGN_ID_PATTERN is campaign_attribution.CAMPAIGN_ID_PATTERN
    assert notif_mod.CAMPAIGN_ID_MAX_LENGTH is campaign_attribution.CAMPAIGN_ID_MAX_LENGTH
