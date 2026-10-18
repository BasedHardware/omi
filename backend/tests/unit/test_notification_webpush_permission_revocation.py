"""A web-push subscription whose permission was revoked is dead forever.

Failure-Class: FC-permanent-write-rejection-retried-forever — sibling instance
in ``backend/utils/notifications.py`` (prod [pusher] 2026-10, ``FCM send
failed: Permission denied by the third party webpush
service.(PERMISSION_DENIED)`` x28/30m). The token-removal latch
(``PERMANENT_FAILURE_CODES``) knew the FCM per-token terminal codes
(``UNREGISTERED``, ``INVALID_REGISTRATION_TOKEN``, ``NOT_FOUND``) but not the
gRPC status the FCM v1 API reports when the upstream webpush service refuses
the subscription: the browser or OS withdrew the web-push permission (or
cleared the site's data) while the token row survived in Firestore. No repeat
send can converge, so every later notification re-dialed FCM for the refused
subscription, logged the same ERROR through ``_collect_send_results``'s
non-permanent branch, and kept the token forever; the bulk pruner inherited
the same blind spot through the shared constant. ``SenderIdMismatchError``
(a token minted by another Firebase sender) reports the same status and is
equally terminal per token.

Guards proven below:
- a ``PERMISSION_DENIED`` send result removes the token through the same
  ``_collect_send_results`` latch on every send boundary — per-user sync,
  per-user async, client-displayed (chat answers), count-returning, and the
  bulk pruner — alongside ``UNREGISTERED`` in one batch and across batch
  splits; the prod ERROR line is replaced by the existing ``Invalid token
  removed`` path plus the ``Push Token Status`` ``invalidated`` event;
- the constant itself carries the new code (parsed from source so the latch
  cannot silently regress without importing firebase_admin);
- transiently-failing codes keep their retry and their ERROR line:
  ``UNAUTHENTICATED`` (auth/key problem) and ``RESOURCE_EXHAUSTED`` (the
  SDK's ``QuotaExceededError`` status) never remove a token, and neither does
  an unknown code or a failed result without an exception;
- the installed SDK maps the FCM v1 webpush refusal to
  ``firebase_admin.exceptions.PermissionDeniedError`` with
  ``code == 'PERMISSION_DENIED'`` — the exact shape ``_collect_send_results``
  inspects — proven against the real SDK package;
- message construction, token fetches, and analytics are unchanged for the
  surviving tokens on the same batch, and no token material reaches the logs
  (log_sanitizer contract).
"""

import ast
import asyncio
import logging
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest
from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _FakeMessagingException(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _FakeResponse:
    def __init__(self, success: bool, exception: Exception | None = None):
        self.success = success
        self.exception = exception


class _FakeBatchResponse:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = responses


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _constructor(**kwargs: Any) -> Any:
    return SimpleNamespace(**kwargs)


def _messaging_module() -> ModuleType:
    class Notification:
        def __init__(self, title: str, body: str):
            self.title = title
            self.body = body

    return _module(
        'firebase_admin.messaging',
        Notification=Notification,
        AndroidConfig=_constructor,
        AndroidNotification=_constructor,
        APNSConfig=_constructor,
        APNSPayload=_constructor,
        Aps=_constructor,
        ApsAlert=_constructor,
        WebpushConfig=_constructor,
        WebpushNotification=_constructor,
        WebpushFCMOptions=_constructor,
        Message=_constructor,
        send_each=MagicMock(),
    )


@contextmanager
def _loaded_notifications() -> Iterator[tuple[ModuleType, ModuleType, ModuleType]]:
    messaging = _messaging_module()
    auth = _module('firebase_admin.auth', get_user=MagicMock())
    notification_db = _module(
        'database.notifications',
        get_all_tokens=MagicMock(),
        remove_bulk_tokens=MagicMock(),
    )
    stubs = {
        'firebase_admin': _module('firebase_admin', messaging=messaging, auth=auth),
        'firebase_admin.messaging': messaging,
        'firebase_admin.auth': auth,
        'database.notifications': notification_db,
        'database.redis_db': _module(
            'database.redis_db',
            set_credit_limit_notification_sent=MagicMock(),
            has_credit_limit_notification_been_sent=MagicMock(),
            set_silent_user_notification_sent=MagicMock(),
            has_silent_user_notification_been_sent=MagicMock(),
        ),
        'database.auth': _module('database.auth', get_user_from_uid=MagicMock()),
        'utils.llm.notifications': _module(
            'utils.llm.notifications',
            generate_notification_message=MagicMock(),
            generate_credit_limit_notification=MagicMock(),
            generate_silent_user_notification=MagicMock(),
        ),
        'utils.integration_telemetry': _module(
            'utils.integration_telemetry',
            emit_posthog_event=MagicMock(),
        ),
    }

    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.notifications',
            str(BACKEND_DIR / 'utils' / 'notifications.py'),
        )
        yield notifications, notification_db, messaging


