"""UnifiedPush send channel (ADR-0011): payload shape, addressing, dead-endpoint cleanup, routing.

The channel POSTs a neutral PushMessage to each registered endpoint and treats HTTP 404/410 as a
permanently-dead endpoint (parity with the FCM invalid-token taxonomy). A final routing test proves
that with PUSH_NOTIFICATION_BACKEND=unifiedpush the public sender reaches this channel and never
touches Firebase.
"""

import asyncio
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

from database.notifications import UnifiedPushEndpoint  # noqa: E402
from testing.import_isolation import load_module_fresh, stub_modules  # noqa: E402
from utils.push import unifiedpush as up  # noqa: E402
from utils.push.base import PushMessage  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _ep(url: str, *, p256dh=None, auth=None) -> UnifiedPushEndpoint:
    return UnifiedPushEndpoint(url=url, p256dh=p256dh, auth=auth)


def test_render_payload_visible_carries_notification():
    payload = up.render_payload(PushMessage(tag='t', title='omi', body='hi', data={'type': 'x'}, priority='high'))
    assert payload == {
        'tag': 't',
        'priority': 'high',
        'is_background': False,
        'data': {'type': 'x'},
        'notification': {'title': 'omi', 'body': 'hi'},
    }


def test_render_payload_data_only_omits_notification():
    payload = up.render_payload(PushMessage(tag='t', data={'type': 'action_item_reminder'}, is_background=True))
    assert 'notification' not in payload
    assert payload['is_background'] is True
    assert payload['data'] == {'type': 'action_item_reminder'}


def test_target_url_verbatim_without_internal_base(monkeypatch):
    monkeypatch.delenv('UNIFIEDPUSH_INTERNAL_BASE_URL', raising=False)
    assert up._target_url('http://10.0.2.2:8090/topicA?up=1') == 'http://10.0.2.2:8090/topicA?up=1'


def test_target_url_rewrites_host_via_internal_base(monkeypatch):
    monkeypatch.setenv('UNIFIEDPUSH_INTERNAL_BASE_URL', 'http://ntfy:80')
    # The phone-facing host is dropped; only the path+query survive onto the internal base.
    assert up._target_url('http://10.0.2.2:8090/topicA?up=1') == 'http://ntfy:80/topicA?up=1'


def _endpoints(monkeypatch, values):
    # Accept URL strings (plaintext, keyless) or UnifiedPushEndpoint records.
    records = [v if isinstance(v, UnifiedPushEndpoint) else _ep(v) for v in values]
    monkeypatch.setattr(up.notification_db, 'get_all_endpoints', lambda _uid: list(records))
    removed = []
    monkeypatch.setattr(up.notification_db, 'remove_bulk_endpoints', lambda eps: removed.append(list(eps)))
    return removed


def test_send_to_user_counts_success_and_drops_dead(monkeypatch):
    removed = _endpoints(monkeypatch, ['http://ntfy/live?up=1', 'http://ntfy/dead?up=1', 'http://ntfy/flaky?up=1'])
    statuses = {'http://ntfy/live?up=1': 200, 'http://ntfy/dead?up=1': 410, 'http://ntfy/flaky?up=1': 503}
    monkeypatch.setattr(up, '_post_sync', lambda url, _body, _headers: statuses[url])

    sent = up.send_to_user('u1', PushMessage(tag='t', title='omi', body='hi'))

    assert sent == 1  # only the 2xx endpoint
    assert removed == [['http://ntfy/dead?up=1']]  # 410 dropped; 503 kept as transient


def test_send_to_user_network_error_keeps_endpoint(monkeypatch):
    removed = _endpoints(monkeypatch, ['http://ntfy/x?up=1'])
    monkeypatch.setattr(up, '_post_sync', lambda _url, _body, _headers: None)  # network error → None

    assert up.send_to_user('u1', PushMessage(tag='t', title='omi', body='hi')) == 0
    assert removed == []  # transient, not dropped


def test_send_to_user_no_endpoints_is_noop(monkeypatch):
    _endpoints(monkeypatch, [])
    called = []
    monkeypatch.setattr(up, '_post_sync', lambda url, body, headers: called.append(url) or 200)
    assert up.send_to_user('u1', PushMessage(tag='t', title='omi', body='hi')) == 0
    assert called == []


