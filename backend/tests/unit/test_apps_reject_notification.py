"""reject_app must forward the rejection reason and deep-link payload in the notification.

The endpoint body stays optional so released clients that reject without a reason keep
working (no required requestBody on /v1/apps/{app_id}/reject). When a reason is sent it
must reach the notification body, and every rejection must carry the
``{'app_id', 'type': 'app_rejected', 'navigate_to': '/apps/<app_id>'}`` data payload so
tapping the notification opens the app page (HomeDeepLink maps the ``apps`` alias).
"""

from unittest.mock import MagicMock, patch

import routers.apps as apps
from routers.apps import AppRejectRequest, reject_app

ADMIN_KEY = 'test-admin-key'
EXPECTED_DATA = {'app_id': 'app-1', 'type': 'app_rejected', 'navigate_to': '/apps/app-1'}


def _reject(data) -> MagicMock:
    send_notification = MagicMock()
    with patch.dict('os.environ', {'ADMIN_KEY': ADMIN_KEY}), patch.object(
        apps, 'change_app_approval_status'
    ), patch.object(apps, 'invalidate_approved_apps_cache'), patch.object(apps, 'delete_app_cache_by_id'), patch.object(
        apps, 'get_available_app_by_id', return_value={'id': 'app-1', 'name': 'Weather'}
    ), patch.object(
        apps, 'send_notification', send_notification
    ):
        reject_app(app_id='app-1', uid='dev-1', data=data, secret_key=ADMIN_KEY)
    return send_notification


def test_reject_app_forwards_reason_and_deep_link_payload():
    send_notification = _reject(AppRejectRequest(reason='Spam keywords'))

    send_notification.assert_called_once()
    uid, title, body, data = send_notification.call_args.args[:4]
    assert (uid, title) == ('dev-1', 'App Rejected 😔')
    assert 'has been rejected.' in body
    assert ' Reason: Spam keywords.' in body
    assert data == EXPECTED_DATA


def test_reject_app_without_body_keeps_notification_backward_compatible():
    send_notification = _reject(None)

    send_notification.assert_called_once()
    uid, title, body, data = send_notification.call_args.args[:4]
    assert (uid, title) == ('dev-1', 'App Rejected 😔')
    assert 'Reason:' not in body
    assert 'has been rejected.' in body
    assert data == EXPECTED_DATA