def _send_per_user(notifications, notification_db, messaging, responses, tokens) -> None:
    notification_db.get_all_tokens.return_value = list(tokens)
    messaging.send_each.return_value = _FakeBatchResponse(responses)
    notifications.send_notification('user-1', 'omi', 'hello')


# --- The fix: PERMISSION_DENIED joins the per-token removal latch ----------


def test_permission_denied_token_removed_on_per_user_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ],
            tokens=['revoked-webpush-token', 'live-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


def test_permission_denied_removed_alongside_unregistered_in_same_batch() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=False, exception=_FakeMessagingException('UNREGISTERED')),
                _FakeResponse(success=True),
            ],
            tokens=['revoked-token', 'uninstalled-token', 'live-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-token', 'uninstalled-token'])


def test_permission_denied_removed_alongside_not_found_in_same_batch() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND')),
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
            ],
            tokens=['orphaned-token', 'revoked-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['orphaned-token', 'revoked-token'])


async def test_permission_denied_token_removed_on_async_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        await notifications.send_notification_async('user-1', 'omi', 'hello')

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


async def test_permission_denied_removed_with_explicit_tokens_on_async_send() -> None:
    """Callers that pre-fetch tokens (daily summary) hit the same latch."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ]
        )

        await notifications.send_notification_async(
            'user-1', 'omi', 'hello', tokens=['revoked-webpush-token', 'live-token']
        )

        notification_db.get_all_tokens.assert_not_called()
        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


def test_permission_denied_token_removed_on_client_displayed_send() -> None:
    """Chat-answer pushes (client_displayed) share the per-user latch."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        notifications.send_client_displayed_notification('user-1', 'omi says', 'answer text', data={'id': 'm1'})

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


async def test_permission_denied_removed_with_explicit_tokens_on_async_send() -> None:
    """Callers that pre-fetch tokens (daily summary) hit the same latch."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ]
        )

        await notifications.send_notification_async(
            'user-1', 'omi', 'hello', tokens=['revoked-webpush-token', 'live-token']
        )

        notification_db.get_all_tokens.assert_not_called()
        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


async def test_permission_denied_token_removed_on_client_displayed_async_send() -> None:
    """The SSE chat boundary uses the async twin of the same latch."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        await notifications.send_client_displayed_notification_async('user-1', 'omi says', 'answer text')

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


def test_permission_denied_token_removed_on_bulk_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        asyncio.run(notifications.send_bulk_notification(['revoked-webpush-token'], 'omi', 'hello'))

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


def test_bulk_splits_batches_and_removes_permission_denied_from_second_batch() -> None:
    """501 tokens = two send batches; a dead token in the SECOND batch is still pruned.

    The fake keys off the batch size (500 vs 1), not a side_effect list: the
    two batches run concurrently, so response consumption order is not
    deterministic, but each batch's size is.
    """
    with _loaded_notifications() as (notifications, notification_db, messaging):
        dead_second_batch = 'revoked-in-second-batch'
        tokens = [f'token-{i}' for i in range(500)] + [dead_second_batch]

        def _respond_by_batch_size(messages):
            if len(messages) == 1:
                return _FakeBatchResponse(
                    [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
                )
            return _FakeBatchResponse([_FakeResponse(success=True)] * len(messages))

        messaging.send_each.side_effect = _respond_by_batch_size

        asyncio.run(notifications.send_bulk_notification(tokens, 'omi', 'hello'))

        assert messaging.send_each.call_count == 2
        notification_db.remove_bulk_tokens.assert_called_once_with([dead_second_batch])


def test_multiple_permission_denied_tokens_removed_in_one_call() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ],
            tokens=['revoked-a', 'revoked-b', 'live-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-a', 'revoked-b'])


