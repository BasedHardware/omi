from datetime import datetime, timezone
from types import SimpleNamespace

import fakeredis
from google.api_core.exceptions import ServiceUnavailable
from prometheus_client import Gauge
from redis.exceptions import ConnectionError

from database import batch_privacy_dead_letter_stock as stock


class CountQuery:
    def __init__(self):
        now = datetime(2026, 11, 28, tzinfo=timezone.utc)
        self.rows = {
            'intent': {'dead_lettered_at': now},
            'receipt_retry': {'dead_lettered_at': now, 'artifact_id': 'receipt'},
            'pending': {'due_at': now},
        }
        self.calls = 0
        self.fail = False

    def collection(self, name):
        assert name == 'batch_privacy_late_sweeps'
        return self

    def where(self, *, filter):
        assert filter.op_string == '>='
        self.field = filter.field_path
        self.cutoff = filter.value
        return self

    def count(self):
        return self

    def get(self, *, timeout, retry):
        assert timeout == 5 and retry is None
        self.calls += 1
        if self.fail:
            raise ServiceUnavailable('synthetic count error')
        values = (row.get(self.field) for row in self.rows.values())
        return [[SimpleNamespace(value=sum(value is not None and value >= self.cutoff for value in values))]]


def test_stock_retains_intent_and_receipt_failures_until_resolved_and_fails_stale(monkeypatch):
    query = CountQuery()
    redis = fakeredis.FakeRedis()
    now = 1_000.0
    units = Gauge('test_privacy_dead_letter_units', 'test', registry=None)
    observed_at = Gauge('test_privacy_dead_letter_observed_at', 'test', registry=None)
    monkeypatch.setattr(stock, 'get_data_plane_firestore_client', lambda: query)
    monkeypatch.setattr(stock, '_redis_client', lambda: redis)
    monkeypatch.setattr(stock, 'time', SimpleNamespace(time=lambda: now))
    monkeypatch.setattr(stock, 'DEAD_LETTER_UNITS', units)
    monkeypatch.setattr(stock, 'DEAD_LETTER_OBSERVED_AT', observed_at)

    def assert_sample(expected_stock, expected_time):
        assert units.collect()[0].samples[0].value == expected_stock
        assert observed_at.collect()[0].samples[0].value == expected_time

    stock.publish_dead_letter_stock()
    stock.publish_dead_letter_stock()
    assert query.calls == 1
    assert redis.ttl(stock._SAMPLE_KEY) == 300
    assert_sample(2, 1000)

    redis.delete(stock._SAMPLE_KEY)  # Simulate expiration of the shared cooldown.
    now = 1300.0
    query.fail = True
    stock.publish_dead_letter_stock()
    stock.publish_dead_letter_stock()
    assert query.calls == 2
    assert_sample(2, 1000)

    redis.delete(stock._SAMPLE_KEY)
    now = 1600.0
    query.fail = False
    # Successful recovery completes through the sweeper and removes the retained row.
    del query.rows['intent']
    del query.rows['receipt_retry']
    stock.publish_dead_letter_stock()
    assert query.calls == 3
    assert_sample(0, 1600)


def test_redis_failure_cannot_fan_out_firestore_reads(monkeypatch):
    def fail_redis():
        raise ConnectionError('synthetic admission failure')

    query = CountQuery()
    monkeypatch.setattr(stock, '_redis_client', fail_redis)
    monkeypatch.setattr(stock, 'get_data_plane_firestore_client', lambda: query)
    stock.publish_dead_letter_stock()
    assert query.calls == 0
