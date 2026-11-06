"""Domain adapters must implement the storage-neutral protocol surfaces."""

import ast
import inspect
from pathlib import Path

import pytest

from database.folders import FirestoreFolders
from database.people import FirestorePeople
from database.ports.base import SpaceStore
from database.ports.folders import FoldersRepo, FoldersTx
from database.ports.people import PeopleRepo, PeopleTx
from database.space_store import FirestoreSpaceStore
from testing.domain_sim.store import SimFolders, SimPeople, SimSpaceStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, ReadAfterWriteError


@pytest.mark.parametrize(
    'protocol,adapter',
    [
        (FoldersRepo, FirestoreFolders),
        (FoldersTx, FirestoreFolders),
        (PeopleTx, FirestorePeople),
        (PeopleRepo, FirestorePeople),
        (SpaceStore, FirestoreSpaceStore),
        (SpaceStore, SimSpaceStore),
        (FoldersRepo, SimFolders),
        (PeopleRepo, SimPeople),
    ],
)
def test_protocol_signatures(protocol, adapter):
    methods = {
        name
        for parent in protocol.__mro__
        for name, member in vars(parent).items()
        if not name.startswith('_') and inspect.isfunction(member)
    }
    for name in methods:
        expected = inspect.signature(getattr(protocol, name)).parameters
        actual = inspect.signature(getattr(adapter, name)).parameters
        assert list(actual) == list(expected), (adapter, name)
        assert [p.kind for p in actual.values()] == [p.kind for p in expected.values()]
        assert [p.default for p in actual.values()] == [p.default for p in expected.values()]


def test_ports_are_pure():
    import sys

    root = Path(__file__).resolve().parents[2] / 'database' / 'ports'
    allowed = sys.stdlib_module_names | {'pydantic'}
    for path in root.glob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.level == 1 and node.module in {'base', 'folders', 'people'}) or (
                    node.level == 0 and (node.module or '').split('.')[0] in allowed
                ), (path, node.module)
            elif isinstance(node, ast.Import):
                assert all(alias.name.split('.')[0] in allowed for alias in node.names), path
    sim = root.parents[1] / 'testing' / 'domain_sim' / 'store.py'
    assert 'google.' not in sim.read_text()


def test_firestore_uow_keeps_sdk_read_before_write_rule():
    client = StrictFirestore({('users', 's', 'people', 'p'): {'id': 'p', 'name': 'Synthetic'}})
    store = FirestoreSpaceStore('s', firestore_client=client)

    def body(tx):
        tx.people.set_pinned('p', True)
        tx.people.read_generation()

    with pytest.raises(ReadAfterWriteError):
        store.run(body)