def test_all_dead_batch_removes_every_token_and_reports_zero_success() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['dead-a', 'dead-b']
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
            ]
        )

        count = notifications.send_notification_result('user-1', 'omi', 'hello')

        assert count == 0
        notification_db.remove_bulk_tokens.assert_called_once_with(['dead-a', 'dead-b'])


def test_send_notification_result_counts_and_removes_permission_denied() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token', 'live-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ]
        )

        count = notifications.send_notification_result('user-1', 'omi', 'hello')

        assert count == 1
        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


# --- Transient shapes keep their retry and their ERROR line ----------------


def test_unauthenticated_failure_keeps_the_token() -> None:
    """Auth/key faults are project-level, not a dead token: keep retrying."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('UNAUTHENTICATED'))],
            tokens=['retry-token'],
        )

        notification_db.remove_bulk_tokens.assert_not_called()


def test_resource_exhausted_failure_keeps_the_token() -> None:
    """The SDK's QuotaExceededError carries code RESOURCE_EXHAUSTED — throttled, not dead."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('RESOURCE_EXHAUSTED'))],
            tokens=['throttled-token'],
        )

        notification_db.remove_bulk_tokens.assert_not_called()


def test_unknown_failure_code_keeps_the_token() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('SOMETHING_NEW'))],
            tokens=['mystery-token'],
        )

        notification_db.remove_bulk_tokens.assert_not_called()


