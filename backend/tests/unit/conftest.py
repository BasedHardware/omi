"""Shared unit-test fallbacks for optional import-time dependencies."""

import asyncio
import importlib.util
import os
import sys
import types
from contextlib import contextmanager

import pytest

# ---------------------------------------------------------------------------
# sys.modules isolation — see issue #8661
# ---------------------------------------------------------------------------
_module_snapshots = {}
_module_stubs = {}

_C_EXT_PREFIXES = frozenset(
    {
        'google.protobuf',
        'google._upb',
        'grpc',
        '_cffi_backend',
        '_brotli',
        'zstandard',
        'charset_normalizer',
        'xxhash',
        'ujson',
        'numpy',
        'yaml',
    }
)

_UNSAFE_TOPS = frozenset({'google', 'grpc', 'proto'})

_ISOLATE_PREFIXES = frozenset({'database', 'dependencies', 'models', 'routers', 'utils'})


def _is_c_extension(name):
    for prefix in _C_EXT_PREFIXES:
        if name == prefix or name.startswith(prefix + '.'):
            return True
    return False


def _should_isolate(name):
    return name.split('.', 1)[0] in _ISOLATE_PREFIXES


@pytest.hookimpl(tryfirst=True)
def pytest_collectstart(collector):
    if isinstance(collector, pytest.Module):
        modules = {}
        paths = {}
        for k, v in list(sys.modules.items()):
            modules[k] = v
            p = getattr(v, '__path__', None)
            if p is not None:
                paths[k] = list(p)
        _module_snapshots[collector.nodeid] = (modules, paths)


@pytest.hookimpl(trylast=True)
def pytest_collectreport(report):
    entry = _module_snapshots.pop(report.nodeid, None)
    if entry is None:
        return
    saved, saved_paths = entry

    stubs = {}
    for k, v in list(sys.modules.items()):
        if _is_c_extension(k):
            continue
        if k not in saved:
            stubs[k] = v
        elif saved[k] is not v:
            stubs[k] = v
    if stubs:
        _module_stubs[report.nodeid] = stubs

    added = sorted([k for k in sys.modules if k not in saved], key=lambda k: -k.count('.'))
    for k in added:
        mod = sys.modules.pop(k, None)
        if mod is not None and '.' in k:
            parent_name, attr_name = k.rsplit('.', 1)
            parent = saved.get(parent_name)
            if parent is not None and getattr(parent, attr_name, None) is mod:
                try:
                    delattr(parent, attr_name)
                except AttributeError:
                    pass
    for k, mod in saved.items():
        cur = sys.modules.get(k)
        if cur is not mod:
            sys.modules[k] = mod
            if '.' in k:
                parent_name, attr_name = k.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr_name, mod)
    for k, orig_path in saved_paths.items():
        mod = sys.modules.get(k)
        if mod is not None and list(getattr(mod, '__path__', [])) != orig_path:
            mod.__path__ = orig_path


_baseline_backend = {}
_baseline_backend_paths = {}
for _k, _v in list(sys.modules.items()):
    if _should_isolate(_k):
        _baseline_backend[_k] = _v
        _p = getattr(_v, '__path__', None)
        if _p is not None:
            _baseline_backend_paths[_k] = list(_p)

_SENTINEL = object()


@pytest.fixture(autouse=True, scope="module")
def _auto_reinstall_module_stubs(request):
    """Reinstall sys.modules stubs from collection, full isolation between modules."""
    nodeid = os.path.relpath(str(request.fspath), str(request.config.rootpath))
    stubs = _module_stubs.get(nodeid)

    prom = sys.modules.get('prometheus_client')
    if prom is not None and hasattr(prom, 'REGISTRY'):
        prom.REGISTRY._names_to_collectors.clear()

    non_backend_pre = {}
    for k, v in list(sys.modules.items()):
        if not _should_isolate(k) and not _is_c_extension(k):
            non_backend_pre[k] = v

    if stubs is not None:
        for k in sorted(stubs, key=lambda x: x.count('.')):
            top = k.split('.', 1)[0]
            if top in _UNSAFE_TOPS:
                continue
            sys.modules[k] = stubs[k]
            if '.' in k:
                parent_name, attr_name = k.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr_name, stubs[k])

    yield

    for k in sorted(
        [k for k in sys.modules if _should_isolate(k) and k not in _baseline_backend],
        key=lambda k: -k.count('.'),
    ):
        sys.modules.pop(k, None)
    for k, mod in _baseline_backend.items():
        cur = sys.modules.get(k)
        if cur is not mod:
            sys.modules[k] = mod
            if '.' in k:
                parent_name, attr_name = k.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr_name, mod)
    for k, orig_path in _baseline_backend_paths.items():
        mod = sys.modules.get(k)
        if mod is not None and list(getattr(mod, '__path__', [])) != orig_path:
            mod.__path__ = orig_path

    for k in sorted(
        [
            k
            for k in sys.modules
            if not _should_isolate(k) and not _is_c_extension(k) and k.split('.', 1)[0] not in _UNSAFE_TOPS
        ],
        key=lambda k: -k.count('.'),
    ):
        orig = non_backend_pre.get(k, _SENTINEL)
        if orig is _SENTINEL:
            sys.modules.pop(k, None)
        elif sys.modules.get(k) is not orig:
            sys.modules[k] = orig

    policy = asyncio.get_event_loop_policy()
    try:
        policy.get_event_loop()
    except RuntimeError:
        policy.set_event_loop(asyncio.new_event_loop())


from tests.unit._sysmodules_helpers import stub_modules  # noqa: F401


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
