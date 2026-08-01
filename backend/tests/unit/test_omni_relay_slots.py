from unittest.mock import MagicMock

from routers import omni_relay


class _FakeRedis:
    """Evaluates the acquire script the way Redis does — as one atomic step."""

    def __init__(self):
        self.counts = {}
        self.ttls = {}
        self.decr_calls = []
        self.eval_calls = []

    def eval(self, script, numkeys, key, ttl):
        assert script is omni_relay._ACQUIRE_SLOT_LUA
        assert numkeys == 1
        self.eval_calls.append((key, ttl))
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        if self.ttls.get(key, -1) < 0:
            self.ttls[key] = ttl
        return count

    def decr(self, key):
        self.decr_calls.append(key)
        self.counts[key] = self.counts.get(key, 0) - 1
        return self.counts[key]


def _redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(omni_relay.redis_db, 'r', client)
    return client


def test_acquire_arms_the_ttl_in_the_same_atomic_operation_as_the_incr(monkeypatch):
    """INCR and EXPIRE as two round-trips let a crash between them strand the
    counter with no expiry — precisely the case the TTL was added for. Three
    such events and the uid is locked out permanently."""
    client = _redis(monkeypatch)
    key = omni_relay._slot_key('uid1')

    assert omni_relay._acquire_relay_slot('uid1') is True

    # A single call, so there is no window where the counter exists with no TTL.
    assert client.eval_calls == [(key, omni_relay._SLOT_TTL_SECONDS)]
    assert client.ttls[key] == omni_relay._SLOT_TTL_SECONDS


def test_second_holder_does_not_rearm_the_ttl(monkeypatch):
    """Re-arming on every acquire lets a reconnect loop keep a stuck counter
    alive indefinitely."""
    client = _redis(monkeypatch)
    key = omni_relay._slot_key('uid1')
    client.counts[key] = 1
    client.ttls[key] = 42

    assert omni_relay._acquire_relay_slot('uid1') is True

    assert client.ttls[key] == 42


def test_a_counter_that_lost_its_ttl_self_heals(monkeypatch):
    """The only way out of a stranded counter short of manual Redis surgery."""
    client = _redis(monkeypatch)
    key = omni_relay._slot_key('uid1')
    client.counts[key] = 1  # no TTL recorded

    assert omni_relay._acquire_relay_slot('uid1') is True

    assert client.ttls[key] == omni_relay._SLOT_TTL_SECONDS


def test_rejected_acquire_gives_the_slot_back(monkeypatch):
    client = _redis(monkeypatch)
    key = omni_relay._slot_key('uid1')
    client.counts[key] = omni_relay._MAX_CONCURRENT_RELAYS
    client.ttls[key] = omni_relay._SLOT_TTL_SECONDS

    assert omni_relay._acquire_relay_slot('uid1') is False

    assert client.decr_calls == [key]
    assert client.counts[key] == omni_relay._MAX_CONCURRENT_RELAYS


def test_acquire_fails_closed_when_redis_raises(monkeypatch):
    client = MagicMock()
    client.eval.side_effect = Exception('redis down')
    monkeypatch.setattr(omni_relay.redis_db, 'r', client)

    try:
        omni_relay._acquire_relay_slot('uid1')
    except Exception:
        return
    raise AssertionError('an unverifiable slot count must not grant a relay session')