def test_keyless_endpoint_posts_plaintext_json(monkeypatch):
    _endpoints(monkeypatch, ['http://ntfy/plain?up=1'])
    captured = {}
    monkeypatch.setattr(up, '_post_sync', lambda url, body, headers: captured.update(url=url, body=body, headers=headers) or 200)

    up.send_to_user('u1', PushMessage(tag='t', title='omi', body='hi', data={'type': 'x'}))

    assert captured['headers']['Content-Type'] == 'application/json'
    assert 'Content-Encoding' not in captured['headers']
    assert json.loads(captured['body'])['notification'] == {'title': 'omi', 'body': 'hi'}


def test_keyed_endpoint_posts_hex_armored_encrypted_body(monkeypatch):
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import http_ece

    private_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    ).rstrip(b'=').decode()
    auth_bytes = os.urandom(16)
    auth = base64.urlsafe_b64encode(auth_bytes).rstrip(b'=').decode()

    _endpoints(monkeypatch, [_ep('http://ntfy/enc?up=1', p256dh=p256dh, auth=auth)])
    captured = {}
    monkeypatch.setattr(up, '_post_sync', lambda url, body, headers: captured.update(body=body, headers=headers) or 200)

    up.send_to_user('u1', PushMessage(tag='t', title='omi', body='secret', data={'type': 'merge_completed'}))

    # ntfy is a text transport: the body is a lowercase-hex UTF-8 string, not raw binary.
    assert captured['headers']['Content-Type'] == 'text/plain'
    assert 'Content-Encoding' not in captured['headers']
    hex_text = captured['body'].decode('ascii')
    assert all(c in '0123456789abcdef' for c in hex_text)
    assert b'secret' not in captured['body']  # confidential on the wire
    # The app hex-decodes then decrypts (RFC 8291) back to the exact JSON payload.
    ciphertext = bytes.fromhex(hex_text)
    decrypted = http_ece.decrypt(ciphertext, private_key=private_key, auth_secret=auth_bytes, version='aes128gcm')
    assert json.loads(decrypted)['notification'] == {'title': 'omi', 'body': 'secret'}


def test_send_to_user_async_drops_dead(monkeypatch):
    removed = _endpoints(monkeypatch, ['http://ntfy/live?up=1', 'http://ntfy/dead?up=1'])
    statuses = {'http://ntfy/live?up=1': 202, 'http://ntfy/dead?up=1': 404}

    async def _post(url, _body, _headers):
        return statuses[url]

    monkeypatch.setattr(up, '_post_async', _post)

    sent = asyncio.run(up.send_to_user_async('u1', PushMessage(tag='t', title='omi', body='hi')))
    assert sent == 1
    assert removed == [['http://ntfy/dead?up=1']]


def test_send_bulk_posts_all_and_drops_dead(monkeypatch):
    removed = []
    monkeypatch.setattr(up.notification_db, 'remove_bulk_endpoints', lambda eps: removed.append(list(eps)))
    statuses = {'http://ntfy/a?up=1': 200, 'http://ntfy/b?up=1': 410}

    async def _post(url, _body, _headers):
        return statuses[url]

    monkeypatch.setattr(up, '_post_async', _post)
    asyncio.run(
        up.send_bulk([_ep('http://ntfy/a?up=1'), _ep('http://ntfy/b?up=1')], PushMessage(tag='t', title='omi', body='hi'))
    )
    assert removed == [['http://ntfy/b?up=1']]  # 410 dropped


def test_send_bulk_empty_is_noop(monkeypatch):
    posted = []

    async def _post(url, _body, _headers):
        posted.append(url)
        return 200

    monkeypatch.setattr(up, '_post_async', _post)
    asyncio.run(up.send_bulk([], PushMessage(tag='t', title='x', body='y')))
    assert posted == []


