"""Bucket-only summaries must survive counter export without an invented sum."""

import pytest
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

from config.fleet_telemetry import registry
from utils.observability.fleet import FleetHistograms


@pytest.mark.parametrize('name', list(registry()['histograms']))
def test_bucket_only_summary_exports_complete_independent_counters(name):
    collector = FleetHistograms()
    edges = registry()['histograms'][name]['buckets']
    deltas = [{'le': edge, 'count': index + 1} for index, edge in enumerate(edges)]
    collector.add(name, 'ios', 'stable', deltas)
    collector.add(name, 'ios', 'stable', deltas)
    collector.add(name, 'linux', 'dev', deltas)
    isolated = CollectorRegistry()
    isolated.register(collector)
    wire = generate_latest(isolated).decode()
    base = 'omi_client_' + name
    # Histogram conversion requires a sum absent from the beacon schema.
    # Independent counter metadata prevents the whole distribution being dropped.
    assert f'# TYPE {base}_bucket_total counter\n' in wire
    assert f'# TYPE {base}_count_total counter\n' in wire
    families = list(text_string_to_metric_families(wire))
    assert len(families) == 2
    assert all(family.type == 'counter' for family in families)
    samples = [sample for family in families for sample in family.samples]
    assert len(samples) == 2 * (len(edges) + 1)
    assert {sample.name for sample in samples} == {base + '_bucket_total', base + '_count_total'}
    for platform, channel, multiplier in (('ios', 'stable', 2), ('linux', 'dev', 1)):
        subset = [s for s in samples if s.labels['platform'] == platform and s.labels['build_channel'] == channel]
        buckets = [s for s in subset if s.name.endswith('_bucket_total')]
        assert [(s.labels['le'], s.value) for s in buckets] == [
            (str(edge), multiplier * (index + 1)) for index, edge in enumerate(edges)
        ]
        count = next(s for s in subset if s.name.endswith('_count_total'))
        assert count.value == multiplier * len(edges)
        assert set(count.labels) == {'platform', 'build_channel'}
        assert all(set(s.labels) == {'platform', 'build_channel', 'le'} for s in buckets)


def test_all_registered_bucket_counters_have_the_reviewed_series_bound():
    collector = FleetHistograms()
    spec = registry()
    for name, histogram in spec['histograms'].items():
        for platform in spec['platforms']:
            for channel in spec['build_channels']:
                collector.add(name, platform, channel, [{'le': edge, 'count': 1} for edge in histogram['buckets']])
    families = list(collector.collect())
    expected = sum(len(h['buckets']) + 1 for h in spec['histograms'].values())
    expected *= len(spec['platforms']) * len(spec['build_channels'])
    assert len(families) == 2 * len(spec['histograms'])
    assert sum(len(family.samples) for family in families) == expected
    assert all(family.type == 'counter' for family in families)
