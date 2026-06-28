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


def _install_redis_stub():
    if 'redis' in sys.modules:
        return
    if importlib.util.find_spec('redis') is not None:
        return

    redis_module = types.ModuleType('redis')

    class _Pipeline:
        def __init__(self, client):
            self._client = client
            self._results = []

        def __getattr__(self, name):
            def _call(*args, **kwargs):
                result = getattr(self._client, name)(*args, **kwargs)
                self._results.append(result)
                return self

            return _call

        def execute(self):
            results = list(self._results)
            self._results.clear()
            return results

    class _Redis:
        def __init__(self, *args, **kwargs):
            self._store = {}

        def get(self, key):
            return self._store.get(key)

        def set(self, key, value, ex=None, nx=False, **kwargs):
            if nx and key in self._store:
                return None
            self._store[key] = value
            return True

        def delete(self, *keys):
            deleted = 0
            for key in keys:
                deleted += int(key in self._store)
                self._store.pop(key, None)
            return deleted

        def expire(self, key, ttl):
            return key in self._store

        def ttl(self, key):
            return -1 if key in self._store else -2

        def incr(self, key, amount=1):
            return self.incrby(key, amount)

        def incrby(self, key, amount=1):
            value = int(self._store.get(key, 0)) + amount
            self._store[key] = value
            return value

        def pipeline(self, *args, **kwargs):
            return _Pipeline(self)

        def eval(self, *args, **kwargs):
            return [0, 0]

        def __getattr__(self, name):
            def _noop(*args, **kwargs):
                return None

            return _noop

    redis_module.Redis = _Redis
    redis_module.ConnectionError = ConnectionError
    redis_module.exceptions = types.SimpleNamespace(ConnectionError=ConnectionError, RedisError=Exception)

    sys.modules['redis'] = redis_module


def _install_cachetools_stub():
    if 'cachetools' in sys.modules:
        return
    if importlib.util.find_spec('cachetools') is not None:
        return

    cachetools_module = types.ModuleType('cachetools')

    class TTLCache(dict):
        def __init__(self, maxsize, ttl, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.maxsize = maxsize
            self.ttl = ttl

        def __setitem__(self, key, value):
            if len(self) >= self.maxsize and key not in self:
                self.pop(next(iter(self)))
            super().__setitem__(key, value)

    cachetools_module.TTLCache = TTLCache
    sys.modules['cachetools'] = cachetools_module


_install_prometheus_client_stub()
_install_redis_stub()
_install_cachetools_stub()
