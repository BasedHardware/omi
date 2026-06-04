import os
import sys
import types
from unittest.mock import patch

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'ACtest123')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test_auth_token')
os.environ.setdefault('TWILIO_API_KEY_SID', 'SKtest123')
os.environ.setdefault('TWILIO_API_KEY_SECRET', 'test_api_secret')
os.environ.setdefault('TWILIO_TWIML_APP_SID', 'APtest123')


# Stub `database.phone_calls` before twilio_service tries to import it so we can
# unit-test delete_user_caller_ids without dragging in firebase_admin and the
# rest of the database init chain. The real implementation only uses
# `get_phone_numbers`, which the tests override per-case via patch.object.
def _install_phone_calls_stub():
    if 'database' not in sys.modules:
        sys.modules['database'] = types.ModuleType('database')
    if 'database.phone_calls' not in sys.modules:
        stub = types.ModuleType('database.phone_calls')

        def get_phone_numbers(uid):
            return []

        stub.get_phone_numbers = get_phone_numbers
        sys.modules['database.phone_calls'] = stub
        setattr(sys.modules['database'], 'phone_calls', stub)


_install_phone_calls_stub()

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
    # An exception escaping delete_caller_id (rather than the swallowed False
    # return path) must not abort cleanup of the remaining caller IDs.
    numbers = [
        {'id': 'a', 'twilio_sid': 'PNaaaa'},
        {'id': 'b', 'twilio_sid': 'PNbbbb'},
        {'id': 'c', 'twilio_sid': 'PNcccc'},
    ]

    def fake_delete(sid):
        if sid == 'PNbbbb':
            raise RuntimeError('twilio 503')
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
