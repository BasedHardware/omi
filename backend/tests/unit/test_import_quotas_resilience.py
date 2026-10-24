"""Hermetic resilience tests for rolling transcript import quotas."""

import logging
import sys
import time
import types
import uuid
from unittest.mock import MagicMock

import pytest

# Stub database.redis_db before importing import_quotas so the redis package
# (which is not installed in this environment) is not required.
class FakeRedis:
    def __init__(self):
        self.zsets = {}
        self.hashes = {}
        self.eval_calls = 0

    def time(self):
        return (int(time.time()), 0)

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return len(mapping)

    def hget(self, key, field):
        value = self.hashes.get(key, {}).get(field)
        if value is None and isinstance(field, str):
            value = self.hashes.get(key, {}).get(field.encode())
        if value is None:
            return None
        if isinstance(value, (bytes, str)):
            return value.encode() if isinstance(value, str) else value
        return str(value).encode()

    def ttl(self, key):
        return 1

    def eval(self, script, num_keys, *args):
        self.eval_calls += 1
        keys = list(args[:num_keys])
        rest = list(args[num_keys:])
        events_key, amounts_key = keys[0], keys[1]
        zset = self.zsets.setdefault(events_key, {})
        hashed = self.hashes.setdefault(amounts_key, {})

        if 'ZADD' in script:  # reserve
            window = int(rest[0])
            limit = int(rest[1])
            amount = int(rest[2])
            reservation = str(rest[3])
            now = time.time()
            expired = [m for m, score in list(zset.items()) if score <= now - window]
            for member in expired:
                due = int(hashed.get(member, 0) or 0)
                hashed['total'] = str(int(hashed.get('total', 0) or 0) - due)
                hashed.pop(member, None)
                zset.pop(member, None)
            total = int(hashed.get('total', 0) or 0)
            if total + amount > limit:
                return 0
            zset[reservation] = now
            hashed[reservation] = amount
            hashed['total'] = str(total + amount)
            return 1
        # release
        reservation = str(rest[0])
        if reservation in zset:
            due = int(hashed.get(reservation, 0) or 0)
            del zset[reservation]
            hashed.pop(reservation, None)
            hashed['total'] = str(int(hashed.get('total', 0) or 0) - due)
        return 1


_fake_redis_module = types.ModuleType('database.redis_db')
_fake_redis_module.r = FakeRedis()
sys.modules['database.redis_db'] = _fake_redis_module

from database import import_quotas


@pytest.fixture(autouse=True)
def reset_fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(import_quotas.redis_db, 'r', fake)
    import_quotas.redis_db.r = fake
    monkeypatch.delenv('IMPORT_MONTHLY_UPLOAD_LIMIT', raising=False)
    monkeypatch.delenv('IMPORT_MONTHLY_BYTE_LIMIT', raising=False)
    return fake


# ---------- _sanitize_uid ----------
def test_sanitize_uid_empty_raises():
    with pytest.raises(ValueError):
        import_quotas._sanitize_uid('')


def test_sanitize_uid_whitespace_only_raises():
    with pytest.raises(ValueError):
        import_quotas._sanitize_uid('   \t\n')


def test_sanitize_uid_forbidden_chars_raise():
    for value in ('a{b', 'a}b', 'a:b', 'a/b', 'a\\b', 'a..b'):
        with pytest.raises(ValueError):
            import_quotas._sanitize_uid(value)


def test_sanitize_uid_control_char_raises():
    with pytest.raises(ValueError):
        import_quotas._sanitize_uid('abc\x00def')


def test_sanitize_uid_non_string_raises():
    with pytest.raises(ValueError):
        import_quotas._sanitize_uid(123)


def test_sanitize_uid_valid_returns_same():
    assert import_quotas._sanitize_uid('user-123') == 'user-123'


# ---------- _sanitize_kind ----------
def test_sanitize_kind_valid_returns_same():
    assert import_quotas._sanitize_kind('upload') == 'upload'
    assert import_quotas._sanitize_kind('byte') == 'byte'


def test_sanitize_kind_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        import_quotas._sanitize_kind('nope')


def test_sanitize_kind_case_sensitive_raises():
    with pytest.raises(KeyError):
        import_quotas._sanitize_kind('Upload')


# ---------- _sanitize_amount ----------
def test_sanitize_amount_bool_rejected():
    with pytest.raises(ValueError):
        import_quotas._sanitize_amount(True)


def test_sanitize_amount_float_rejected():
    with pytest.raises(ValueError):
        import_quotas._sanitize_amount(5.0)


def test_sanitize_amount_str_rejected():
    with pytest.raises(ValueError):
        import_quotas._sanitize_amount('5')


def test_sanitize_amount_zero_rejected():
    with pytest.raises(ValueError):
        import_quotas._sanitize_amount(0)


def test_sanitize_amount_negative_rejected():
    with pytest.raises(ValueError):
        import_quotas._sanitize_amount(-3)


