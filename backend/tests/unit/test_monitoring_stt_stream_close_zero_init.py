"""Zero scrapes make the first provider close observable to increase()."""

import json
import re
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry, Counter

from utils.stt import stream_close


@pytest.fixture
def registry(monkeypatch):
    registry = CollectorRegistry()
    counter = Counter(
        'omi_stt_stream_close_total',
        'Isolated stream-close test counter',
        stream_close.OMI_STT_STREAM_CLOSE_TOTAL._labelnames,
        registry=registry,
    )
    monkeypatch.setattr(stream_close, 'OMI_STT_STREAM_CLOSE_TOTAL', counter)
    return registry


def _samples(registry):
    return [
        sample
        for family in registry.collect()
        for sample in family.samples
        if sample.name == 'omi_stt_stream_close_total'
    ]


def test_every_bounded_child_exists_at_zero(registry):
    assert not _samples(registry)
    stream_close.initialize_stt_stream_close_children()
    samples = _samples(registry)
    assert {(s.labels['provider'], s.labels['reason']) for s in samples} == {
        (provider, reason)
        for provider in stream_close.STT_STREAM_CLOSE_PROVIDERS | {'unknown'}
        for reason in stream_close.STT_STREAM_CLOSE_REASONS
    }
    assert all(s.value == 0 for s in samples)


def test_first_soniox_budget_close_has_observable_increase(registry):
    stream_close.initialize_stt_stream_close_children()
    labels = {'provider': 'soniox', 'reason': stream_close.PROVIDER_BUDGET_EXHAUSTED}
    before = registry.get_sample_value('omi_stt_stream_close_total', labels)
    assert before == 0  # Inspect exposition without creating a child via labels().
    stream_close.record_stt_stream_close(**labels)
    after = registry.get_sample_value('omi_stt_stream_close_total', labels)
    assert after == 1
    # Both scrapes are inside the 5m window (0, 300]. A positive monotonic
    # delta gives a positive increase after extrapolation. Without the zero
    # scrape there is only one sample, which increase() cannot use. This
    # fixture checks the input delta, not Prometheus resets/extrapolation.
    scrapes = [(15, before), (285, after)]
    assert scrapes[-1][1] - scrapes[0][1] > 0
    stream_close.initialize_stt_stream_close_children()
    assert registry.get_sample_value('omi_stt_stream_close_total', labels) == 1


def test_all_alert_close_selectors_match_zero_children(registry):
    stream_close.initialize_stt_stream_close_children()
    samples = _samples(registry)
    alerts = Path(__file__).resolve().parents[2] / 'charts/monitoring/alerts'
    checked = 0
    for path in alerts.glob('*.json'):
        for rule in json.loads(path.read_text()):
            for query in rule.get('data', []):
                expr = query.get('model', {}).get('expr', '')
                for selector in re.findall(r'omi_stt_stream_close_total\{([^{}]*)\}', expr):
                    matchers = re.findall(r'(provider|reason)\s*(=~|!~|!=|=)\s*"([^"]*)"', selector)

                    def matches(sample):
                        for label, operator, value in matchers:
                            actual = sample.labels[label]
                            equal = bool(re.fullmatch(value, actual)) if '~' in operator else actual == value
                            if equal != (operator in ('=', '=~')):
                                return False
                        return True

                    assert any(matches(s) and s.value == 0 for s in samples), (rule['uid'], selector)
                    checked += 1
    assert checked >= 4


def test_initializer_never_raises(monkeypatch):
    def fail(**labels):
        raise RuntimeError('collector unavailable')

    monkeypatch.setattr(stream_close.OMI_STT_STREAM_CLOSE_TOTAL, 'labels', fail)
    stream_close.initialize_stt_stream_close_children()
