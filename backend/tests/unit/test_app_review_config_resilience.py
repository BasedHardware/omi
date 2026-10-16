"""app_review_config must validate its platform id and fail open on backend errors.

`backend/database/app_review_config.py` turns a caller-supplied platform into a
Firestore document ID and is reached from hot read paths (e.g. `GET /v1/users/me`
via `should_hide_subscription_ui`). Before this change:

* an unsafe platform value was passed straight into the document path,
* a transient Firestore error, a failing cache, or a malformed `hidden_versions`
  entry propagated out of the module and 500'd the request.

This test imports the module with its Firestore / cache / announcements
collaborators stubbed (no network, no Redis, no pydantic) and drives it with
injected fakes. Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_app_review_config_resilience.py
"""

import os
import sys
import types
from typing import Any

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# --- stub the heavy collaborators before importing the module under test -----


class _FakeCache:
    """Minimal stand-in for InMemoryCacheManager."""

    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.deleted: list[str] = []
        self.fetched = 0

    def get_or_fetch(self, key: str, fetch: Any, ttl: Any = None) -> Any:
        if self.raises:
            raise RuntimeError('cache backend down')
        self.fetched += 1
        return fetch()

    def delete(self, key: str) -> None:
        if self.raises:
            raise RuntimeError('cache backend down')
        self.deleted.append(key)


_cache_holder: dict[str, _FakeCache] = {'cache': _FakeCache()}


def _get_memory_cache() -> _FakeCache:
    return _cache_holder['cache']


def _compare_versions(v1: Any, v2: Any) -> int:
    return _compare_versions.impl(v1, v2)


_compare_versions.impl = lambda a, b: 0 if a == b else (-1 if a < b else 1)  # type: ignore[attr-defined]


def _install_stubs() -> None:
    db_mod = types.ModuleType('database._client')
    db_mod.db = types.SimpleNamespace()  # type: ignore[attr-defined]
    sys.modules['database._client'] = db_mod

    ann_mod = types.ModuleType('database.announcements')
    ann_mod.compare_versions = _compare_versions  # type: ignore[attr-defined]
    sys.modules['database.announcements'] = ann_mod

    cache_mod = types.ModuleType('database.cache')
    cache_mod.get_memory_cache = _get_memory_cache  # type: ignore[attr-defined]
    sys.modules['database.cache'] = cache_mod


_install_stubs()

from database import app_review_config as arc  # noqa: E402

# --- fakes for the Firestore surface ----------------------------------------


class _Doc:
    def __init__(self, data: Any, exists: bool = True) -> None:
        self._data = data
        self.exists = exists

    def to_dict(self) -> Any:
        return self._data


class _Client:
    def __init__(self, doc: Any = None, *, raises: bool = False) -> None:
        self._doc = doc
        self.raises = raises
        self.requested_ids: list[str] = []

    def collection(self, name: str) -> '_Client':
        return self

    def document(self, doc_id: str) -> '_Client':
        self.requested_ids.append(doc_id)
        return self

    def get(self) -> _Doc:
        if self.raises:
            raise RuntimeError('firestore unavailable')
        return self._doc if self._doc is not None else _Doc(None, exists=False)


def _reset(cache: _FakeCache | None = None) -> _FakeCache:
    _cache_holder['cache'] = cache if cache is not None else _FakeCache()
    _compare_versions.impl = lambda a, b: 0 if a == b else (-1 if a < b else 1)  # type: ignore[attr-defined]
    return _cache_holder['cache']


class _serve_config:
    """Patch the module's bound ``get_memory_cache`` to serve ``client``."""

    def __init__(self, client: _Client) -> None:
        self._client = client
        self._original = arc.get_memory_cache

    def __enter__(self) -> None:
        client = self._client

        class _Cache(_FakeCache):
            def get_or_fetch(self, key: str, fetch: Any, ttl: Any = None) -> Any:
                return arc._fetch_review_config('ios', firestore_client=client)

        arc.get_memory_cache = lambda: _Cache()  # type: ignore[assignment]

    def __exit__(self, *exc: Any) -> None:
        arc.get_memory_cache = self._original  # type: ignore[assignment]


# --- platform validation -----------------------------------------------------


def test_clean_platform_normalizes_supported_values():
    assert arc._clean_platform('ios') == 'ios'
    assert arc._clean_platform('IOS') == 'ios'
    assert arc._clean_platform('  macos  ') == 'macos'


