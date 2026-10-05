from importlib import reload
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, Histogram

from utils import metrics_smart_merge


@pytest.mark.parametrize(
    'registry',
    [SimpleNamespace(), SimpleNamespace(_names_to_collectors=MagicMock())],
    ids=['missing', 'nonmapping'],
)
def test_reuse_or_create_calls_factory_when_registry_namespace_uninspectable(monkeypatch, registry):
    monkeypatch.setattr(metrics_smart_merge, 'REGISTRY', registry)
    factory = MagicMock()
    result = metrics_smart_merge._reuse_or_create(factory, 'omi_test_smart_merge_total', 'test', ['outcome'])
    factory.assert_called_once_with('omi_test_smart_merge_total', 'test', ['outcome'])
    assert result is factory.return_value
    if hasattr(registry, '_names_to_collectors'):
        registry._names_to_collectors.get.assert_not_called()


def test_reuse_or_create_returns_existing_identical_collector(monkeypatch):
    registry = CollectorRegistry()
    counter = Counter('omi_test_smart_merge_existing_total', 'test', ['outcome'], registry=registry)
    monkeypatch.setattr(metrics_smart_merge, 'REGISTRY', registry)
    assert (
        metrics_smart_merge._reuse_or_create(Counter, 'omi_test_smart_merge_existing_total', 'test', ['outcome'])
        is counter
    )


def test_reuse_or_create_rejects_label_mismatch(monkeypatch):
    registry = CollectorRegistry()
    Counter('omi_test_smart_merge_existing_total', 'test', ['outcome'], registry=registry)
    monkeypatch.setattr(metrics_smart_merge, 'REGISTRY', registry)
    with pytest.raises(ValueError, match='different shape'):
        metrics_smart_merge._reuse_or_create(Counter, 'omi_test_smart_merge_existing_total', 'test', ['reason'])


def test_reuse_or_create_rejects_factory_type_mismatch(monkeypatch):
    registry = CollectorRegistry()
    Counter('omi_test_smart_merge_existing_total', 'test', ['outcome'], registry=registry)
    monkeypatch.setattr(metrics_smart_merge, 'REGISTRY', registry)
    with pytest.raises(ValueError, match='different shape'):
        metrics_smart_merge._reuse_or_create(Histogram, 'omi_test_smart_merge_existing_total', 'test', ['outcome'])


def test_overlap_counter_survives_reload_and_bounds_labels(monkeypatch):
    counter = metrics_smart_merge.OMI_CONVERSATION_SMART_MERGE_PREDECESSOR_OVERLAP_TOTAL
    reload(metrics_smart_merge)
    reload(metrics_smart_merge)
    assert metrics_smart_merge.OMI_CONVERSATION_SMART_MERGE_PREDECESSOR_OVERLAP_TOTAL is counter
    assert counter._labelnames == ('mode', 'skipped')
    seen = []
    monkeypatch.setattr(counter, 'labels', lambda **kw: seen.append(kw) or SimpleNamespace(inc=lambda: None))
    metrics_smart_merge.record_conversation_smart_merge_predecessor_overlap('merge', 1)
    metrics_smart_merge.record_conversation_smart_merge_predecessor_overlap('shadow', 3)
    metrics_smart_merge.record_conversation_smart_merge_predecessor_overlap('untrusted', 999)
    assert seen == [
        {'mode': 'merge', 'skipped': '1'},
        {'mode': 'shadow', 'skipped': '3'},
        {'mode': 'other', 'skipped': 'other'},
    ]
