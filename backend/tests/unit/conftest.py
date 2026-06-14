"""Shared unit-test fallbacks for optional import-time dependencies."""

from contextlib import contextmanager
import importlib.util
import sys
import types


def _install_prometheus_client_stub():
    if 'prometheus_client' in sys.modules:
        return
    if importlib.util.find_spec('prometheus_client') is not None:
        return

    prometheus_client = types.ModuleType('prometheus_client')

    class _Registry:
        def __init__(self):
            self._names_to_collectors = {}

    registry = _Registry()

    @contextmanager
    def _timer():
        yield

    class _Value:
        def __init__(self):
            self._amount = 0

        def get(self):
            return self._amount

        def inc(self, amount):
            self._amount += amount

        def set(self, value):
            self._amount = value

    class _Metric:
        def __init__(self, name, documentation, labelnames=(), **kwargs):
            self._name = name
            self._documentation = documentation
            self._labelnames = tuple(labelnames or ())
            self._kwargs = kwargs
            self._value = _Value()
            self._register(name)

        def _register(self, name):
            names = [name]
            if name.endswith('_total'):
                names.append(name[: -len('_total')])
            for metric_name in names:
                existing = registry._names_to_collectors.get(metric_name)
                if existing is not None and existing is not self:
                    raise ValueError(f'Duplicated timeseries in CollectorRegistry: {metric_name}')
            for metric_name in names:
                registry._names_to_collectors[metric_name] = self

        def labels(self, *args, **kwargs):
            return self

        def inc(self, amount=1):
            self._value.inc(amount)

        def dec(self, amount=1):
            self._value.inc(-amount)

        def set(self, value):
            self._value.set(value)

        def observe(self, value):
            self._value.set(value)

        def time(self):
            return _timer()

    prometheus_client.Counter = _Metric
    prometheus_client.Gauge = _Metric
    prometheus_client.Histogram = _Metric
    prometheus_client.REGISTRY = registry
    prometheus_client.CONTENT_TYPE_LATEST = 'text/plain; version=0.0.4; charset=utf-8'
    prometheus_client.generate_latest = lambda registry=None: b''

    sys.modules['prometheus_client'] = prometheus_client


_install_prometheus_client_stub()
