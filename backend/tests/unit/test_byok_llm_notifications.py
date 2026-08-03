"""BYOK LLM error notifications (ADR-0011): source gating, dedupe lock, delivery-confirmation.

Since the transport migration, BYOK delivery is owned by the shared push channel
(``utils.notifications.send_user_notification``), which selects fcm / unifiedpush / disabled and
handles device fan-out + invalid-address cleanup. These tests assert only what byok_errors still
owns: notify only on an actionable BYOK error, deduplicate via the lock, and release the lock when
nothing was delivered (so the next error retries). Batching and dead-address cleanup are the
channel's concern and are covered by test_unifiedpush_channel / test_notification_token_cleanup.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# byok_errors imports send_user_notification from utils.notifications at load. Stub the module so the
# test stays hermetic (no real notifications/firebase/db chain); behaviour is driven per-test by
# patching byok_errors.send_user_notification.
if 'utils.notifications' not in sys.modules:
    _notif_stub = types.ModuleType('utils.notifications')
    _notif_stub.send_user_notification = MagicMock(return_value=0)
    sys.modules['utils.notifications'] = _notif_stub


class _HTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def _quota_error() -> _HTTPError:
    return _HTTPError('insufficient_quota', 429)


@patch('utils.llm.byok_errors.send_user_notification', return_value=1)
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_notifies_actionable_byok_error(mock_get_key, mock_get_uid, mock_lock, mock_send):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    mock_send.assert_called_once()
    args = mock_send.call_args.args
    assert args[0] == 'user-1'
    assert args[1] == 'omi'
    assert args[3] == {'type': 'byok_llm_error', 'provider': 'openai', 'reason': 'quota'}


@patch('utils.llm.byok_errors.send_user_notification', return_value=1)
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=False)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_deduplicates_recent_notification(mock_get_key, mock_get_uid, mock_lock, mock_send):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    mock_send.assert_not_called()


@patch('utils.llm.byok_errors.send_user_notification', return_value=1)
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value=None)
def test_does_not_notify_platform_error(mock_get_key, mock_get_uid, mock_lock, mock_send):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_not_called()
    mock_send.assert_not_called()


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.send_user_notification', return_value=2)
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_keeps_lock_when_delivered(mock_get_key, mock_get_uid, mock_lock, mock_send, mock_release):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    # At least one device was reached — the dedupe lock must be kept (not released).
    mock_release.assert_not_called()


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.send_user_notification', return_value=0)
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_releases_lock_when_nothing_delivered(mock_get_key, mock_get_uid, mock_lock, mock_send, mock_release):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    # No device received it (no endpoints, disabled backend, all-transient) — release for retry.
    mock_release.assert_called_once_with('user-1', 'openai', 'quota')


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.send_user_notification', side_effect=RuntimeError('transport down'))
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_releases_lock_when_send_raises(mock_get_key, mock_get_uid, mock_lock, mock_send, mock_release):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_quota_error(), 'openai', feature='memories', model='gpt-test')

    # The send raised, so nothing was delivered: the lock must be released for retry.
    mock_release.assert_called_once_with('user-1', 'openai', 'quota')


@pytest.mark.parametrize(
    'error, expected_reason, body_fragment',
    [
        (_HTTPError('insufficient_quota', 429), 'quota', 'out of quota'),
        (_HTTPError('denied', 403), 'permission', 'denied access'),
        (_HTTPError('bad key', 401), 'invalid', 'was rejected'),
    ],
)
def test_reason_maps_to_body(error, expected_reason, body_fragment):
    with patch('utils.llm.byok_errors.send_user_notification', return_value=1) as mock_send, patch(
        'utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True
    ), patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1'), patch(
        'utils.llm.byok_errors.get_byok_key', return_value='sk-user'
    ):
        from utils.llm.byok_errors import handle_llm_error

        handle_llm_error(error, 'openai', feature='memories', model='gpt-test')

        assert mock_send.call_args.args[3]['reason'] == expected_reason
        assert body_fragment in mock_send.call_args.args[2]
