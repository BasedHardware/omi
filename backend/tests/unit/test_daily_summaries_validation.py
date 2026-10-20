"""daily_summaries must validate path segments, counters, and pagination bounds.

`backend/database/daily_summaries.py` builds `users/{uid}/...` paths and merges
device counters from client payloads. Before this change:

* `upsert_desktop_daily_usage` indexed `counters[field]` directly, so a partial
  counter set raised `KeyError` and aborted the whole write,
* an empty `uid` produced `users//daily_summaries/...` and wrote orphaned docs,
* an unbounded/negative `limit` or `offset` reached Firestore as an invalid query.

This test imports the module with its Firestore collaborators stubbed (no
network, no google-cloud install) and drives it with injected fakes. Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_daily_summaries_validation.py
"""

import os
import sys
import types

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class FieldFilter:
    def __init__(self, field: str, op: str, value: object) -> None:
        self.field = field
        self.op = op
        self.value = value


class _Query:
    DESCENDING = 'DESCENDING'


def transactional(func: object) -> object:
    return func


class _Snap:
    def __init__(self, data: object, exists: bool = True) -> None:
        self._data = data
        self.exists = exists

    def to_dict(self) -> object:
        return self._data


class _Tx:
    def __init__(self) -> None:
        self.sets: list[object] = []

    def set(self, ref: object, payload: object) -> None:
        self.sets.append(payload)


class _FakeClient:
    def __init__(self) -> None:
        self.path: list[tuple[str, str]] = []
        self.sets: list[object] = []
        self.updates: list[object] = []
        self.deletes = 0
        self.limits: list[int] = []
        self.offsets: list[int] = []
        self.wheres: list[object] = []
        self.snapshot = _Snap(None, exists=False)
        self.stream_docs: list[object] = []
        self.tx = _Tx()

    def collection(self, name: str) -> '_FakeClient':
        self.path.append(('collection', name))
        return self

    def document(self, doc_id: str) -> '_FakeClient':
        self.path.append(('document', doc_id))
        return self

    def get(self, transaction: object = None) -> _Snap:
        return self.snapshot

    def set(self, payload: object) -> None:
        self.sets.append(payload)

    def update(self, payload: object) -> None:
        self.updates.append(payload)

    def delete(self) -> None:
        self.deletes += 1

    def where(self, filter: object = None) -> '_FakeClient':  # noqa: A002
        self.wheres.append(filter)
        return self

    def order_by(self, *args: object, **kwargs: object) -> '_FakeClient':
        return self

    def limit(self, value: int) -> '_FakeClient':
        self.limits.append(value)
        return self

    def offset(self, value: int) -> '_FakeClient':
        self.offsets.append(value)
        return self

    def stream(self) -> list[object]:
        return self.stream_docs

    def transaction(self) -> _Tx:
        return self.tx


_fake = _FakeClient()


def _load_module_under_test() -> types.ModuleType:
    """Import ``database.daily_summaries`` with its Firestore collaborators stubbed.

    Tier 2 of ``backend/docs/test_isolation.md``: these fakes must be active
    *before* the target module imports, so they are installed through the
    sanctioned ``stub_modules`` helper inside this loader — never by mutating
    ``sys.modules`` at module scope, which leaks fakes across test files.
    """
    from testing.import_isolation import AutoMockModule, stub_modules

    google = AutoMockModule('google')
    google.__path__ = []  # type: ignore[attr-defined]
    g_cloud = AutoMockModule('google.cloud')
    g_cloud.__path__ = []  # type: ignore[attr-defined]
    g_firestore = AutoMockModule('google.cloud.firestore_v1')
    g_firestore.__path__ = []  # type: ignore[attr-defined]
    g_base_query = AutoMockModule('google.cloud.firestore_v1.base_query')
    g_base_query.FieldFilter = FieldFilter
    g_firestore.transactional = transactional
    g_firestore.Query = _Query
    g_cloud.firestore = g_firestore

    client_mod = AutoMockModule('database._client')
    client_mod.db = _fake
    client_mod.get_firestore_client = lambda: _fake

    redis_mod = AutoMockModule('database.redis_db')
    redis_mod.remove_daily_summary_to_uid = lambda summary_id: None

    with stub_modules(
        {
            'google': google,
            'google.cloud': g_cloud,
            'google.cloud.firestore_v1': g_firestore,
            'google.cloud.firestore_v1.base_query': g_base_query,
            'database._client': client_mod,
            'database.redis_db': redis_mod,
        }
    ):
        from database import daily_summaries as module

    return module


ds = _load_module_under_test()


def _fresh() -> _FakeClient:
    client = _FakeClient()
    ds.db = client  # type: ignore[assignment]
    return client


# --- validators --------------------------------------------------------------


def test_clean_uid_rejects_unsafe_values():
    for bad in ['', '   ', 'a/b', 'a\\b', 'a:b', None, 7, 'x' * (ds._MAX_ID_LENGTH + 1)]:
        try:
            ds._clean_uid(bad)
        except ValueError:
            continue
        raise AssertionError(f'_clean_uid accepted {bad!r}')
    assert ds._clean_uid(' uid1 ') == 'uid1'


