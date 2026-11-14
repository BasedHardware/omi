"""Delivered-share sampling: bounded metadata page, per-language cells, collector."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from database.batch_pipeline_delivered_share import (
    ADMITTED_STATES,
    COHORT_SECONDS,
    FIELDS,
    PAGE_LIMIT,
    TARGET_SECONDS,
    delivered_share_page,
    delivery_stamp,
)
from utils.batch_pipeline import delivered_share as module

NOW = 2_000_000_000.0


class PageQuery:
    def __init__(self, client, filters=(), page=None, projection=()):
        self.client, self.filters, self.page, self.projection = client, filters, page, projection

    def where(self, key, op, value):
        return PageQuery(self.client, self.filters + ((key, op, value),), self.page, self.projection)

    def order_by(self, key):
        return PageQuery(self.client, self.filters, self.page, self.projection)

    def select(self, fields):
        return PageQuery(self.client, self.filters, self.page, tuple(fields))

    def limit(self, value):
        return PageQuery(self.client, self.filters, value, self.projection)

    def stream(self, *, timeout, retry):
        assert timeout == 10 and retry is None
        self.client.calls.append((self.filters, self.page, self.projection))
        if self.client.fail:
            raise RuntimeError('synthetic page failure')
        rows = [row for row in self.client.rows if _matches(row, self.filters)]
        rows.sort(key=lambda row: row['enqueued_at'])
        return [SimpleNamespace(to_dict=lambda row=row: row) for row in rows[: self.page]]


def _matches(row, filters):
    for key, op, value in filters:
        actual = row.get(key)
        if op == 'in' and actual not in value:
            return False
        if op == '>=' and actual < value:
            return False
        if op == '<=' and actual > value:
            return False
    return True


class PageClient:
    def __init__(self, rows=(), fail=False):
        self.rows = rows
        self.calls = []
        self.fail = fail

    def collection(self, name):
        assert name == 'batch_pipeline_dev_jobs'
        return PageQuery(self)


def _query():
    return PageQuery(PageClient())


def test_page_is_the_cohort_window_ordered_by_admission_and_bounded():
    query = _query().limit(PAGE_LIMIT)
    assert query.page == PAGE_LIMIT
    assert PAGE_LIMIT == 5000


def test_page_selects_admitted_states_and_excludes_reservations():
    client = PageClient(
        [
            {'state': 'ready', 'enqueued_at': NOW - 400},
            {'state': 'provider_pending', 'enqueued_at': NOW - 500},
            {'state': 'committed', 'enqueued_at': NOW - 600},
            {'state': 'record_pending', 'enqueued_at': NOW - 500},
            {'state': 'ready', 'enqueued_at': NOW - TARGET_SECONDS + 1},
            {'state': 'ready', 'enqueued_at': NOW - COHORT_SECONDS - TARGET_SECONDS - 1},
        ]
    )
    rows, truncated = delivered_share_page(client, 'batch_pipeline_dev', NOW)
    assert [row['state'] for row in rows] == ['committed', 'provider_pending', 'ready']
    assert truncated is False
    filters, limit, projection = client.calls[0]
    assert limit == PAGE_LIMIT
    assert projection == FIELDS
    assert 'owner_id' not in projection
    assert ('state', 'in', list(ADMITTED_STATES)) in filters
    assert ('enqueued_at', '>=', NOW - COHORT_SECONDS - TARGET_SECONDS) in filters
    assert ('enqueued_at', '<=', NOW - TARGET_SECONDS) in filters
    assert 'record_pending' not in ADMITTED_STATES


def test_page_reports_truncation_at_the_cap():
    client = PageClient([{'state': 'ready', 'enqueued_at': NOW - 400}] * 3)
    rows, truncated = delivered_share_page(client, 'batch_pipeline_dev', NOW, limit=3)
    assert len(rows) == 3 and truncated is True


def test_delivery_stamp_counts_only_the_target_and_stays_sticky():
    admitted = NOW - TARGET_SECONDS
    assert delivery_stamp({'enqueued_at': admitted}, NOW) == (NOW, True)
    assert delivery_stamp({'enqueued_at': admitted - 1}, NOW) == (NOW, False)
    # A replay cannot move an earlier acknowledge later or clear an in-target stamp.
    assert delivery_stamp(
        {'enqueued_at': admitted, 'delivered_at': NOW - 10, 'delivered_in_target': True}, NOW + 60
    ) == (NOW - 10, True)
    # A missing or malformed admission clock is not a delivered-in-target unit.
    assert delivery_stamp({}, NOW) == (NOW, False)
    assert delivery_stamp({'enqueued_at': True}, NOW) == (NOW, False)


def test_cells_bound_route_and_language():
    rows = [
        {'stt_route': {'stt_route': 'provider'}, 'projection_binding': {'language': 'ja'}, 'delivered_in_target': True},
        {'policy': {'stt_route': 'provider'}, 'projection_binding': {'language': 'ja-JP'}},
        {'policy': {'stt_route': 'parakeet'}, 'projection_binding': {'language': 'en'}, 'delivered_in_target': True},
        {'policy': {'stt_route': 'parakeet'}, 'projection_binding': {'language': 'en-GB'}},
        {'projection_binding': {'language': 'zz'}, 'delivered_in_target': True},
        {'projection_binding': {}},
        {},
    ]
    counted = module.cells(rows)
    assert counted[('provider', 'ja')] == (2, 1)
    assert counted[('parakeet', 'en')] == (2, 1)
    assert counted[('unknown', 'other')] == (1, 1)
    assert counted[('unknown', 'unknown')] == (2, 0)
    assert module.share(2, 1) == 0.5
    assert module.share(0, 0) is None


def test_language_vocabulary_is_the_deployed_route_tables():
    from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL

    deployed = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] | MODULATE_SUPPORTED_LANGUAGES
    assert module.LANGUAGES == deployed


def test_alarm_needs_volume_baseline_and_an_unfolded_language():
    baselines = {('provider', 'ja'): 0.98, ('provider', 'ko'): 0.98, ('parakeet', 'en'): 0.99}
    cells = {
        ('provider', 'ja'): (100, 0),
        ('provider', 'ko'): (10, 0),  # under the volume floor
        ('parakeet', 'en'): (500, 490),  # 0.98, above the discounted baseline
        ('unknown', 'other'): (100, 0),  # folded labels are never alarmed
        ('provider', 'th'): (100, 0),  # no observed baseline
    }
    assert module.alarm_cells(cells, baselines) == [('provider', 'ja', 0.0, 0.98)]


@pytest.fixture
def sampler(monkeypatch):
    clock = [0.0]
    monkeypatch.delenv('BATCH_PIPELINE_DELIVERED_SHARE_ENABLED', raising=False)
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'time', lambda: NOW)
    registry = CollectorRegistry()
    return module.DeliveredShare(registry), registry, clock


def samples(registry):
    return {
        (s.name.removeprefix(module.PREFIX), tuple(sorted(s.labels.items()))): s.value
        for metric in registry.collect()
        for s in metric.samples
    }


def store(client):
    return SimpleNamespace(client=client, namespace='batch_pipeline_dev')


def test_sample_publishes_counts_ratio_and_age(sampler):
    rows = [
        {
            'state': 'committed',
            'enqueued_at': NOW - 400,
            'projection_binding': {'language': 'ja'},
            'policy': {'stt_route': 'provider'},
            'delivered_in_target': True,
        },
        {
            'state': 'vendor_held',
            'enqueued_at': NOW - 400,
            'projection_binding': {'language': 'ja'},
            'policy': {'stt_route': 'provider'},
        },
    ]
    sampler, registry, _ = sampler
    sampler.refresh(store(PageClient(rows)))
    assert samples(registry) == {
        ('admitted_units', (('language', 'ja'), ('route', 'provider'))): 2,
        ('units', (('language', 'ja'), ('route', 'provider'))): 1,
        ('ratio', (('language', 'ja'), ('route', 'provider'))): 0.5,
        ('truncated', ()): 0,
        ('sample_age_seconds', ()): 0,
    }


def test_empty_cohort_publishes_no_ratio(sampler):
    sampler, registry, _ = sampler
    sampler.refresh(store(PageClient()))
    assert samples(registry) == {
        ('truncated', ()): 0,
        ('sample_age_seconds', ()): 0,
    }


def test_failed_page_clears_counts_and_ratio_but_keeps_age(sampler):
    sampler, registry, clock = sampler
    sampler.refresh(
        store(
            PageClient(
                [
                    {
                        'state': 'ready',
                        'enqueued_at': NOW - 400,
                        'projection_binding': {'language': 'ja'},
                        'policy': {'stt_route': 'provider'},
                        'delivered_in_target': True,
                    }
                ]
            )
        )
    )
    assert ('ratio', (('language', 'ja'), ('route', 'provider'))) in samples(registry)
    clock[0] += 300
    sampler.refresh(store(PageClient(fail=True)))
    cleared = samples(registry)
    assert ('ratio', (('language', 'ja'), ('route', 'provider'))) not in cleared
    assert cleared[('sample_age_seconds', ())] == 300


def test_counts_expire_when_supervision_stops(sampler):
    sampler, registry, clock = sampler
    sampler.refresh(
        store(
            PageClient(
                [
                    {
                        'state': 'ready',
                        'enqueued_at': NOW - 400,
                        'projection_binding': {'language': 'ja'},
                        'policy': {'stt_route': 'provider'},
                        'delivered_in_target': True,
                    }
                ]
            )
        )
    )
    clock[0] += module.FRESH_SECONDS
    stale = samples(registry)
    assert ('ratio', (('language', 'ja'), ('route', 'provider'))) not in stale
    assert stale[('sample_age_seconds', ())] == module.FRESH_SECONDS


def test_follower_deactivation_hides_every_gauge(sampler):
    sampler, registry, _ = sampler
    sampler.refresh(store(PageClient()))
    sampler.deactivate()
    assert samples(registry) == {}


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no'])
def test_kill_switch_stops_the_page_and_hides_the_gauges(sampler, monkeypatch, value):
    sampler, registry, _ = sampler
    monkeypatch.setenv('BATCH_PIPELINE_DELIVERED_SHARE_ENABLED', value)
    client = PageClient()
    sampler.refresh(store(client))
    assert client.calls == []
    assert samples(registry) == {}


def test_refresh_is_throttled_to_the_sample_interval(sampler):
    sampler, _, clock = sampler
    client = PageClient()
    sampler.refresh(store(client))
    sampler.refresh(store(client))
    assert len(client.calls) == 1
    clock[0] += module.SAMPLE_SECONDS
    sampler.refresh(store(client))
    assert len(client.calls) == 2
