"""A malformed stored app must 404 the app-to-user notification routes, not 500.

`POST /v1/integrations/notification` and `POST /v2/integrations/{app_id}/notification`
authenticate the calling app by API key, then built `App(**app_data)` after only a
truthiness check. A stored app doc missing a required field (name, category, image, ...)
raised `ValidationError`, so the integration got a 500. They now use
`App.deserialize_safe`, as the app detail routes do since #19584, and keep the existing
`404 App not found`.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers import integration as integration_router
from routers import notifications as notifications_router

MALFORMED_APP = {'id': 'app-1', 'private': False}
BEARER = 'Bearer key'


def test_the_v1_app_notification_for_a_malformed_app_is_not_found():
    body = {'aid': 'app-1', 'uid': 'user-1', 'message': 'hello'}
    with patch.object(notifications_router, 'verify_api_key', return_value=True), patch.object(
        notifications_router, 'get_available_app_by_id', return_value=dict(MALFORMED_APP)
    ), pytest.raises(HTTPException) as raised:
        notifications_router.send_app_notification_to_user(None, body, authorization=BEARER)

    assert raised.value.status_code == 404


def test_the_v2_integration_notification_for_a_malformed_app_is_not_found():
    with patch.object(integration_router, 'verify_api_key', return_value=True), patch.object(
        integration_router.apps_utils, 'get_available_app_by_id', return_value=dict(MALFORMED_APP)
    ), pytest.raises(HTTPException) as raised:
        integration_router.send_notification_via_integration(None, 'app-1', 'hello', 'user-1', authorization=BEARER)

    assert raised.value.status_code == 404