def test_failed_result_without_exception_is_ignored() -> None:
    """A failed result with no exception carries no code — removal stays scoped."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=None)],
            tokens=['token-without-diagnosis'],
        )

        notification_db.remove_bulk_tokens.assert_not_called()


async def test_transient_failure_keeps_the_token_on_async_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('UNAUTHENTICATED'))]
        )

        await notifications.send_notification_async('user-1', 'omi', 'hello', tokens=['retry-token'])

        notification_db.remove_bulk_tokens.assert_not_called()


def test_transient_failure_keeps_the_token_on_client_displayed_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('RESOURCE_EXHAUSTED'))]
        )

        notifications.send_client_displayed_notification('user-1', 'omi says', 'answer text')

        notification_db.remove_bulk_tokens.assert_not_called()


def test_mixed_transient_and_dead_removes_only_the_dead() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('UNAUTHENTICATED')),
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=False, exception=_FakeMessagingException('SOMETHING_NEW')),
            ],
            tokens=['auth-blip', 'revoked-token', 'unknown-blip'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-token'])


# --- The latch constant itself ---------------------------------------------


def test_permanent_failure_codes_carry_permission_denied() -> None:
    """The latch itself carries the new code without importing firebase_admin."""
    source = (BACKEND_DIR / 'utils' / 'notifications.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'PERMANENT_FAILURE_CODES'
    )
    codes = [
        elt.value
        for elt in assignment.value.args[0].elts  # type: ignore[attr-defined]  # frozenset([...]) literal
        if isinstance(elt, ast.Constant)
    ]
    assert 'PERMISSION_DENIED' in codes, 'PERMANENT_FAILURE_CODES must latch PERMISSION_DENIED'
    for permanent in ('UNREGISTERED', 'INVALID_REGISTRATION_TOKEN', 'NOT_FOUND'):
        assert permanent in codes, f'latch lost historical code {permanent}'


def test_real_sdk_reports_permission_denied_code_for_webpush_revocation() -> None:
    """The installed SDK maps the FCM v1 webpush refusal to code PERMISSION_DENIED.

    ``_MessagingService._build_fcm_error`` only recognizes FCM-specific
    ``FcmError.errorCode`` detail entries (``UNREGISTERED`` & friends); the
    webpush service's permission refusal carries no such detail, so the SDK
    falls back to the gRPC status and builds
    ``exceptions.PermissionDeniedError`` with ``code == 'PERMISSION_DENIED'`` —
    exactly the ``result.exception.code`` value ``_collect_send_results`` reads.
    """
    try:
        from firebase_admin import _utils as real_utils
        from firebase_admin import exceptions as real_exceptions
        from firebase_admin import messaging as real_messaging
    except ImportError:
        pytest.skip('firebase_admin is not installed')

    # The requests error shape _handle_func_requests inspects: a real response
    # with the FCM v1 error body (no FcmError detail — the webpush refusal).
    requests_error = MagicMock()
    requests_error.response.status_code = 403
    requests_error.response.content = b'{"error": {"code": 403, "message": "x", "status": "PERMISSION_DENIED"}}'

    error_dict = {
        'code': 403,
        'message': 'Permission denied by the third party webpush service.',
        'details': [],
        'status': 'PERMISSION_DENIED',
    }
    assert (
        real_messaging._MessagingService._build_fcm_error(error_dict) is None
    ), 'FCM-specific detail parsing must not claim the webpush-refusal shape'
    platform_error = real_utils._handle_func_requests(requests_error, error_dict['message'], error_dict)
    assert isinstance(platform_error, real_exceptions.PermissionDeniedError)
    assert platform_error.code == 'PERMISSION_DENIED'


def test_sender_id_mismatch_sdk_error_also_carries_permission_denied_code() -> None:
    """A token minted by another Firebase sender is the same terminal shape.

    The SDK's ``SenderIdMismatchError`` subclasses
    ``exceptions.PermissionDeniedError`` with ``code == 'PERMISSION_DENIED'``;
    the latch cannot (and must not) distinguish it from the webpush refusal —
    both are permanent for this project's sends.
    """
    try:
        from firebase_admin import exceptions as real_exceptions
        from firebase_admin import messaging as real_messaging
    except ImportError:
        pytest.skip('firebase_admin is not installed')

    mismatch = real_messaging.SenderIdMismatchError('Sender ID mismatch')
    assert isinstance(mismatch, real_exceptions.PermissionDeniedError)
    assert mismatch.code == 'PERMISSION_DENIED'


# --- Log and analytics contracts -------------------------------------------


def test_permission_denied_removal_does_not_log_send_failed(caplog: pytest.LogCaptureFixture) -> None:
    """The prod ERROR signature ('FCM send failed: Permission denied ...') must not fire."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        with caplog.at_level(logging.ERROR):
            _send_per_user(
                notifications,
                notification_db,
                messaging,
                [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))],
                tokens=['revoked-webpush-token'],
            )

        assert not any('FCM send failed' in record.getMessage() for record in caplog.records)
        assert any('Invalid token removed' in record.getMessage() for record in caplog.records)


def test_transient_failure_still_logs_send_failed(caplog: pytest.LogCaptureFixture) -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        with caplog.at_level(logging.ERROR):
            _send_per_user(
                notifications,
                notification_db,
                messaging,
                [_FakeResponse(success=False, exception=_FakeMessagingException('UNAUTHENTICATED'))],
                tokens=['retry-token'],
            )

        assert any(
            'FCM send failed' in record.getMessage() for record in caplog.records
        ), 'transient failures must stay observable through the existing ERROR line'