# --- routing: public sender -> unifiedpush channel, never Firebase --------------------------------


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@contextmanager
def _loaded_notifications() -> Iterator[ModuleType]:
    def _unexpected_send(_messages: Any) -> Any:
        raise AssertionError('messaging.send_each must not be called in unifiedpush mode')

    messaging = _module(
        'firebase_admin.messaging',
        Notification=lambda title, body: SimpleNamespace(title=title, body=body),
        AndroidConfig=lambda **k: SimpleNamespace(**k),
        AndroidNotification=lambda **k: SimpleNamespace(**k),
        APNSConfig=lambda **k: SimpleNamespace(**k),
        APNSPayload=lambda **k: SimpleNamespace(**k),
        Aps=lambda **k: SimpleNamespace(**k),
        WebpushConfig=lambda **k: SimpleNamespace(**k),
        WebpushNotification=lambda **k: SimpleNamespace(**k),
        WebpushFCMOptions=lambda **k: SimpleNamespace(**k),
        Message=lambda **k: SimpleNamespace(**k),
        send_each=_unexpected_send,
    )
    auth = _module('firebase_admin.auth', get_user=lambda _uid: SimpleNamespace(display_name='Ada'))
    stubs = {
        'firebase_admin': _module('firebase_admin', messaging=messaging, auth=auth),
        'firebase_admin.messaging': messaging,
        'firebase_admin.auth': auth,
        'database.redis_db': _module(
            'database.redis_db',
            set_credit_limit_notification_sent=lambda _uid: None,
            has_credit_limit_notification_been_sent=lambda _uid: False,
            set_silent_user_notification_sent=lambda _uid: None,
            has_silent_user_notification_been_sent=lambda _uid: False,
        ),
        'database.auth': _module('database.auth', get_user_from_uid=lambda _uid: None),
        'utils.llm.notifications': _module(
            'utils.llm.notifications',
            generate_notification_message=lambda *_a, **_k: ('t', 'b'),
            generate_credit_limit_notification=lambda *_a, **_k: ('t', 'b'),
            generate_silent_user_notification=lambda *_a, **_k: ('t', 'b'),
        ),
    }
    with stub_modules(stubs):
        notifications = load_module_fresh('utils.notifications', str(BACKEND_DIR / 'utils' / 'notifications.py'))
        yield notifications


def test_send_notification_routes_to_unifiedpush(monkeypatch):
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    monkeypatch.setattr(up.notification_db, 'get_all_endpoints', lambda _uid: [_ep('http://ntfy/t?up=1')])
    posted = []
    monkeypatch.setattr(up, '_post_sync', lambda url, body, _headers: posted.append((url, json.loads(body))) or 200)

    with _loaded_notifications() as notifications:
        notifications.send_notification('user-1', 'omi', 'hello')

    assert len(posted) == 1
    url, payload = posted[0]
    assert url == 'http://ntfy/t?up=1'
    assert payload['notification'] == {'title': 'omi', 'body': 'hello'}


def test_send_bulk_notification_routes_to_unifiedpush(monkeypatch):
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')
    captured = {}

    async def _spy(endpoints, msg):
        captured['endpoints'] = list(endpoints)
        captured['title'] = msg.title

    monkeypatch.setattr(up, 'send_bulk', _spy)

    with _loaded_notifications() as notifications:
        # Bare URL strings (the pre-key-set recipient shape) are normalized to UnifiedPushEndpoint
        # records before reaching send_bulk, so bulk delivery is resilient to caller shape.
        asyncio.run(notifications.send_bulk_notification(['http://ntfy/a?up=1', 'http://ntfy/b?up=1'], 'omi', 'hi'))

    assert captured['endpoints'] == [_ep('http://ntfy/a?up=1'), _ep('http://ntfy/b?up=1')]
    assert captured['title'] == 'omi'


def test_resolve_push_backend_normalizes_whitespace_and_case(monkeypatch):
    # The flag is read at call time; whitespace/case around a valid value must normalize, not coerce.
    from utils.push.selector import resolve_push_backend

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', '  UnifiedPush\n')
    assert resolve_push_backend() == 'unifiedpush'


def test_resolve_push_backend_coerces_unknown_to_fcm(monkeypatch):
    # A non-blank typo is coerced to the FCM default (logged), never raised — a typo must not take
    # push delivery down.
    from utils.push.selector import resolve_push_backend

    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'bogus')
    assert resolve_push_backend() == 'fcm'