def test_sanitize_amount_positive_accepted():
    assert import_quotas._sanitize_amount(7) == 7


# ---------- _quota_keys ----------
def test_quota_keys_sanitizes_uid():
    with pytest.raises(ValueError):
        import_quotas._quota_keys('a{b', 'upload')


def test_quota_keys_sanitizes_kind():
    with pytest.raises(KeyError):
        import_quotas._quota_keys('u1', 'nope')


def test_quota_keys_shape():
    events, amounts = import_quotas._quota_keys('u1', 'upload')
    assert events == 'import:monthly:upload:{u1}:events'
    assert amounts == 'import:monthly:upload:{u1}:amounts'


# ---------- import_quota_limit ----------
def test_import_quota_limit_defaults():
    assert import_quotas.import_quota_limit('upload') == 100
    assert import_quotas.import_quota_limit('byte') == 1024 * 1024 * 1024


def test_import_quota_limit_env_override(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '7')
    assert import_quotas.import_quota_limit('upload') == 7


def test_import_quota_limit_env_zero(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '0')
    assert import_quotas.import_quota_limit('upload') == 0


def test_import_quota_limit_unknown_kind_raises():
    with pytest.raises(KeyError):
        import_quotas.import_quota_limit('nope')


def test_import_quota_limit_bad_env_warns_and_falls_back(monkeypatch, caplog):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', 'not-a-number')
    with caplog.at_level(logging.WARNING, logger='database.import_quotas'):
        result = import_quotas.import_quota_limit('upload')
    assert result == 100
    assert any(r.levelname == 'WARNING' for r in caplog.records)


def test_import_quota_limit_bad_env_empty_warns(monkeypatch, caplog):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '')
    with caplog.at_level(logging.WARNING, logger='database.import_quotas'):
        result = import_quotas.import_quota_limit('upload')
    assert result == 100
    assert any(r.levelname == 'WARNING' for r in caplog.records)


# ---------- reserve_import_quota ----------
def test_reserve_invalid_uid_no_client_call():
    client = MagicMock()
    with pytest.raises(ValueError):
        import_quotas.reserve_import_quota('', 'upload', 1, redis_client=client)
    client.eval.assert_not_called()


def test_reserve_invalid_kind_no_client_call():
    client = MagicMock()
    with pytest.raises(KeyError):
        import_quotas.reserve_import_quota('u1', 'nope', 1, redis_client=client)
    client.eval.assert_not_called()


def test_reserve_invalid_amount_no_client_call():
    client = MagicMock()
    with pytest.raises(ValueError):
        import_quotas.reserve_import_quota('u1', 'upload', True, redis_client=client)
    client.eval.assert_not_called()


def test_reserve_admitted_returns_reservation():
    client = MagicMock()
    client.eval.return_value = 1
    reservation = import_quotas.reserve_import_quota('u1', 'upload', 1, redis_client=client)
    assert isinstance(reservation, str) and len(reservation) == 32


def test_reserve_denied_returns_none():
    client = MagicMock()
    client.eval.return_value = 0
    assert import_quotas.reserve_import_quota('u1', 'upload', 1, redis_client=client) is None


def test_reserve_uses_explicit_redis_client():
    client = MagicMock()
    client.eval.return_value = 1
    import_quotas.reserve_import_quota('u1', 'upload', 1, redis_client=client)
    client.eval.assert_called_once()


def test_reserve_defaults_to_redis_db_r(monkeypatch):
    default_client = MagicMock()
    default_client.eval.return_value = 1
    monkeypatch.setattr(import_quotas.redis_db, 'r', default_client)
    import_quotas.reserve_import_quota('u1', 'upload', 1)
    default_client.eval.assert_called_once()


# ---------- release_import_quota ----------
def test_release_skips_redis_roundtrip_for_bad_reservations():
    client = MagicMock()
    for reservation in (None, '', '   ', 'a\x00b'):
        import_quotas.release_import_quota('u1', 'upload', reservation, redis_client=client)
    client.eval.assert_not_called()


def test_release_uses_client_for_valid_reservation():
    client = MagicMock()
    import_quotas.release_import_quota('u1', 'upload', 'reservation-1', redis_client=client)
    client.eval.assert_called_once()


# ---------- fake redis integration ----------
def test_fake_redis_reserve_and_release_roundtrip(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_BYTE_LIMIT', '10')
    client = FakeRedis()
    # use explicit client without touching module-level fake
    reservation = import_quotas.reserve_import_quota('u1', 'byte', 7, redis_client=client)
    assert reservation
    assert import_quotas.reserve_import_quota('u1', 'byte', 4, redis_client=client) is None
    import_quotas.release_import_quota('u1', 'byte', reservation, redis_client=client)
    assert import_quotas.reserve_import_quota('u1', 'byte', 7, redis_client=client)