def test_removal_log_line_omits_token_value(caplog: pytest.LogCaptureFixture) -> None:
    """No token material may reach the logs (log_sanitizer contract)."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        with caplog.at_level(logging.ERROR):
            _send_per_user(
                notifications,
                notification_db,
                messaging,
                [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))],
                tokens=['revoked-S3cret-webpush-token-value'],
            )

        assert any('PERMISSION_DENIED' in record.getMessage() for record in caplog.records)
        assert all('S3cret' not in record.getMessage() for record in caplog.records)


def test_bulk_removal_does_not_log_send_failed(caplog: pytest.LogCaptureFixture) -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )
        with caplog.at_level(logging.ERROR):
            asyncio.run(notifications.send_bulk_notification(['revoked-webpush-token'], 'omi', 'hello'))

        assert not any('FCM send failed' in record.getMessage() for record in caplog.records)


def test_invalidated_analytics_emitted_for_permission_denied_removal() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        with patch.object(notifications, 'emit_posthog_event') as emit:
            notifications.send_notification('user-1', 'omi', 'hello')

        emit.assert_called_once_with('user-1', 'Push Token Status', {'status': 'invalidated', 'invalidated_count': 1})


def test_analytics_failure_does_not_block_removal_or_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        with patch.object(notifications, 'emit_posthog_event') as emit:
            emit.side_effect = RuntimeError('posthog down')
            count = notifications.send_notification_result('user-1', 'omi', 'hello')

        assert count == 0
        notification_db.remove_bulk_tokens.assert_called_once_with(['revoked-webpush-token'])


# --- Unchanged contracts the fix must not disturb --------------------------


def test_clean_send_does_not_remove_any_token() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=True), _FakeResponse(success=True)],
            tokens=['live-a', 'live-b'],
        )

        notification_db.remove_bulk_tokens.assert_not_called()


def test_no_tokens_skips_send_and_removal() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = []

        notifications.send_notification('user-1', 'omi', 'hello')

        messaging.send_each.assert_not_called()
        notification_db.remove_bulk_tokens.assert_not_called()


def test_removal_preserves_batch_token_order() -> None:
    """Collector output keeps the request's token order — the caller dedupes nothing."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        tokens = ['t1', 't2', 't3', 't4']
        notification_db.get_all_tokens.return_value = list(tokens)
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=True),
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
                _FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND')),
            ]
        )

        count = notifications.send_notification_result('user-1', 'omi', 'hello')

        assert count == 2
        notification_db.remove_bulk_tokens.assert_called_once_with(['t2', 't4'])


def test_success_count_ignores_removed_permission_denied_token() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-token', 'live-a', 'live-b']
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
                _FakeResponse(success=True),
            ]
        )

        count = notifications.send_notification_result('user-1', 'omi', 'hello')

        assert count == 2


def test_message_construction_is_identical_for_a_batch_with_a_dead_token() -> None:
    """The fix changes the post-send bookkeeping only, never the outgoing payloads."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        tokens = ['revoked-webpush-token', 'live-token']
        notification_db.get_all_tokens.return_value = list(tokens)
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED')),
                _FakeResponse(success=True),
            ]
        )

        notifications.send_notification('user-1', 'omi says', 'hello there')

        sent_messages = messaging.send_each.call_args.args[0]
        assert len(sent_messages) == 2
        assert all(message.token == token for message, token in zip(sent_messages, tokens))


def test_get_all_tokens_fetched_once_per_send() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['revoked-webpush-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))]
        )

        notifications.send_notification('user-1', 'omi', 'hello')

        notification_db.get_all_tokens.assert_called_once_with('user-1')


def test_unregistered_still_removed() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('UNREGISTERED'))],
            tokens=['uninstalled-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['uninstalled-token'])


def test_invalid_registration_token_still_removed() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('INVALID_REGISTRATION_TOKEN'))],
            tokens=['malformed-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['malformed-token'])


def test_not_found_still_removed() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        _send_per_user(
            notifications,
            notification_db,
            messaging,
            [_FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND'))],
            tokens=['orphaned-token'],
        )

        notification_db.remove_bulk_tokens.assert_called_once_with(['orphaned-token'])


def test_bulk_mixed_dead_tokens_across_batches_are_aggregated() -> None:
    """Dead tokens in BOTH bulk batches land in one removal call."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        dead_first = 'revoked-in-first-batch'
        dead_second = 'revoked-in-second-batch'
        tokens = [dead_first] + [f'token-{i}' for i in range(499)] + [dead_second]

        def _respond_by_batch_size(messages):
            dead = dead_second if len(messages) == 1 else dead_first
            responses = [_FakeResponse(success=True)] * len(messages)
            responses[0] = _FakeResponse(success=False, exception=_FakeMessagingException('PERMISSION_DENIED'))
            assert messages[0].token == dead
            return _FakeBatchResponse(responses)

        messaging.send_each.side_effect = _respond_by_batch_size

        asyncio.run(notifications.send_bulk_notification(tokens, 'omi', 'hello'))

        notification_db.remove_bulk_tokens.assert_called_once_with([dead_first, dead_second])
