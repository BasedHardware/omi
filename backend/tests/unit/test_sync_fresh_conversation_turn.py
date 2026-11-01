"""At most one fresh job persists into one user's conversation at a time.

Concurrent fresh jobs for the same conversation each ran the assignment transaction and the
bridge copy against the same documents and objects (FirestoreContentionExhausted, GCS 429).
The turn is a throughput guard, so every failure mode proceeds unserialized.
"""

import pytest
from prometheus_client import REGISTRY

from utils.sync import conversation_turn


class _Redis:
    def __init__(self):
        self.values = {}
        self.calls = 0

    def set(self, key, value, nx=False, ex=None):
        self.calls += 1
        assert nx and ex == conversation_turn.TURN_TTL_SECONDS
        if key in self.values:
            return None
        self.values[key] = value
        return True

    def eval(self, script, numkeys, key, token):
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def redis(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(conversation_turn, 'r', fake)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('SYNC_FRESH_CONVERSATION_TURN', raising=False)
    return fake


def _turns(outcome):
    return REGISTRY.get_sample_value('omi_sync_fresh_conversation_turn_total', {'outcome': outcome}) or 0.0


def test_one_turn_per_conversation_and_release_frees_it(redis):
    first = conversation_turn.acquire('uid-7q', 'conv-9z', 'fresh')
    assert first is not None
    other_conversation = conversation_turn.acquire('uid-7q', 'conv-8y', 'fresh')
    assert other_conversation is not None and other_conversation.key != first.key
    assert 'uid-7q' not in first.key and 'conv-9z' not in first.key

    conversation_turn.release(first)
    again = conversation_turn.acquire('uid-7q', 'conv-9z', 'fresh')
    assert again is not None


def test_second_job_waits_for_the_holder(redis, monkeypatch):
    holder = conversation_turn.acquire('u', 'c1', 'fresh')
    clock = _Clock()
    waited = _turns('waited')

    def sleep(seconds):
        clock.sleep(seconds)
        if clock.now > 1.0:
            conversation_turn.release(holder)

    turn = conversation_turn.acquire('u', 'c1', 'fresh', sleep=sleep, clock=clock)

    assert turn is not None and turn.token != holder.token
    assert _turns('waited') == waited + 1


def test_wait_is_bounded_and_then_proceeds_unserialized(redis):
    conversation_turn.acquire('u', 'c1', 'fresh')
    clock = _Clock()
    timeouts = _turns('timeout')

    assert conversation_turn.acquire('u', 'c1', 'fresh', wait_seconds=2.0, sleep=clock.sleep, clock=clock) is None
    assert 2.0 <= clock.now < 3.0
    assert _turns('timeout') == timeouts + 1


def test_release_never_frees_a_turn_another_job_now_holds(redis):
    stale = conversation_turn.acquire('u', 'c1', 'fresh')
    redis.values[stale.key] = 'successor-token'  # stale holder's TTL expired; another job acquired

    conversation_turn.release(stale)

    assert redis.values[stale.key] == 'successor-token'


def test_backfill_and_kill_switch_do_not_touch_redis(redis, monkeypatch):
    assert conversation_turn.acquire('u', 'c1', 'backfill') is None
    assert conversation_turn.acquire('u', None, 'fresh') is None  # new conversation: no uid-wide key
    monkeypatch.setenv('SYNC_FRESH_CONVERSATION_TURN', 'off')
    assert conversation_turn.acquire('u', 'c1', 'fresh') is None
    assert redis.calls == 0
    conversation_turn.release(None)


def test_unavailable_redis_or_stage_proceeds_unserialized(redis, monkeypatch):
    unavailable = _turns('unavailable')

    def broken_set(*args, **kwargs):
        raise ConnectionError('redis down')

    monkeypatch.setattr(redis, 'set', broken_set)
    assert conversation_turn.acquire('u', 'c1', 'fresh') is None

    monkeypatch.setenv('OMI_ENV_STAGE', 'not-a-stage')
    assert conversation_turn.acquire('u', 'c1', 'fresh') is None
    assert _turns('unavailable') == unavailable + 2
