import os
from unittest.mock import patch

from tests.unit.twilio_stub import install_phone_calls_stub, install_twilio_stub, prepare_twilio_service_import

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'ACtest123')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test_auth_token')
os.environ.setdefault('TWILIO_API_KEY_SID', 'SKtest123')
os.environ.setdefault('TWILIO_API_KEY_SECRET', 'test_api_secret')
os.environ.setdefault('TWILIO_TWIML_APP_SID', 'APtest123')
install_twilio_stub()
prepare_twilio_service_import()


# Stub `database.phone_calls` before twilio_service tries to import it so we can
# unit-test delete_user_caller_ids without dragging in firebase_admin and the
# rest of the database init chain. The real implementation only uses
# `get_phone_numbers`, which the tests override per-case via patch.object.
install_phone_calls_stub()

from utils import twilio_service
from database import phone_calls as phone_calls_db  # noqa: E402  (stub above)


def test_delete_user_caller_ids_calls_twilio_for_each_sid():
    numbers = [
        {'id': 'a', 'twilio_sid': 'PNaaaa'},
        {'id': 'b', 'twilio_sid': 'PNbbbb'},
    ]
    with patch.object(twilio_service, 'delete_caller_id', return_value=True) as mock_delete, patch.object(
        phone_calls_db, 'get_phone_numbers', return_value=numbers
    ):
        deleted = twilio_service.delete_user_caller_ids('uid-1')
    assert deleted == 2
    assert mock_delete.call_count == 2
    assert mock_delete.call_args_list[0].args[0] == 'PNaaaa'
    assert mock_delete.call_args_list[1].args[0] == 'PNbbbb'


def test_delete_user_caller_ids_skips_entries_without_sid():
    numbers = [
        {'id': 'a', 'twilio_sid': 'PNaaaa'},
        {'id': 'b'},
        {'id': 'c', 'twilio_sid': None},
        {'id': 'd', 'twilio_sid': ''},
    ]
    with patch.object(twilio_service, 'delete_caller_id', return_value=True) as mock_delete, patch.object(
        phone_calls_db, 'get_phone_numbers', return_value=numbers
    ):
        deleted = twilio_service.delete_user_caller_ids('uid-1')
    assert deleted == 1
    assert mock_delete.call_count == 1
    assert mock_delete.call_args_list[0].args[0] == 'PNaaaa'


def test_delete_user_caller_ids_continues_when_one_raises():
    # Simulates _get_client() raising mid-loop (e.g. credentials were rotated
    # and the cached client got reset between entries). Twilio API errors
    # themselves don't reach this path — delete_caller_id swallows those and
    # returns False — but the outer guard exists for _get_client() failures,
    # and it must not abort cleanup of the remaining caller IDs.
    numbers = [
        {'id': 'a', 'twilio_sid': 'PNaaaa'},
        {'id': 'b', 'twilio_sid': 'PNbbbb'},
        {'id': 'c', 'twilio_sid': 'PNcccc'},
    ]

    def fake_delete(sid):
        if sid == 'PNbbbb':
            raise RuntimeError('twilio client unavailable')
        return True

    with patch.object(twilio_service, 'delete_caller_id', side_effect=fake_delete) as mock_delete, patch.object(
        phone_calls_db, 'get_phone_numbers', return_value=numbers
    ):
        deleted = twilio_service.delete_user_caller_ids('uid-1')
    assert deleted == 2
    assert mock_delete.call_count == 3


def test_delete_user_caller_ids_returns_zero_when_no_phone_numbers():
    with patch.object(twilio_service, 'delete_caller_id', return_value=True) as mock_delete, patch.object(
        phone_calls_db, 'get_phone_numbers', return_value=[]
    ):
        deleted = twilio_service.delete_user_caller_ids('uid-1')
    assert deleted == 0
    assert mock_delete.call_count == 0


def test_delete_user_caller_ids_swallows_phone_list_error():
    # If we can't even list the user's phone_numbers, we still must not raise —
    # the caller (delete_account background wipe) needs to keep going so the
    # Firestore wipe completes.
    with patch.object(twilio_service, 'delete_caller_id', return_value=True) as mock_delete, patch.object(
        phone_calls_db, 'get_phone_numbers', side_effect=RuntimeError('firestore down')
    ):
        deleted = twilio_service.delete_user_caller_ids('uid-1')
    assert deleted == 0
    assert mock_delete.call_count == 0
