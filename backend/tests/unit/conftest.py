"""Shared unit-test fallbacks for optional import-time dependencies."""

import atexit
from contextlib import contextmanager
import importlib.util
import os
import shutil
import tempfile

# Unit tests never build a real Google client from the developer's or agent's ambient credentials:
# an unstubbed Firestore read would reach whatever project those credentials grant (prod read-only
# on agent hosts). ADC points at a file google-auth rejects without any network call, and gcloud
# gets an empty config, so an accidental client fails at once instead of authenticating.
# Integration suites keep their configured credentials; emulator-backed runs are left alone.
# Every pytest process (each xdist worker included) makes its own stub dir and removes it at exit.
if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
    _no_credentials_dir = tempfile.mkdtemp(prefix='omi-unit-no-adc-')
    atexit.register(shutil.rmtree, _no_credentials_dir, ignore_errors=True)
    _no_credentials_file = os.path.join(_no_credentials_dir, 'adc.json')
    with open(_no_credentials_file, 'w', encoding='utf-8') as handle:
        handle.write('{"type": "omi_unit_tests_have_no_google_credentials"}')
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _no_credentials_file
    os.environ['CLOUDSDK_CONFIG'] = _no_credentials_dir
    os.environ.pop('GOOGLE_CLOUD_PROJECT', None)

import sys
import types
from unittest.mock import MagicMock

import pytest

# Capture the pure resolver boundary before legacy suites replace package objects.
import config.rollout_cohorts as _rollout_cohorts


@pytest.fixture(scope='session', autouse=True)
def legacy_offline_spend_policy():
    # Component fixtures have fake storage/providers but no funded subscription.
    # Keep billing admission explicit: the offline spend contract suite unsets
    # this value to test the production default; boundary tests enable it.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
        yield


from tests.unit.memory_import_isolation import (  # noqa: F401 — re-export for test modules
    AutoMockModule as _AutoMockModule,
    install_database_client_stub,
    restore_sys_modules,
    snapshot_sys_modules,
)

# Cache the real google.api_core.exceptions in sys.modules before any test stubs the `google`
# namespace at module scope. Modules that catch google.api_core exceptions (database/users.py,
# database/advice.py, ...) then import cleanly regardless of test-file collection order, instead of
# failing with ModuleNotFoundError once a later-collected test has replaced `google` with a stub.
import google.api_core.exceptions  # noqa: F401,E402


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
    prometheus_client.disable_created_metrics = lambda: None
    prometheus_client.start_http_server = lambda *args, **kwargs: (MagicMock(), MagicMock())

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


@pytest.fixture(autouse=True)
def _reset_live_stt_fleet_health():
    """Reset the module-level live STT fleet-health singleton in place.

    Account quarantine now persists in the shared singleton even while the
    cost-routing kill switch is off (a mode-independent hard exclusion), so a
    test that records a synthetic bench must not withdraw providers from
    later tests. The reset swaps instance state in place because sibling
    modules (live_chain, streaming, live_session) keep import-time references
    to this exact object; rebinding the module attribute would leave them
    sharing the polluted instance.
    """
    import sys

    if 'utils.stt.live_health' not in sys.modules:
        # Unrelated shards must not pay this module's import chain.
        yield
        return
    from utils.stt import live_health

    shared = live_health.health
    fresh = type(shared)()
    with shared._lock:
        vars(shared).update({key: value for key, value in vars(fresh).items() if key != '_lock'})
    if 'utils.stt.streaming' in sys.modules:
        # Clear both breaker evidence and its identity latch so the next test
        # starts with closed family circuits, including account quarantine.
        from utils.stt import streaming

        # Import-isolation stubs register a bare streaming module. They have no
        # family circuits to reset, and touching the missing lock fails the next file.
        lock = getattr(streaming, '_family_circuits_lock', None)
        circuits = (
            getattr(streaming, '_parakeet_circuit', None),
            getattr(streaming, '_deepgram_circuit', None),
            getattr(streaming, '_modulate_circuit', None),
            getattr(streaming, '_soniox_circuit', None),
        )
        identity = getattr(streaming, '_family_circuits_identity', None)
        if lock is None or identity is None or any(circuit is None for circuit in circuits):
            yield
            return
        with lock:
            for circuit in (
                streaming._parakeet_circuit,
                streaming._deepgram_circuit,
                streaming._modulate_circuit,
                streaming._soniox_circuit,
            ):
                circuit.reset()
            streaming._family_circuits_identity.clear()
    yield


@pytest.fixture(autouse=True)
def isolated_dream_dynamic_control(monkeypatch):
    """Unit tests inject flag state instead of reading remote operator config."""
    from config import dream_control

    monkeypatch.setattr(dream_control, '_until', float('inf'))
    monkeypatch.setattr(dream_control, '_allowed', True)
    monkeypatch.setattr(dream_control, '_refreshing', False)


@pytest.fixture(autouse=True)
def empty_rollout_cohorts(monkeypatch):
    """Inject an empty store without importing SDKs or scheduling real reads."""
    cohorts = _rollout_cohorts

    def membership(uid, name, *, legacy_members=None, legacy_all=False):
        return cohorts.legacy_membership(uid, name, legacy_members=legacy_members, legacy_all=legacy_all)

    def members(name):
        return tuple(
            sorted({item.strip() for item in cohorts.COHORT_ENVS[name]().split(',') if cohorts.valid_uid(item.strip())})
        )

    async def warm(_uid):
        return None

    monkeypatch.setattr(cohorts, '_membership_resolver', membership)
    monkeypatch.setattr(cohorts, '_members_resolver', members)
    monkeypatch.setattr(cohorts, '_load_resolver', lambda _uid: None)
    monkeypatch.setattr(cohorts, '_warm_resolver', warm)
