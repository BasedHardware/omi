"""Implementation of the capture sinks. See the package docstring for the choke points."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
from pathlib import Path
import threading
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlsplit

from testing.pipeline_lab.stack.io import append_jsonl, iso, parse_time

_SCOPE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar('pipeline_lab_scope', default=None)
# Fallback for threads the product starts without copying contextvars. The chain
# driver runs one conversation at a time on the ordered path, so this is exact
# there; under fan-out it is best effort and rows say so.
_FALLBACK: dict[str, Any] = {}
_FALLBACK_LOCK = threading.Lock()


@contextmanager
def capture_scope(conversation_id: str | None, stage: str) -> Iterator[None]:
    scope = {'conversation_id': conversation_id, 'stage': stage}
    token = _SCOPE.set(scope)
    with _FALLBACK_LOCK:
        previous = dict(_FALLBACK)
        _FALLBACK.clear()
        _FALLBACK.update(scope)
    try:
        yield
    finally:
        _SCOPE.reset(token)
        with _FALLBACK_LOCK:
            _FALLBACK.clear()
            _FALLBACK.update(previous)


def current_scope() -> dict[str, Any]:
    scope = _SCOPE.get()
    if scope is not None:
        return {**scope, 'scope_source': 'context'}
    with _FALLBACK_LOCK:
        if _FALLBACK:
            return {**_FALLBACK, 'scope_source': 'fallback'}
    return {'conversation_id': None, 'stage': None, 'scope_source': 'none'}


# Headers the lab adds to every request bound for the lab LLM proxy, so the proxy's
# call log can attribute each call (DESIGN llm_calls.jsonl: stage, conversation_id).
# Contract with lane core's llm_proxy; requests to any other host are never tagged.
SCOPE_CONVERSATION_HEADER = 'X-Pipeline-Lab-Conversation'
SCOPE_STAGE_HEADER = 'X-Pipeline-Lab-Stage'


def tag_request(request: Any) -> None:
    scope = current_scope()
    headers = getattr(request, 'headers', None)
    if headers is None:
        return
    if scope.get('conversation_id'):
        headers[SCOPE_CONVERSATION_HEADER] = str(scope['conversation_id'])
    if scope.get('stage'):
        headers[SCOPE_STAGE_HEADER] = str(scope['stage'])


_SKIP_CALLER_MODULES = (
    'testing.pipeline_lab',
    'firebase_admin',
    'unittest.mock',
    'contextlib',
    'concurrent',
    'threading',
)


def _caller(depth: int = 3) -> str:
    """The first product frame above the sink (``module:function``)."""
    frame = inspect.currentframe()
    try:
        for _ in range(depth):
            if frame is None:
                break
            frame = frame.f_back
        while frame is not None:
            module = frame.f_globals.get('__name__', '')
            if not module.startswith(_SKIP_CALLER_MODULES) and module != __name__:
                return f'{module}:{frame.f_code.co_name}'
            frame = frame.f_back
        return 'unknown'
    finally:
        del frame


@dataclass
class _Response:
    success: bool = True
    exception: Any = None
    message_id: str = ''


@dataclass
class _BatchResponse:
    responses: list[_Response]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.responses if r.success)

    @property
    def failure_count(self) -> int:
        return len(self.responses) - self.success_count


def _attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def decode_message(message: Any) -> dict[str, Any]:
    """Pull the user-visible parts out of a ``messaging.Message`` (or a dict stand-in)."""
    notification = _attr(message, 'notification')
    data = dict(_attr(message, 'data') or {})
    apns = _attr(message, 'apns')
    payload = _attr(apns, 'payload')
    aps = _attr(payload, 'aps')
    alert = _attr(aps, 'alert')
    title = _attr(notification, 'title') or _attr(alert, 'title') or data.get('title')
    body = _attr(notification, 'body') or _attr(alert, 'body') or data.get('body')
    content_available = bool(_attr(aps, 'content_available'))
    kind = 'alert' if notification is not None else ('background' if content_available else 'data')
    fire_at = None
    for key in ('due_at', 'fire_at', 'scheduled_at', 'reminder_at'):
        if data.get(key):
            fire_at = data[key]
            break
    return {
        'title': title,
        'body': body,
        'kind': kind,
        'data_type': data.get('type') or data.get('notification_type') or data.get('action'),
        'data': data,
        'fire_at': fire_at,
        'token_class': 'synthetic' if str(_attr(message, 'token') or '').startswith('pipeline-lab-') else 'other',
    }


@dataclass
class CaptureSinks:
    run_dir: Path | None = None
    clock: Callable[[], datetime] | None = None
    allowed_hosts: frozenset[str] = frozenset({'127.0.0.1', 'localhost', '::1'})
    allowed_ports: frozenset[int] = frozenset()
    proxy_url: str | None = None
    notifications: list[dict[str, Any]] = field(default_factory=list)
    egress: list[dict[str, Any]] = field(default_factory=list)
    telemetry: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self) -> datetime:
        return self.clock() if self.clock is not None else datetime.now(timezone.utc)

    def _write(self, name: str, row: dict[str, Any]) -> None:
        if self.run_dir is not None:
            append_jsonl(self.run_dir / name, row)

    # -- FCM -----------------------------------------------------------------
    def record_messages(self, messages: list[Any], *, api: str) -> _BatchResponse:
        at = self._now()
        scope = current_scope()
        caller = _caller()
        responses = []
        for index, message in enumerate(messages):
            decoded = decode_message(message)
            fire_at = parse_time(decoded['fire_at']) or at
            row = {
                'at': iso(at),
                'fire_at': iso(fire_at),
                'title': decoded['title'],
                'body': decoded['body'],
                'trigger': scope.get('stage') or caller,
                'caller': caller,
                'conversation_id': scope.get('conversation_id'),
                'scope_source': scope.get('scope_source'),
                'kind': decoded['kind'],
                'data_type': decoded['data_type'],
                'data': decoded['data'],
                'token_class': decoded['token_class'],
                'api': api,
            }
            with self._lock:
                self.notifications.append(row)
            self._write('notifications.jsonl', row)
            responses.append(_Response(True, None, f'pipeline-lab-{len(self.notifications)}-{index}'))
        return _BatchResponse(responses)

    def _install_fcm(self, stack: ExitStack) -> None:
        from unittest.mock import patch

        from firebase_admin import messaging

        def send_each(messages, dry_run=False, app=None):
            return self.record_messages(list(messages), api='send_each')

        def send(message, dry_run=False, app=None):
            return self.record_messages([message], api='send').responses[0].message_id

        def send_each_for_multicast(multicast, dry_run=False, app=None):
            tokens = list(_attr(multicast, 'tokens') or [])
            fake = [
                {
                    'token': token,
                    'notification': _attr(multicast, 'notification'),
                    'data': _attr(multicast, 'data'),
                    'apns': _attr(multicast, 'apns'),
                }
                for token in tokens
            ]
            return self.record_messages(fake, api='send_each_for_multicast')

        for name, replacement in (
            ('send_each', send_each),
            ('send', send),
            ('send_each_for_multicast', send_each_for_multicast),
            ('send_multicast', send_each_for_multicast),
            ('send_all', send_each),
        ):
            if hasattr(messaging, name):
                stack.enter_context(patch.object(messaging, name, replacement))

    # -- HTTP egress ---------------------------------------------------------
    def host_allowed(self, url: str) -> bool:
        parts = urlsplit(str(url))
        host = (parts.hostname or '').lower()
        if host not in self.allowed_hosts and not host.startswith('127.'):
            return False
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        return not self.allowed_ports or port in self.allowed_ports

    def is_proxy(self, url: str) -> bool:
        if not self.proxy_url:
            return False
        a, b = urlsplit(str(url)), urlsplit(self.proxy_url)
        return (a.hostname, a.port) == (b.hostname, b.port)

    def record_egress(self, channel: str, method: str, url: str, **detail: Any) -> dict[str, Any]:
        parts = urlsplit(str(url))
        scope = current_scope()
        row = {
            'at': iso(self._now()),
            'channel': channel,
            'method': method,
            # Host and path only: query strings can carry uids or secrets.
            'destination': f'{parts.scheme}://{parts.hostname}{parts.path}',
            'conversation_id': scope.get('conversation_id'),
            'stage': scope.get('stage'),
            'caller': _caller(),
            **detail,
        }
        with self._lock:
            self.egress.append(row)
        self._write('sinks_egress.jsonl', row)
        return row

    def _install_http(self, stack: ExitStack) -> None:
        from unittest.mock import patch

        import httpx

        original_async = httpx.AsyncClient.send
        original_sync = httpx.Client.send
        sinks = self

        async def async_send(client, request, *args, **kwargs):
            if sinks.host_allowed(str(request.url)):
                if sinks.is_proxy(str(request.url)):
                    tag_request(request)
                return await original_async(client, request, *args, **kwargs)
            sinks.record_egress('httpx', request.method, str(request.url))
            return httpx.Response(200, json={}, request=request)

        def sync_send(client, request, *args, **kwargs):
            if sinks.host_allowed(str(request.url)):
                if sinks.is_proxy(str(request.url)):
                    tag_request(request)
                return original_sync(client, request, *args, **kwargs)
            sinks.record_egress('httpx', request.method, str(request.url))
            return httpx.Response(200, json={}, request=request)

        stack.enter_context(patch.object(httpx.AsyncClient, 'send', async_send))
        stack.enter_context(patch.object(httpx.Client, 'send', sync_send))
        try:
            import requests
        except ImportError:  # pragma: no cover
            return
        original_requests = requests.Session.send

        def requests_send(session, request, **kwargs):
            if sinks.host_allowed(request.url):
                if sinks.is_proxy(request.url):
                    tag_request(request)
                return original_requests(session, request, **kwargs)
            sinks.record_egress('requests', request.method, request.url)
            response = requests.Response()
            response.status_code = 200
            response._content = b'{}'
            response.url = request.url
            response.request = request
            return response

        stack.enter_context(patch.object(requests.Session, 'send', requests_send))

    # -- named product leaves ------------------------------------------------
    def _install_leaves(self, stack: ExitStack) -> None:
        import httpx

        from testing.pipeline_lab.stack.patching import replace_attribute_everywhere

        sinks = self

        async def post_dev_webhook(webhook_name, webhook_url, *args, **kwargs):
            sinks.record_egress('webhook', 'POST', webhook_url, webhook=webhook_name)
            return httpx.Response(200, json={})

        async def sync_to_cloud_service(uid, app_key, integration, action_item, *args, **kwargs):
            sinks.record_egress(
                'task_sync', 'POST', f'https://{app_key}.task-sync.invalid/', action_item_id=action_item.get('id')
            )
            return {'synced': True, 'platform': app_key, 'reason': 'pipeline_lab_captured'}

        def emit_product_event(*args, **kwargs):
            event = kwargs.get('event') if 'event' in kwargs else (args[1] if len(args) > 1 else None)
            row = {'at': iso(sinks._now()), 'event': event, **{k: v for k, v in current_scope().items()}}
            with sinks._lock:
                sinks.telemetry.append(row)
            sinks._write('sinks_telemetry.jsonl', row)
            return None

        replace_attribute_everywhere(stack, 'utils.webhooks', '_post_dev_webhook', post_dev_webhook)
        replace_attribute_everywhere(stack, 'utils.task_sync', '_sync_to_cloud_service', sync_to_cloud_service)
        replace_attribute_everywhere(stack, 'utils.product_telemetry', 'emit_product_event', emit_product_event)

    def install(self, stack: ExitStack, *, fcm: bool = True, http: bool = True, leaves: bool = True) -> 'CaptureSinks':
        if fcm:
            self._install_fcm(stack)
        if http:
            self._install_http(stack)
        if leaves:
            self._install_leaves(stack)
        return self

    def notifications_for(self, conversation_id: str | None) -> list[dict[str, Any]]:
        with self._lock:
            return [row for row in self.notifications if row.get('conversation_id') == conversation_id]
