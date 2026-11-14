import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest

import database.users as users_db
import utils.byok as byok_util


def test_coerce_utc_datetime_in_users_and_byok():
    assert hasattr(users_db, '_coerce_utc_datetime'), "users_db must have _coerce_utc_datetime"
    assert hasattr(byok_util, '_coerce_utc_datetime'), "byok_util must have _coerce_utc_datetime"

    for fn in [users_db._coerce_utc_datetime, byok_util._coerce_utc_datetime]:
        # Naive datetime
        naive = datetime(2026, 10, 28, 12, 0, 0)
        res = fn(naive)
        assert res is not None
        assert res.tzinfo == timezone.utc
        assert res.hour == 12

        # Non-UTC aware datetime
        offset = timezone(timedelta(hours=4))
        aware = datetime(2026, 10, 28, 16, 0, 0, tzinfo=offset)
        res = fn(aware)
        assert res is not None
        assert res.tzinfo == timezone.utc
        assert res.hour == 12

        # ISO string naive
        res = fn("2026-10-28T12:00:00")
        assert res is not None
        assert res.tzinfo == timezone.utc
        assert res.hour == 12

        # ISO string aware
        res = fn("2026-10-28T12:00:00Z")
        assert res is not None
        assert res.tzinfo == timezone.utc
        assert res.hour == 12

        # None / invalid
        assert fn(None) is None
        assert fn("invalid") is None
        assert fn(999) is None


def test_get_byok_state_guards_explicit_none():
    client = MagicMock()
    snapshot = MagicMock()
    # User document has explicit {'byok': None}
    snapshot.to_dict.return_value = {'byok': None}
    client.collection.return_value.document.return_value.get.return_value = snapshot

    with patch('database.users.user_snapshot', return_value=snapshot):
        state = users_db.get_byok_state('user_none_byok', firestore_client=client)
        assert isinstance(state, dict)
        assert state == {}

        # Non-dict byok field (e.g. string or list)
        snapshot.to_dict.return_value = {'byok': 'invalid'}
        state = users_db.get_byok_state('user_invalid_byok', firestore_client=client)
        assert isinstance(state, dict)
        assert state == {}


def test_is_byok_active_with_naive_and_iso_timestamps():
    now = datetime.now(timezone.utc)
    recent_naive = (now - timedelta(hours=1)).replace(tzinfo=None)
    old_naive = (now - timedelta(days=10)).replace(tzinfo=None)
    recent_iso = (now - timedelta(hours=2)).isoformat()
    old_iso = (now - timedelta(days=10)).isoformat()

    # 1. Recent naive datetime must be active and not raise TypeError
    with patch('database.users.get_byok_state', return_value={'active': True, 'last_seen_at': recent_naive}):
        assert users_db.is_byok_active('u1') is True

    # 2. Old naive datetime must be inactive
    with patch('database.users.get_byok_state', return_value={'active': True, 'last_seen_at': old_naive}):
        assert users_db.is_byok_active('u1') is False

    # 3. Recent ISO string must be active (not false-negative)
    with patch('database.users.get_byok_state', return_value={'active': True, 'last_seen_at': recent_iso}):
        assert users_db.is_byok_active('u1') is True

    # 4. Old ISO string must be inactive
    with patch('database.users.get_byok_state', return_value={'active': True, 'last_seen_at': old_iso}):
        assert users_db.is_byok_active('u1') is False

    # 5. None state or None last_seen_at
    with patch('database.users.get_byok_state', return_value={'active': True, 'last_seen_at': None}):
        assert users_db.is_byok_active('u1') is False

    with patch('database.users.get_byok_state', return_value={}):
        assert users_db.is_byok_active('u1') is False


def test_validated_byok_keys_guards_none_and_timestamps():
    now = datetime.now(timezone.utc)
    recent_naive = (now - timedelta(minutes=5)).replace(tzinfo=None)
    key_val = "sk-ant-test-key-1234"
    fp_val = hashlib.sha256(key_val.encode()).hexdigest()

    # 1. State with naive last_seen_at and explicit None in fingerprints
    state_payload = {
        'active': True,
        'last_seen_at': recent_naive,
        'fingerprints': {
            'anthropic': fp_val,
            'openai': None,  # None fingerprint entry
            'gemini': 12345,  # non-string fingerprint
        },
    }

    with patch('utils.byok.get_cached_byok_state', return_value=state_payload), patch.object(byok_util.logger, 'warning') as mock_warn:
        validated, err = byok_util._validated_byok_keys('u1', {'anthropic': key_val})
        assert err is None
        assert validated == {'anthropic': key_val}
        skipped_warnings = [
            call[0][0]
            for call in mock_warn.call_args_list
            if "Skipping corrupt non-string BYOK fingerprint" in str(call[0][0])
        ]
        assert len(skipped_warnings) == 2

    # 2. State with None fingerprints map
    state_none_fps = {
        'active': True,
        'last_seen_at': recent_naive,
        'fingerprints': None,
    }
    with patch('utils.byok.get_cached_byok_state', return_value=state_none_fps):
        validated, err = byok_util._validated_byok_keys('u1', {'anthropic': key_val})
        assert err is None
        assert validated == {}

    # 3. Cached state itself is None or empty
    with patch('utils.byok.get_cached_byok_state', return_value=None):
        validated, err = byok_util._validated_byok_keys('u1', {'anthropic': key_val})
        assert err is None
        assert validated == {}
