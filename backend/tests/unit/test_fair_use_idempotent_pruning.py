"""Bounded fair-use history pruning on idempotent admissions."""

import fakeredis
import pytest

import utils.fair_use as fair_use


@pytest.fixture
def redis(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(fair_use, 'redis_client', client)
    monkeypatch.setattr(fair_use, 'FAIR_USE_ENABLED', True)
    return client


def test_duplicate_idempotent_admission_prunes_stale_history_in_bounded_batches(redis, monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr(fair_use.time, 'time', lambda: now)
    uid = 'prune-test'
    source = 'sync_fresh'
    bucket_key = fair_use._bucket_key(uid, source)
    zset_key = fair_use._redis_key(uid, source)
    current_minute = now // fair_use.FAIR_USE_BUCKET_SECONDS
    stale_cutoff = now - fair_use.FAIR_USE_REDIS_RETENTION_SECONDS

    stale_fields = [str(current_minute - 20_000 - index) for index in range(140)]
    stale_values = {field: 100 for field in stale_fields}
    fresh_fields = [str(current_minute - 2), str(current_minute - 1)]
    fresh_values = {fresh_fields[0]: 1_000, fresh_fields[1]: 2_000}
    redis.hset(bucket_key, mapping={**stale_values, **fresh_values})
    redis.zadd(
        zset_key,
        {
            **{field: stale_cutoff - 1 - index for index, field in enumerate(stale_fields)},
            **{field: now - 120 + index * 60 for index, field in enumerate(fresh_fields)},
        },
    )
    once_key = f'fair_use:v2:once:speech:{source}:{uid}:existing-content'
    redis.set(once_key, '1', ex=fair_use.FAIR_USE_REDIS_RETENTION_SECONDS)

    # Duplicate admission must retain the existing NX once-marker behavior and
    # still run one bounded pruning batch.
    fair_use.record_speech_ms(uid, 5_000, source=source, idempotency_key='existing-content')
    assert redis.get(once_key) == '1'
    assert redis.zcard(zset_key) == 14
    assert redis.hlen(bucket_key) == 14
    remaining_stale = set(stale_fields) & set(redis.zrange(zset_key, 0, -1))
    assert len(remaining_stale) == 12

    # The next duplicate drains the bounded backlog without touching fresh data.
    fair_use.record_speech_ms(uid, 5_000, source=source, idempotency_key='existing-content')
    assert redis.zcard(zset_key) == 2
    assert redis.hlen(bucket_key) == 2
    assert not (set(stale_fields) & set(redis.zrange(zset_key, 0, -1)))
    assert all(redis.hexists(bucket_key, field) for field in fresh_fields)

    totals = fair_use.get_rolling_speech_ms(uid, sources=(source,))
    assert totals == {'daily_ms': 3_000, 'three_day_ms': 3_000, 'weekly_ms': 3_000}
