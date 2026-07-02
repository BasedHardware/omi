import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers import users as users_router


def test_delete_account_delegates_to_service():
    start_account_deletion = MagicMock(return_value={'status': 'ok', 'message': 'Account deletion started'})
    request = users_router.DeleteAccountRequest(reason='reason', reason_details='details')

    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
        result = users_router.delete_account(request=request, uid='uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    start_account_deletion.assert_called_once_with('uid1', reason='reason', reason_details='details')


def test_delete_account_maps_unexpected_service_error_to_500():
    start_account_deletion = MagicMock(side_effect=Exception('boom'))
    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
        with pytest.raises(HTTPException) as exc:
            users_router.delete_account(request=users_router.DeleteAccountRequest(), uid='uid1')

    assert exc.value.status_code == 500
    assert exc.value.detail == 'Could not delete account. Please try again.'


def test_export_all_user_data_keeps_streaming_headers():
    users_router.iter_user_data_export = MagicMock(return_value=iter(['{"ok": true}\n']))

    response = users_router.export_all_user_data(uid='uid1')

    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    users_router.iter_user_data_export.assert_called_once_with('uid1')

    async def _consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return ''.join(parts)

    assert asyncio.run(_consume()) == '{"ok": true}\n'
