from unittest.mock import MagicMock

from routers import omni_relay


def _redis_stub(monkeypatch, counts):
    client = MagicMock()
    client.incr.side_effect = counts
    monkeypatch.setattr(omni_relay.redis_db, 'r', client)
    return client


def test_acquire_arms_the_ttl_only_for_the_first_holder(monkeypatch):
    client = _redis_stub(monkeypatch, [1, 2])

    assert omni_relay._acquire_relay_slot('uid1') is True
    assert omni_relay._acquire_relay_slot('uid1') is True

    client.expire.assert_called_once_with(omni_relay._slot_key('uid1'), omni_relay._SLOT_TTL_SECONDS)


def test_rejected_acquire_does_not_rearm_the_ttl(monkeypatch):
    """Re-arming on rejection lets a reconnect loop keep a stuck counter alive forever."""
    over = omni_relay._MAX_CONCURRENT_RELAYS + 1
    client = _redis_stub(monkeypatch, [over, over])

    assert omni_relay._acquire_relay_slot('uid1') is False
    assert omni_relay._acquire_relay_slot('uid1') is False

    client.expire.assert_not_called()
    assert client.decr.call_count == 2