def test_clean_platform_rejects_unsafe_values():
    assert arc._clean_platform('') is None
    assert arc._clean_platform('   ') is None
    assert arc._clean_platform('x' * (arc._MAX_PLATFORM_LENGTH + 1)) is None
    assert arc._clean_platform('io/s') is None
    assert arc._clean_platform('io\\s') is None
    assert arc._clean_platform(None) is None
    assert arc._clean_platform(123) is None


def test_should_hide_ignores_unsafe_platform_without_touching_firestore():
    _reset()
    client = _Client(doc=_Doc({'reviewer_uids': ['uid1']}))
    assert arc.should_hide_subscription_ui('uid1', '../users/uid1', '1.0.0') is False
    assert client.requested_ids == [], 'unsafe platform must not reach Firestore'


def test_should_hide_ignores_unsupported_platform():
    _reset()
    assert arc.should_hide_subscription_ui('uid1', 'android', '1.0.0') is False


# --- fail-open behaviour -----------------------------------------------------


def test_fetch_fails_open_on_firestore_error():
    _reset()
    assert arc._fetch_review_config('ios', firestore_client=_Client(raises=True)) == {}


def test_get_review_config_returns_empty_on_firestore_error():
    _reset()
    assert arc.get_review_config('ios', firestore_client=_Client(raises=True)) == {}


def test_get_review_config_falls_back_when_cache_raises():
    _reset(_FakeCache(raises=True))
    client = _Client(doc=_Doc({'hidden_versions': ['1.0.5']}))
    # Cache blows up, but the direct fetch still returns the real config.
    assert arc.get_review_config('ios', firestore_client=client) == {'hidden_versions': ['1.0.5']}


def test_get_review_config_returns_empty_for_unsafe_platform():
    cache = _reset()
    assert arc.get_review_config('io/s') == {}
    assert cache.fetched == 0, 'unsafe platform must not hit the cache'


def test_get_review_config_coerces_non_dict_payload_to_empty():
    _reset()
    assert arc.get_review_config('ios', firestore_client=_Client(doc=_Doc(['not', 'a', 'dict']))) == {}


# --- cache invalidation ------------------------------------------------------


def test_invalidate_review_config_cache_deletes_prefixed_key():
    cache = _reset()
    arc.invalidate_review_config_cache('IOS')
    assert cache.deleted == [f'{arc._CACHE_KEY_PREFIX}ios']


def test_invalidate_review_config_cache_ignores_unsafe_platform():
    cache = _reset()
    arc.invalidate_review_config_cache('io/s')
    assert cache.deleted == []


def test_invalidate_review_config_cache_swallows_cache_errors():
    _reset(_FakeCache(raises=True))
    arc.invalidate_review_config_cache('ios')  # must not raise


# --- decision logic ----------------------------------------------------------


def test_should_hide_for_reviewer_uid():
    _reset()
    client = _Client(doc=_Doc({'reviewer_uids': ['uid1']}))
    with _serve_config(client):
        assert arc.should_hide_subscription_ui('uid1', 'ios', None) is True
        assert arc.should_hide_subscription_ui('uid2', 'ios', None) is False


def test_should_hide_for_hidden_version():
    _reset()
    client = _Client(doc=_Doc({'hidden_versions': ['1.0.531']}))
    with _serve_config(client):
        assert arc.should_hide_subscription_ui('', 'ios', '1.0.531') is True
        assert arc.should_hide_subscription_ui('', 'ios', '1.0.532') is False


def test_malformed_hidden_version_does_not_crash():
    _reset()
    client = _Client(doc=_Doc({'hidden_versions': ['bogus']}))

    def _boom(a, b):
        raise ValueError('malformed version')

    _compare_versions.impl = _boom  # type: ignore[attr-defined]
    try:
        with _serve_config(client):
            # A malformed version comparison must be skipped, not propagated.
            assert arc.should_hide_subscription_ui('', 'ios', 'not-a-version') is False
    finally:
        _compare_versions.impl = lambda a, b: 0 if a == b else (-1 if a < b else 1)  # type: ignore[attr-defined]


if __name__ == '__main__':
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_') and callable(value)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f'PASS {test.__name__}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL {test.__name__}: {exc}')
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f'ERROR {test.__name__}: {type(exc).__name__}: {exc}')
    print(f'\n{len(tests) - failures}/{len(tests)} tests passed')
    sys.exit(1 if failures else 0)