def test_clean_id_rejects_relative_and_separator_values():
    for bad in ['', '.', '..', 'a/b', 'a:b', None]:
        try:
            ds._clean_id(bad, 'summary_id')
        except ValueError:
            continue
        raise AssertionError(f'_clean_id accepted {bad!r}')
    assert ds._clean_id('s1') == 's1'


def test_clean_date_requires_iso_day():
    for bad in ['', '2026-9-1', 'not-a-date', None, '2026/09/01']:
        try:
            ds._clean_date(bad)
        except ValueError:
            continue
        raise AssertionError(f'_clean_date accepted {bad!r}')
    assert ds._clean_date(' 2026-09-01 ') == '2026-09-01'


# --- the real crash: partial counters ---------------------------------------


def test_upsert_accepts_partial_counters():
    """A counter dict that omits fields must not raise KeyError mid-write."""
    client = _fresh()
    ds.upsert_desktop_daily_usage('uid1', '2026-09-01', 'Asia/Jakarta', 'dev1', {'watching_seconds': 12})
    assert len(client.tx.sets) == 1
    payload = client.tx.sets[0]
    assert payload['watching_seconds'] == 12
    assert payload['listening_seconds'] == 0
    assert payload['ptt_turns'] == 0


def test_upsert_merges_by_max_and_ignores_bad_counters():
    """Existing totals win when larger; non-int/bool/negative values become 0."""
    client = _fresh()
    client.snapshot = _Snap(
        {
            'watching_seconds': 90,
            'listening_seconds': 5,
            'proactive_cards_shown': 'oops',
            'proactive_cards_acted': True,
            'ptt_turns': -4,
        },
        exists=True,
    )
    ds.upsert_desktop_daily_usage(
        'uid1',
        '2026-09-01',
        'Asia/Jakarta',
        'dev1',
        {'watching_seconds': 30, 'listening_seconds': 7, 'ptt_turns': 2},
    )
    payload = client.tx.sets[0]
    assert payload['watching_seconds'] == 90
    assert payload['listening_seconds'] == 7
    assert payload['proactive_cards_shown'] == 0
    assert payload['proactive_cards_acted'] == 0
    assert payload['ptt_turns'] == 2


def test_upsert_rejects_unsafe_path_segments():
    for kwargs in (
        {'uid': '', 'date': '2026-09-01', 'client_device_id': 'dev1'},
        {'uid': 'u/1', 'date': '2026-09-01', 'client_device_id': 'dev1'},
        {'uid': 'uid1', 'date': '2026-9-1', 'client_device_id': 'dev1'},
        {'uid': 'uid1', 'date': '2026-09-01', 'client_device_id': 'a/b'},
    ):
        client = _fresh()
        try:
            ds.upsert_desktop_daily_usage(kwargs['uid'], kwargs['date'], 'Asia/Jakarta', kwargs['client_device_id'], {})
        except ValueError:
            continue
        raise AssertionError(f'upsert accepted {kwargs!r}')


def test_upsert_uses_cleaned_segments_in_the_doc_path():
    client = _fresh()
    ds.upsert_desktop_daily_usage(' uid1 ', ' 2026-09-01 ', 'Asia/Jakarta', ' dev1 ', {})
    assert ('document', 'uid1') in client.path
    assert ('document', '2026-09-01__dev1') in client.path


# --- pagination --------------------------------------------------------------


def test_get_daily_summaries_clamps_pagination():
    client = _fresh()
    ds.get_daily_summaries('uid1', limit=10**6, offset=-5)
    assert client.limits == [ds._MAX_PAGE_LIMIT]
    assert client.offsets == [0]

    client = _fresh()
    ds.get_daily_summaries('uid1', limit=-3, offset=2)
    assert client.limits == [ds._MIN_PAGE_LIMIT]
    assert client.offsets == [2]


def test_get_daily_summaries_rejects_invalid_uid():
    client = _fresh()
    try:
        ds.get_daily_summaries('users//x')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid uid must raise')
    assert client.path == []


# --- summary id validation ---------------------------------------------------


def test_create_daily_summary_requires_id():
    _fresh()
    try:
        ds.create_daily_summary('uid1', {'date': '2026-09-01'})
    except ValueError:
        return
    raise AssertionError('summary_data without id must raise')


def test_get_daily_summary_rejects_separator_id():
    client = _fresh()
    try:
        ds.get_daily_summary('uid1', 'a/b')
    except ValueError:
        pass
    else:
        raise AssertionError('separator-bearing summary_id must raise')
    assert client.path == []


def test_delete_daily_summary_uses_cleaned_id():
    client = _fresh()
    assert ds.delete_daily_summary('uid1', ' s1 ') is True
    assert client.deletes == 1
    assert ('document', 's1') in client.path


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
