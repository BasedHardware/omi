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
