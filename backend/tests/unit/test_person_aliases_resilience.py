"""person_aliases must validate Firestore path segments and fail safe on transport errors.

`backend/database/person_aliases.py` builds `users/{uid}/people/{person_id}` paths
straight from caller-supplied identifiers. Before this change:

* an empty or separator-bearing `uid` / `person_id` was interpolated into the
  document path (e.g. an empty uid produced `users//people/...`),
* a transient Firestore/transport error propagated out of the rename and
  dismiss helpers and surfaced as a user-visible 500.

This test imports the module with its Firestore / chat_edits collaborators
stubbed (no network, no pydantic) and drives it with injected fakes. Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_person_aliases_resilience.py
"""

import json
import os
import sys
import types
from typing import Any

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


def _mod(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


# --- stub the heavy collaborators before importing the module under test -----

google = _mod('google')
google.__path__ = []  # type: ignore[attr-defined]
g_cloud = _mod('google.cloud')
g_cloud.__path__ = []  # type: ignore[attr-defined]
g_firestore = _mod('google.cloud.firestore_v1')
g_firestore.__path__ = []  # type: ignore[attr-defined]
g_api = _mod('google.api_core')
g_api.__path__ = []  # type: ignore[attr-defined]
g_exc = _mod('google.api_core.exceptions')


class NotFound(Exception):
    pass


class FieldFilter:
    def __init__(self, field: str, op: str, value: Any) -> None:
        self.field = field
        self.op = op
        self.value = value


def transactional(func: Any) -> Any:
    return func


g_exc.NotFound = NotFound  # type: ignore[attr-defined]
g_firestore.FieldFilter = FieldFilter  # type: ignore[attr-defined]
g_firestore.transactional = transactional  # type: ignore[attr-defined]

import database  # noqa: E402

chat_edits = _mod('database.chat_edits')
chat_edits.FIELDS = {'person': ['name']}  # type: ignore[attr-defined]
chat_edits.encode = lambda fields: json.dumps(fields, sort_keys=True, default=str)  # type: ignore[attr-defined]
database.chat_edits = chat_edits  # type: ignore[attr-defined]

from database import person_aliases as pa  # noqa: E402

# --- fakes for the Firestore surface ----------------------------------------


class _Snapshot:
    def __init__(self, data: Any, exists: bool = True) -> None:
        self._data = data
        self.exists = exists

    def to_dict(self) -> Any:
        return self._data


class _Tx:
    def __init__(self) -> None:
        self.patches: list[Any] = []

    def update(self, ref: Any, patch: Any) -> None:
        self.patches.append(patch)


class _Client:
    """Chainable stand-in for a Firestore client / document reference."""

    def __init__(self, snapshot: Any = None, *, raises: BaseException | None = None) -> None:
        self._snapshot = snapshot
        self._raises = raises
        self.path: list[str] = []
        self.tx = _Tx()

    def collection(self, name: str) -> '_Client':
        self.path.append(name)
        return self

    def document(self, doc_id: str) -> '_Client':
        self.path.append(doc_id)
        return self

    def get(self, transaction: Any = None) -> _Snapshot:
        if self._raises is not None:
            raise self._raises
        return self._snapshot if self._snapshot is not None else _Snapshot(None, exists=False)

    def transaction(self) -> _Tx:
        return self.tx

    def stream(self) -> list[Any]:
        if self._raises is not None:
            raise self._raises
        return []

    def where(self, filter: Any = None) -> '_Client':  # noqa: A002
        return self


# --- _clean_id ---------------------------------------------------------------


def test_clean_id_accepts_simple_tokens():
    assert pa._clean_id('uid1') == 'uid1'
    assert pa._clean_id(' person-1 ') == 'person-1'


def test_clean_id_rejects_unsafe_values():
    assert pa._clean_id('') is None
    assert pa._clean_id('   ') is None
    assert pa._clean_id('../users/x') is None
    assert pa._clean_id('a/b') is None
    assert pa._clean_id('a\\b') is None
    assert pa._clean_id('a:b') is None
    assert pa._clean_id('..') is None
    assert pa._clean_id(None) is None
    assert pa._clean_id(42) is None
    assert pa._clean_id('x' * (pa._MAX_ID_LENGTH + 1)) is None


# --- rename ------------------------------------------------------------------


def test_rename_rejects_invalid_uid_without_touching_firestore():
    client = _Client(snapshot=_Snapshot({'name': 'Old'}))
    assert pa.rename_person_retaining_aliases(client, '', 'p1', 'New') is False
    assert client.path == [], 'invalid uid must not reach the Firestore path builder'


def test_rename_rejects_invalid_person_id():
    client = _Client(snapshot=_Snapshot({'name': 'Old'}))
    assert pa.rename_person_retaining_aliases(client, 'u1', 'a/b', 'New') is False
    assert client.path == []


def test_rename_succeeds_and_writes_expected_path():
    client = _Client(snapshot=_Snapshot({'name': 'Old'}))
    assert pa.rename_person_retaining_aliases(client, 'u1', 'p1', 'New') is True
    assert client.path == ['users', 'u1', 'people', 'p1']
    assert client.tx.patches and client.tx.patches[0]['name'] == 'New'


def test_rename_maps_not_found_to_false():
    client = _Client(raises=NotFound('gone'))
    assert pa.rename_person_retaining_aliases(client, 'u1', 'p1', 'New') is False


def test_rename_swallows_transport_errors():
    client = _Client(raises=RuntimeError('transport reset'))
    assert pa.rename_person_retaining_aliases(client, 'u1', 'p1', 'New') is False


def test_rename_reraises_permission_error():
    client = _Client(snapshot=_Snapshot({'name': 'Old'}))
    try:
        pa.rename_person_retaining_aliases(
            client, 'u1', 'p1', 'New', expected_chat_state={'before': 'stale', 'after': None}
        )
    except PermissionError:
        return
    raise AssertionError('optimistic-concurrency conflict must still surface to the caller')


# --- dismiss -----------------------------------------------------------------


def test_dismiss_rejects_invalid_identifiers():
    client = _Client(snapshot=_Snapshot({'name': 'Old'}))
    assert pa.dismiss_person_soft(client, 'u1', '../p') is False
    assert client.path == []


def test_dismiss_swallows_transport_errors():
    client = _Client(raises=RuntimeError('transport reset'))
    assert pa.dismiss_person_soft(client, 'u1', 'p1') is False


# --- get_person_aliases ------------------------------------------------------


def test_get_person_aliases_returns_normalized_values():
    client = _Client(snapshot=_Snapshot({'aliases': [' Alice ', 'Bob', 7, '']}))
    assert pa.get_person_aliases(client, 'u1', 'p1') == ['Alice', 'Bob']


def test_get_person_aliases_returns_empty_on_error_or_missing():
    assert pa.get_person_aliases(_Client(raises=RuntimeError('boom')), 'u1', 'p1') == []
    assert pa.get_person_aliases(_Client(snapshot=_Snapshot(None, exists=False)), 'u1', 'p1') == []
    assert pa.get_person_aliases(_Client(), 'u1', 'a/b') == []


# --- listing / lookup --------------------------------------------------------


def test_list_people_rejects_invalid_uid():
    client = _Client()
    assert pa.list_people(client, 'u/1') == []
    assert client.path == []


def test_find_person_by_name_rejects_invalid_uid():
    client = _Client()
    assert pa.find_person_by_name(client, '', 'Alice') is None
    assert client.path == []


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
