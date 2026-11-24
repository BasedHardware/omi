"""Keep collectors registered by fixture-scoped imports out of the default registry."""

from contextlib import contextmanager

import pytest
from prometheus_client import REGISTRY
from prometheus_client.registry import CollectorRegistry


@contextmanager
def isolated_prometheus():
    registry = CollectorRegistry()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(REGISTRY, 'register', registry.register)
        yield
