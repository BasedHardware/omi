"""batch_update_action_items (task reorder) must honor its missing_ids contract under a concurrent
delete, not fail the whole request with a raw provider error.

The reorder endpoint promises: ids that no longer exist come back in ``missing_ids`` while the rest
are applied. The pre-port implementation used a plain ``store.exists()`` gate followed by a separate
``store.update()`` — a TOCTOU window where a delete landing in between made ``update()`` raise a raw
not-found (Firestore) and 500 the request. The fix runs the existence gate and the write inside one
transaction, so a vanished doc is normalized to ``missing_ids``. Exercised through the real
``_store()`` seam via ``FakeDocumentStore``.
"""

from types import SimpleNamespace

from database import action_items as action_items_db
from tests.store_fakes import FakeDocumentStore

_UID = 'uid'


def _entry(item_id, *, sort_order=None, indent_level=None):
    return SimpleNamespace(id=item_id, sort_order=sort_order, indent_level=indent_level)


def _bind(monkeypatch, store):
    monkeypatch.setattr(action_items_db, '_store', lambda: store)


def _seed(store, item_id):
    store._docs[f'users/{_UID}/action_items/{item_id}'] = {'sort_order': 0, 'indent_level': 0}


def test_missing_ids_are_reported_and_present_ids_updated(monkeypatch):
    store = FakeDocumentStore()
    _seed(store, 'present-1')
    _seed(store, 'present-2')
    _bind(monkeypatch, store)

    result = action_items_db.batch_update_action_items(
        _UID,
        [
            _entry('present-1', sort_order=5),
            _entry('absent', sort_order=9),
            _entry('present-2', indent_level=2),
        ],
    )

    assert result.updated_ids == ['present-1', 'present-2']
    assert result.missing_ids == ['absent']
    assert store._docs[f'users/{_UID}/action_items/present-1']['sort_order'] == 5
    assert store._docs[f'users/{_UID}/action_items/present-2']['indent_level'] == 2


def test_noop_entry_is_reported_before_any_store_access(monkeypatch):
    store = FakeDocumentStore()
    _bind(monkeypatch, store)

    # No sort_order / indent_level → nothing to change → noop, even though the doc is absent.
    result = action_items_db.batch_update_action_items(_UID, [_entry('any')])

    assert result.noop_ids == ['any']
    assert result.updated_ids == []
    assert result.missing_ids == []


def test_concurrent_delete_is_normalized_to_missing_ids(monkeypatch):
    """A doc present when the request arrives but deleted as its write transaction begins must land
    in missing_ids without raising. ``update`` on the vanished path raises to prove the write is
    gated inside the transaction (never a blind post-read update)."""

    class _ConcurrentDelete(Exception):
        pass

    class _ConcurrentDeleteStore(FakeDocumentStore):
        def __init__(self, racing_id):
            super().__init__()
            self._racing_id = racing_id

        def run_transaction(self, fn, *, attempts=3):
            # The delete lands the instant this reorder's transactions start running.
            self._docs.pop(f'users/{_UID}/action_items/{self._racing_id}', None)
            return super().run_transaction(fn)

        def update(self, path, data):
            if path.endswith(f'/{self._racing_id}'):
                raise _ConcurrentDelete('document deleted concurrently')
            return super().update(path, data)

    store = _ConcurrentDeleteStore('racing')
    _seed(store, 'racing')
    _seed(store, 'survivor')
    _bind(monkeypatch, store)

    result = action_items_db.batch_update_action_items(
        _UID,
        [_entry('racing', sort_order=3), _entry('survivor', sort_order=7)],
    )

    assert result.missing_ids == ['racing']
    assert result.updated_ids == ['survivor']
    assert store._docs[f'users/{_UID}/action_items/survivor']['sort_order'] == 7
