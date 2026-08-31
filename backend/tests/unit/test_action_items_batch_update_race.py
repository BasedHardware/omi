"""batch_update_action_items (task reorder) must honor its missing_ids contract under a concurrent
delete, not fail the whole request with a raw provider error.

The reorder endpoint promises: ids that no longer exist come back in ``missing_ids`` while the rest
are applied. Each row is a standalone ``update()`` that raises ``NotFound`` on a vanished document
(the write itself is the existence gate — no separate pre-read TOCTOU window), so a delete landing
the instant before the write is normalized to ``missing_ids`` rather than 500-ing the request.
Exercised through the ADR-0044 facade seam (``install_fake_db_client``): the fake's neutral
``NotFound`` is translated by the facade to the ``google`` ``NotFound`` the source catches.
"""

from types import SimpleNamespace

from database import action_items as action_items_db
from tests.store_fakes import FakeDocumentStore, install_fake_db_client

_UID = 'uid'


def _entry(item_id, *, sort_order=None, indent_level=None):
    return SimpleNamespace(id=item_id, sort_order=sort_order, indent_level=indent_level)


def _bind(monkeypatch, store):
    install_fake_db_client(monkeypatch, store=store)


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
    """A doc present when the request arrives but deleted the instant its write begins must land in
    missing_ids without raising. The racing store drops the doc right before its ``update``, so the
    write hits a vanished path and raises NotFound — proving the write itself is the gate (never a
    blind pre-read + update), and that the facade surfaces it as the NotFound the source catches."""

    class _ConcurrentDeleteStore(FakeDocumentStore):
        def __init__(self, racing_id):
            super().__init__()
            self._racing_id = racing_id
            self._deleted = False

        def update(self, path, data, *, if_updated_at=None):
            if path.endswith(f'/{self._racing_id}') and not self._deleted:
                # The concurrent delete lands the instant before our write.
                self._deleted = True
                self._docs.pop(path, None)
            return super().update(path, data, if_updated_at=if_updated_at)

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
