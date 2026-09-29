from database.translation_admission import release_translation, reservation_is_current, reserve_translation


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.down = False

    def eval(self, script, count, *args):
        if self.down:
            raise ConnectionError('offline')
        keys, values = args[:count], args[count:]
        if 'INCRBY' in script:
            token, _ttl, amount, uid_cap, global_cap, _day_ttl = values
            if keys[0] in self.values or keys[1] in self.values:
                return 0
            if (
                int(self.values.get(keys[2], 0)) + amount > uid_cap
                or int(self.values.get(keys[3], 0)) + amount > global_cap
            ):
                return -1
            self.values[keys[0]] = self.values[keys[1]] = token.encode()
            self.values[keys[2]] = int(self.values.get(keys[2], 0)) + amount
            self.values[keys[3]] = int(self.values.get(keys[3], 0)) + amount
            return 1
        token, refund = values
        if self.values.get(keys[0]) != token.encode() or self.values.get(keys[1]) != token.encode():
            return 0
        self.values.pop(keys[0])
        self.values.pop(keys[1])
        self.values[keys[2]] -= refund
        self.values[keys[3]] -= refund
        return 1

    def get(self, key):
        if self.down:
            raise ConnectionError('offline')
        return self.values.get(key)


def test_shared_uid_lock_budget_refund_and_late_release():
    redis = FakeRedis()
    first, reason = reserve_translation(
        'u', 'c', 'en', 'rev1', 'viewed_v1', 100, 150, 150, client=redis, day='20260929'
    )
    assert reason == 'admitted' and first is not None
    second, reason = reserve_translation(
        'u', 'c', 'en', 'rev2', 'viewed_v1', 100, 150, 150, client=redis, day='20260929'
    )
    assert second is None and reason == 'duplicate_suppressed'
    assert reservation_is_current(first, client=redis)
    assert release_translation(first, 30, client=redis)
    assert not release_translation(first, 0, client=redis)
    third, reason = reserve_translation(
        'u', 'another', 'en', 'rev3', 'viewed_v1', 130, 150, 150, client=redis, day='20260929'
    )
    assert third is None and reason == 'budget_denied'
    redis.down = True
    fourth, reason = reserve_translation(
        'u', 'c', 'en', 'rev1', 'viewed_v1', 10, 150, 150, client=redis, day='20260929'
    )
    assert fourth is None and reason == 'redis_unavailable'
